#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="/root/metadata-fix-backups"
TARGET="/root/docker-compose/emby-tools"
TOOL="${TARGET}/fix-strm-chinese-titles.py"
INSTALLER="${TARGET}/fix-emby-strm-chinese-titles.sh"
SERVICE="/etc/systemd/system/emby-fix-strm-titles.service"
TIMER="/etc/systemd/system/emby-fix-strm-titles.timer"

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

ACTION="${1:-install}"
SELF="$(readlink -f -- "${BASH_SOURCE[0]}")"
case "${ACTION}" in
  install|status|run|uninstall|apply|dry-run) ;;
  *)
    echo "用法: $0 [install|status|run|uninstall|apply|dry-run]"
    exit 2
    ;;
esac

install -d -m 0755 "${TARGET}"
install -d -m 0755 "${BACKUP_DIR}"
if [[ "${SELF}" != "${INSTALLER}" ]]; then
  install -m 0755 "${SELF}" "${INSTALLER}"
fi

cat >"${TOOL}" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import re
import shutil
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


DB = Path("/root/docker-compose/emby/config/data/library.db")
AUTH_DB = Path("/root/docker-compose/emby/config/data/authentication.db")
BACKUP_DIR = Path("/root/metadata-fix-backups")
CONFIG = Path("/root/docker-compose/emby-tools/strm-fixer-roots.json")
EMBY_BASE = "http://127.0.0.1:8096"
TOKEN_FILES = [
    Path("/root/docker-compose/embystream/config/config.toml"),
    Path("/root/docker-compose/embystream-test/config/config.toml"),
]
DEFAULT_ROOTS = [
    Path("/home/symedia_gd/movies"),
    Path("/home/symedia_rclone_zero/movies"),
]
CJK = re.compile(r"[\u4e00-\u9fff]")
FOLDER_RE = re.compile(r"(.+?) \(\d{4}\) \{tmdb-\d+\}$")
TITLE_RE = re.compile(r"(<title>)(.*?)(</title>)", re.S | re.I)
SORT_RE = re.compile(r"(<sorttitle>)(.*?)(</sorttitle>)", re.S | re.I)
PLOT_RE = re.compile(r"(<plot>)(.*?)(</plot>)", re.S | re.I)
OUTLINE_RE = re.compile(r"(<outline>)(.*?)(</outline>)", re.S | re.I)
TOKEN_RE = re.compile(r'token\s*=\s*"([^"]+)"|api_key=([^&\s]+)|Token="([^"]+)"', re.I)
MODE = os.environ.get("FIX_REFRESH_MODE", "missing")


def clean_token(value: str) -> str:
    return "".join(ch for ch in urllib.parse.unquote(value).strip() if ch.isalnum())


def emby_db_token() -> str:
    if not AUTH_DB.exists():
        return ""
    try:
        con = sqlite3.connect(f"file:{AUTH_DB}?mode=ro", uri=True)
        row = con.execute(
            "select AccessToken from Tokens_2 where IsActive=1 "
            "order by DateLastActivityInt desc limit 1"
        ).fetchone()
        con.close()
    except sqlite3.Error:
        return ""
    if not row:
        return ""
    token = clean_token(str(row[0]))
    return token if len(token) >= 20 else ""


def emby_token() -> str:
    token = emby_db_token()
    if token:
        return token
    for path in TOKEN_FILES:
        try:
            text = path.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        for groups in TOKEN_RE.findall(text):
            token = next((part for part in groups if part), "")
            token = clean_token(token)
            if len(token) >= 20:
                return token
    log_path = Path("/root/docker-compose/emby/config/logs/embyserver.txt")
    try:
        text = log_path.read_text("utf-8", errors="ignore")[-2_000_000:]
    except OSError:
        return ""
    for groups in TOKEN_RE.findall(text):
        token = next((part for part in groups if part), "")
        token = clean_token(token)
        if len(token) >= 20:
            return token
    return ""


def configured_roots() -> list[Path]:
    try:
        data = json.loads(CONFIG.read_text("utf-8"))
        if "title_roots" not in data:
            return DEFAULT_ROOTS
        roots = [Path(value) for value in data.get("title_roots", []) if isinstance(value, str)]
        roots = [root for root in roots if str(root).startswith("/home/")]
        return roots
    except (OSError, json.JSONDecodeError):
        return DEFAULT_ROOTS


def title_from_path(path: str) -> str | None:
    if not path:
        return None
    media_path = Path(path)
    for root in configured_roots():
        try:
            rel = media_path.relative_to(root)
        except ValueError:
            continue
        for part in rel.parts[:-1]:
            match = FOLDER_RE.match(part)
            if match:
                title = match.group(1).strip()
                return title if CJK.search(title) else None
    return None


def fix_nfo(path: str, title: str, dry_run: bool) -> tuple[bool, str]:
    nfo = Path(path).with_suffix(".nfo")
    if not nfo.exists():
        return False, "missing"
    try:
        data = nfo.read_text("utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)
    changed = False
    match = TITLE_RE.search(data)
    if match and match.group(2).strip() != title:
        data = TITLE_RE.sub(lambda m: m.group(1) + title + m.group(3), data, count=1)
        changed = True
    sort_match = SORT_RE.search(data)
    if sort_match:
        if sort_match.group(2).strip() != title:
            data = SORT_RE.sub(lambda m: m.group(1) + title + m.group(3), data, count=1)
            changed = True
    elif "</title>" in data:
        data = data.replace("</title>", f"</title>\n  <sorttitle>{title}</sorttitle>", 1)
        changed = True
    if changed and not dry_run:
        try:
            nfo.write_text(data, "utf-8")
        except OSError as exc:
            return False, str(exc)
    return changed, "changed" if changed else "unchanged"


def nfo_has_chinese_overview(path: str) -> bool:
    nfo = Path(path).with_suffix(".nfo")
    try:
        data = nfo.read_text("utf-8", errors="ignore")
    except OSError:
        return False
    for pattern in (PLOT_RE, OUTLINE_RE):
        match = pattern.search(data)
        if match and CJK.search(match.group(2)):
            return True
    return False


def refresh_item(item_id: int, token: str, full: bool) -> bool:
    if not token:
        return False
    query = {
        "api_key": token,
        "Recursive": "false",
        "MetadataRefreshMode": "FullRefresh",
        "ImageRefreshMode": "Default",
        "ReplaceAllMetadata": "true" if full else "false",
        "ReplaceAllImages": "false",
    }
    url = f"{EMBY_BASE}/emby/Items/{item_id}/Refresh?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return 200 <= resp.status < 300


def find_changes(cur: sqlite3.Cursor, dry_run: bool) -> tuple[list[tuple[int, str, str, str]], int, list[tuple[int, str, str, str]], dict]:
    cur.execute(
        "select Id, Name, SortName, OriginalTitle, Path, Overview, DateLastRefreshed from MediaItems "
        "where Path like '/home/%'"
    )
    changes: list[tuple[int, str, str, str]] = []
    refreshes: list[tuple[int, str, str, str]] = []
    nfo_changes = 0
    stats = {"items_scanned": 0, "strm_checked": 0, "title_needed": 0, "overview_refresh_needed": 0, "nfo_failed": []}
    for item_id, name, sort_name, original_title, path, overview, date_last_refreshed in cur.fetchall():
        stats["items_scanned"] += 1
        print(f"CHECK_ITEM|{stats['items_scanned']}|{item_id}|{path}")
        if not path or not path.endswith(".strm"):
            continue
        stats["strm_checked"] += 1
        title = title_from_path(path)
        if not title:
            continue
        current = name or ""
        overview_text = overview or ""
        needs_title = current != title and not CJK.search(current)
        needs_overview = not overview_text.strip() or not CJK.search(overview_text)
        needs_first_scan = not date_last_refreshed
        if needs_title:
            stats["title_needed"] += 1
            changes.append((item_id, current, title, path))
        nfo_changed, nfo_reason = fix_nfo(path, title, dry_run)
        nfo_changes += int(nfo_changed)
        if nfo_reason not in {"missing", "unchanged", "changed"}:
            stats["nfo_failed"].append((item_id, path, nfo_reason))
        if MODE == "full" or needs_overview or needs_first_scan or not nfo_has_chinese_overview(path):
            stats["overview_refresh_needed"] += 1
            refreshes.append((item_id, current, title, path))
    return changes, nfo_changes, refreshes, stats


def main() -> int:
    started = time.monotonic()
    dry_run = os.environ.get("DRY_RUN") == "1"
    if not DB.exists():
        raise SystemExit(f"missing db: {DB}")

    con = sqlite3.connect(DB)
    cur = con.cursor()
    changes, nfo_changes, refreshes, stats = find_changes(cur, dry_run)
    mode = MODE

    if dry_run:
        duration = time.monotonic() - started
        print(
            "SUMMARY|chinese_metadata|dry_run=1|"
            f"items_scanned={stats['items_scanned']}|strm_checked={stats['strm_checked']}|"
            f"title_needed={len(changes)}|nfo_changed={nfo_changes}|nfo_failed={len(stats['nfo_failed'])}|"
            f"refresh_needed={len(refreshes)}|duration_seconds={duration:.1f}|mode={mode}"
        )
        print(f"dry_run=1 changed={len(changes)} nfo_changed={nfo_changes} refresh={len(refreshes)} failed={len(stats['nfo_failed'])} mode={mode}")
        for item_id, old_name, title, path in changes:
            print(f"WOULD_FIX|{item_id}|{old_name}|{title}|{path}")
        for item_id, old_name, title, path in refreshes:
            print(f"WOULD_REFRESH|{item_id}|{old_name}|{title}|{path}")
        for item_id, path, reason in stats["nfo_failed"]:
            print(f"FAIL|nfo|item={item_id}|path={path}|reason={reason}")
        con.close()
        return 0

    if not changes and not refreshes:
        duration = time.monotonic() - started
        print(
            "SUMMARY|chinese_metadata|"
            f"items_scanned={stats['items_scanned']}|strm_checked={stats['strm_checked']}|"
            f"title_needed=0|title_success=0|title_failed=0|nfo_changed=0|nfo_failed={len(stats['nfo_failed'])}|"
            f"refresh_needed=0|refresh_success=0|refresh_failed=0|duration_seconds={duration:.1f}|mode={mode}"
        )
        for item_id, path, reason in stats["nfo_failed"]:
            print(f"FAIL|nfo|item={item_id}|path={path}|reason={reason}")
        print(f"changed=0 nfo_changed=0 refreshed=0 failed={len(stats['nfo_failed'])} mode={mode}")
        print(
            "RESULT|chinese_metadata|"
            f"mode={mode}|items_scanned={stats['items_scanned']}|strm_checked={stats['strm_checked']}|"
            f"title_needed=0|title_success=0|title_failed=0|nfo_changed=0|nfo_failed={len(stats['nfo_failed'])}|"
            f"refresh_needed=0|refresh_success=0|refresh_failed=0|duration_seconds={duration:.1f}"
        )
        con.close()
        return 0

    backup = None
    if changes:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"library-before-title-fix-{datetime.now():%Y%m%d-%H%M%S}.db"
        shutil.copy2(DB, backup)
    title_success = 0
    title_failures: list[tuple[int, str, str]] = []
    for item_id, old_name, title, path in changes:
        try:
            cur.execute(
                "update MediaItems set Name=?, SortName=? where Id=?",
                (title, title, item_id),
            )
            try:
                cur.execute("update fts_search9 set Name=? where rowid=?", (title, item_id))
            except sqlite3.DatabaseError:
                pass
            title_success += 1
            print(f"TITLE_OK|{item_id}|{old_name}|{title}|{path}")
        except sqlite3.DatabaseError as exc:
            title_failures.append((item_id, path, repr(exc)))
            print(f"TITLE_FAIL|{item_id}|{old_name}|{title}|{path}|{exc}")
    con.commit()
    con.execute("pragma wal_checkpoint(TRUNCATE)")
    con.close()

    token = "" if os.environ.get("FIX_SKIP_REFRESH") == "1" else emby_token()
    refreshed = 0
    refresh_failures: list[tuple[int, str, str]] = []
    if token:
        for item_id, old_name, title, path in refreshes:
            try:
                if refresh_item(item_id, token, full=(mode == "full")):
                    refreshed += 1
                    print(f"REFRESH_OK|{item_id}|{title}|{path}")
                else:
                    refresh_failures.append((item_id, path, "http_not_2xx"))
            except Exception as exc:
                refresh_failures.append((item_id, path, repr(exc)))
                print(f"REFRESH_FAIL|{item_id}|{title}|{path}|{exc}")
    elif refreshes:
        print("WARN|no_emby_token_skip_refresh")
        refresh_failures = [(item_id, path, "missing_token") for item_id, _old_name, _title, path in refreshes]

    if backup:
        print(f"backup={backup}")
    duration = time.monotonic() - started
    print(
        "SUMMARY|chinese_metadata|"
        f"items_scanned={stats['items_scanned']}|strm_checked={stats['strm_checked']}|"
        f"title_needed={len(changes)}|title_success={title_success}|title_failed={len(title_failures)}|"
        f"nfo_changed={nfo_changes}|nfo_failed={len(stats['nfo_failed'])}|"
        f"refresh_needed={len(refreshes)}|refresh_success={refreshed}|refresh_failed={len(refresh_failures)}|duration_seconds={duration:.1f}|mode={mode}"
    )
    for item_id, path, reason in stats["nfo_failed"]:
        print(f"FAIL|nfo|item={item_id}|path={path}|reason={reason}")
    for item_id, path, reason in title_failures:
        print(f"FAIL|title|item={item_id}|path={path}|reason={reason}")
    for item_id, path, reason in refresh_failures:
        print(f"FAIL|refresh|item={item_id}|path={path}|reason={reason}")
    print(f"changed={title_success} nfo_changed={nfo_changes} refreshed={refreshed} failed={len(stats['nfo_failed']) + len(title_failures) + len(refresh_failures)} mode={mode}")
    print(
        "RESULT|chinese_metadata|"
        f"mode={mode}|items_scanned={stats['items_scanned']}|strm_checked={stats['strm_checked']}|"
        f"title_needed={len(changes)}|title_success={title_success}|title_failed={len(title_failures)}|"
        f"nfo_changed={nfo_changes}|nfo_failed={len(stats['nfo_failed'])}|"
        f"refresh_needed={len(refreshes)}|refresh_success={refreshed}|refresh_failed={len(refresh_failures)}|duration_seconds={duration:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x "${TOOL}"

if [[ "${ACTION}" == "status" ]]; then
  systemctl --no-pager --full status emby-fix-strm-titles.timer || true
  systemctl --no-pager --full status emby-fix-strm-titles.service || true
  exit 0
fi

if [[ "${ACTION}" == "run" ]]; then
  systemctl start emby-fix-strm-titles.service
  systemctl --no-pager --full status emby-fix-strm-titles.service
  exit 0
fi

if [[ "${ACTION}" == "uninstall" ]]; then
  systemctl disable --now emby-fix-strm-titles.timer 2>/dev/null || true
  rm -f "${SERVICE}" "${TIMER}"
  systemctl daemon-reload
  echo "Emby STRM 中文标题监控已卸载，保留工具：${TOOL}"
  exit 0
fi

if [[ "${ACTION}" == "dry-run" ]]; then
  DRY_RUN=1 python3 "${TOOL}"
  exit 0
fi

if [[ "${ACTION}" == "apply" ]]; then
  preview="$(DRY_RUN=1 python3 "${TOOL}")"
  pending="$(printf '%s\n' "${preview}" | sed -n 's/^dry_run=1 changed=\([0-9]\+\).*/\1/p' | tail -1)"
  refresh="$(printf '%s\n' "${preview}" | sed -n 's/^dry_run=1 .*refresh=\([0-9]\+\).*/\1/p' | tail -1)"
  if [[ "${pending:-0}" == "0" && "${refresh:-0}" == "0" ]]; then
    echo "没有发现需要修正的中文标题或简介，不重启 Emby。"
    exit 0
  fi
  if [[ "${pending:-0}" == "0" ]]; then
    echo "发现 ${refresh} 个项目需要刷新中文简介或元数据，不停止 Emby。"
    python3 "${TOOL}"
    exit 0
  fi
  echo "发现 ${pending} 个英文标题，停止 Emby 后修复……"
  docker stop emby >/dev/null
  FIX_SKIP_REFRESH=1 python3 "${TOOL}"
  docker start emby >/dev/null
  if [[ "${refresh:-0}" != "0" ]]; then
    echo "Emby 已启动，继续刷新 ${refresh} 个中文简介或元数据项目……"
    python3 "${TOOL}"
  fi
  echo "已重启 Emby。若客户端仍显示旧标题，刷新页面或清理客户端缓存。"
  exit 0
fi

cat >"${SERVICE}" <<EOF
[Unit]
Description=Fix Chinese titles and overviews in Emby STRM libraries
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
Environment=PYTHONUNBUFFERED=1
ExecStart=${INSTALLER} apply
EOF

cat >"${TIMER}" <<'EOF'
[Unit]
Description=Run Emby STRM Chinese metadata fixer periodically

[Timer]
OnBootSec=10min
OnUnitActiveSec=15min
Persistent=true
Unit=emby-fix-strm-titles.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now emby-fix-strm-titles.timer
systemctl start emby-fix-strm-titles.service || true
systemctl --no-pager --full status emby-fix-strm-titles.timer || true
echo "Emby STRM 中文标题监控已安装。"
