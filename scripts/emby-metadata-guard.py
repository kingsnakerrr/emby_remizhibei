#!/usr/bin/env python3
import json
import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path
from xml.etree import ElementTree as ET

import requests


MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/home/symedia_gd"))
EMBY_URL = os.environ.get("EMBY_URL", "http://127.0.0.1:8096/emby").rstrip("/")
EMBY_API_KEY = os.environ.get("EMBY_API_KEY", "")
EMBY_AUTH_DB = Path(os.environ.get(
    "EMBY_AUTH_DB",
    "/root/docker-compose/emby/config/data/authentication.db",
))
BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/root/emby-nfo-title-backups"))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/root/emby-metadata-guard-report.json"))
FOLDER_PATTERN = re.compile(r"^(?P<title>.+?)\s+\((?:18|19|20)\d{2}\)\s+\{tmdb-(?P<tmdb>\d+)\}$", re.I)
CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("emby-metadata-guard")


def expected_identity(nfo_path: Path):
    match = FOLDER_PATTERN.match(nfo_path.parent.name)
    if not match or not CJK_PATTERN.search(match.group("title")):
        return None
    return match.group("title").strip(), match.group("tmdb")


def normalize_nfo(nfo_path: Path):
    identity = expected_identity(nfo_path)
    if not identity:
        return None
    expected_title, tmdb_id = identity
    try:
        tree = ET.parse(nfo_path)
    except (ET.ParseError, OSError) as error:
        log.warning("Cannot parse %s: %s", nfo_path, error)
        return None
    title = tree.getroot().find("title")
    current_title = (title.text or "").strip() if title is not None else ""
    if not current_title or CJK_PATTERN.search(current_title) or current_title == expected_title:
        return None

    relative = nfo_path.relative_to(MEDIA_ROOT)
    backup_path = BACKUP_ROOT / relative
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        shutil.copy2(nfo_path, backup_path)
    title.text = expected_title
    tree.write(nfo_path, encoding="utf-8", xml_declaration=True)
    log.info("Normalized NFO title: %s -> %s (%s)", current_title, expected_title, nfo_path)
    return tmdb_id


def discover_emby_api_key():
    if EMBY_API_KEY:
        return EMBY_API_KEY
    if not EMBY_AUTH_DB.exists():
        return ""
    try:
        db = sqlite3.connect(f"file:{EMBY_AUTH_DB}?mode=ro", uri=True, timeout=10)
        row = db.execute(
            "SELECT AccessToken FROM Tokens_2 WHERE IsActive=1 "
            "ORDER BY DateLastActivityInt DESC LIMIT 1"
        ).fetchone()
        db.close()
    except sqlite3.Error:
        return ""
    return str(row[0]).strip() if row and row[0] else ""


def emby_session():
    api_key = discover_emby_api_key()
    if not api_key:
        raise RuntimeError("No active Emby API token found")
    session = requests.Session()
    session.params.update({"api_key": api_key})
    return session


def admin_user_id(session):
    users = session.get(f"{EMBY_URL}/Users", timeout=20).json()
    admin = next((user for user in users if user.get("Policy", {}).get("IsAdministrator")), None)
    return (admin or users[0])["Id"]


def emby_items(session, user_id):
    items = []
    start = 0
    while True:
        response = session.get(
            f"{EMBY_URL}/Users/{user_id}/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
                "Fields": "Path,ProviderIds,Overview,ProductionYear,ImageTags",
                "StartIndex": start,
                "Limit": 1000,
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("Items", [])
        items.extend(batch)
        start += len(batch)
        if not batch or start >= payload.get("TotalRecordCount", 0):
            return items


def refresh_tmdb_ids(session, items, tmdb_ids):
    refreshed = 0
    for item in items:
        tmdb_id = str((item.get("ProviderIds") or {}).get("Tmdb") or "")
        if tmdb_id not in tmdb_ids:
            continue
        response = session.post(
            f"{EMBY_URL}/Items/{item['Id']}/Refresh",
            params={
                "Recursive": "false",
                "MetadataRefreshMode": "Default",
                "ImageRefreshMode": "Default",
                "ReplaceAllMetadata": "false",
                "ReplaceAllImages": "false",
            },
            timeout=30,
        )
        response.raise_for_status()
        refreshed += 1
    return refreshed


def missing_metadata(items):
    result = []
    for item in items:
        path = item.get("Path") or ""
        if not path.startswith(str(MEDIA_ROOT)):
            continue
        missing = []
        if not (item.get("ImageTags") or {}).get("Primary"):
            missing.append("cover")
        if not (item.get("ProviderIds") or {}).get("Tmdb"):
            missing.append("tmdb")
        if not (item.get("Overview") or "").strip():
            missing.append("overview")
        if not item.get("ProductionYear"):
            missing.append("year")
        if missing:
            result.append({
                "id": item.get("Id"),
                "type": item.get("Type"),
                "name": item.get("Name"),
                "path": path,
                "missing": missing,
            })
    return result


def main():
    changed_tmdb_ids = set()
    for nfo_path in MEDIA_ROOT.glob("movies/**/*.nfo"):
        tmdb_id = normalize_nfo(nfo_path)
        if tmdb_id:
            changed_tmdb_ids.add(tmdb_id)

    session = emby_session()
    user_id = admin_user_id(session)
    items = emby_items(session, user_id)
    refreshed = refresh_tmdb_ids(session, items, changed_tmdb_ids)
    missing = missing_metadata(items)
    report = {
        "normalized_tmdb_ids": sorted(changed_tmdb_ids),
        "refreshed_items": refreshed,
        "item_count": len(items),
        "missing_metadata": missing,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "Completed: normalized=%d refreshed=%d missing=%d",
        len(changed_tmdb_ids), refreshed, len(missing),
    )


if __name__ == "__main__":
    main()
