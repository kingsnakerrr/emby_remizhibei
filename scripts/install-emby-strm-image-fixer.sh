#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="/root/docker-compose/emby-tools"
SCRIPT="${TARGET}/fix-strm-images.py"
SERVICE="/etc/systemd/system/emby-fix-strm-images.service"
TIMER="/etc/systemd/system/emby-fix-strm-images.timer"

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

case "${1:-install}" in
  install|status|run|uninstall) ;;
  *)
    echo "用法: $0 [install|status|run|uninstall]"
    exit 2
    ;;
esac

if [[ "${1:-install}" == "status" ]]; then
  systemctl --no-pager --full status emby-fix-strm-images.timer || true
  systemctl --no-pager --full status emby-fix-strm-images.service || true
  exit 0
fi

if [[ "${1:-install}" == "run" ]]; then
  systemctl start emby-fix-strm-images.service
  systemctl --no-pager --full status emby-fix-strm-images.service
  exit 0
fi

if [[ "${1:-install}" == "uninstall" ]]; then
  systemctl disable --now emby-fix-strm-images.timer 2>/dev/null || true
  rm -f "${SERVICE}" "${TIMER}"
  systemctl daemon-reload
  echo "Emby STRM 图片补齐器已卸载，保留脚本目录：${TARGET}"
  exit 0
fi

install -d -m 0755 "${TARGET}"

cat >"${SCRIPT}" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import sqlite3
import sys
import urllib.parse
import urllib.request


CONFIG = Path("/root/docker-compose/emby-tools/strm-fixer-roots.json")
DB = Path("/root/docker-compose/emby/config/data/library.db")
AUTH_DB = Path("/root/docker-compose/emby/config/data/authentication.db")
EMBY_BASE = "http://127.0.0.1:8096"
TOKEN_FILES = [
    Path("/root/docker-compose/embystream/config/config.toml"),
    Path("/root/docker-compose/embystream-test/config/config.toml"),
]
DEFAULT_ROOTS = [
    # Keep this focused on movie STRM libraries. Wider scans can be expensive
    # and may copy artwork in unrelated folders.
    Path("/home/symedia_gd/movies"),
    Path("/home/symedia_rclone_zero/movies"),
]
IMAGE_KINDS = ["poster.jpg", "fanart.jpg", "backdrop.jpg", "landscape.jpg", "clearlogo.png"]
VIDEO_SUFFIXES = {".strm"}
CJK = re.compile(r"[\u4e00-\u9fff]")
TOKEN_RE = re.compile(r'token\s*=\s*"([^"]+)"|api_key=([^&\s]+)|Token="([^"]+)"', re.I)


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
        if "image_roots" not in data:
            return DEFAULT_ROOTS
        roots = [Path(value) for value in data.get("image_roots", []) if isinstance(value, str)]
        roots = [root for root in roots if str(root).startswith("/home/")]
        return roots
    except (OSError, json.JSONDecodeError):
        return DEFAULT_ROOTS


def safe_copy(src: Path | None, dst: Path) -> tuple[bool, str]:
    if dst.exists():
        return False, "exists"
    if src is None or not src.exists():
        return False, "missing_source"
    if src.stat().st_size <= 0:
        return False, "empty_source"
    try:
        if src.resolve() == dst.resolve():
            return False, "same_file"
    except OSError:
        return False, "resolve_failed"
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        return False, str(exc)
    return True, "copied"


def find_source(folder: Path, kind: str) -> Path | None:
    direct = folder / kind
    if direct.exists() and direct.stat().st_size > 0:
        return direct
    for candidate in sorted(folder.glob(f"*-{kind}")):
        try:
            if candidate.stat().st_size > 0:
                return candidate
        except OSError:
            continue
    return None


def fix_folder(folder: Path) -> tuple[list[tuple[Path, Path]], list[tuple[Path | None, Path, str]], list[tuple[Path | None, Path, str]]]:
    strms = [
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if not strms:
        return [], [], []

    changed: list[tuple[Path, Path]] = []
    failures: list[tuple[Path | None, Path, str]] = []
    missing_sources: list[tuple[Path | None, Path, str]] = []
    for kind in IMAGE_KINDS:
        dst = folder / kind
        src = find_source(folder, kind)
        ok, reason = safe_copy(src, dst)
        if ok and src is not None:
            changed.append((src, dst))
        elif reason == "missing_source":
            missing_sources.append((src, dst, reason))
        elif reason not in {"exists", "same_file"}:
            failures.append((src, dst, reason))

    for strm in strms:
        for kind in IMAGE_KINDS:
            dst = folder / f"{strm.stem}-{kind}"
            src = find_source(folder, kind)
            if src is None:
                continue
            ok, reason = safe_copy(src, dst)
            if ok and src is not None:
                changed.append((src, dst))
            elif reason == "missing_source":
                missing_sources.append((src, dst, reason))
            elif reason not in {"exists", "same_file"}:
                failures.append((src, dst, reason))

    return changed, failures, missing_sources


def item_root(path: str) -> bool:
    try:
        media_path = Path(path)
        return any(media_path.is_relative_to(root) for root in configured_roots())
    except (OSError, ValueError):
        return False


def images_missing(images: str | None) -> bool:
    if not images:
        return True
    lowered = images.lower()
    return "primary" not in lowered or ("backdrop" not in lowered and "art" not in lowered)


def nfo_missing(path: str) -> bool:
    try:
        return not Path(path).with_suffix(".nfo").exists()
    except OSError:
        return True


def needs_metadata_refresh(row: tuple) -> bool:
    item_id, path, name, overview, images, date_last_refreshed = row
    if not path or not str(path).endswith(".strm") or not item_root(path):
        return False
    if not date_last_refreshed:
        return True
    return images_missing(images) or nfo_missing(path) or not (overview or "").strip()


def refresh_item(item_id: int, token: str, full: bool) -> bool:
    if not token:
        return False
    query = {
        "api_key": token,
        "Recursive": "false",
        "MetadataRefreshMode": "FullRefresh" if full else "Default",
        "ImageRefreshMode": "FullRefresh",
        "ReplaceAllMetadata": "true" if full else "false",
        "ReplaceAllImages": "false",
    }
    url = f"{EMBY_BASE}/emby/Items/{item_id}/Refresh?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return 200 <= resp.status < 300


def refresh_emby_missing_or_full(full: bool) -> tuple[int, int, int, list[tuple[int, str, str]]]:
    if not DB.exists():
        return 0, 0, 0, [(0, str(DB), "missing_db")]
    token = emby_token()
    if not token:
        print("WARN|no_emby_token_skip_refresh", file=sys.stderr)
        return 0, 0, 0, [(0, "Emby API", "missing_token")]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select Id, Path, Name, Overview, Images, DateLastRefreshed from MediaItems "
            "where Path like '/home/%' and IsMovie=1"
        ).fetchall()
    finally:
        con.close()
    checked = 0
    needed = 0
    success = 0
    failures: list[tuple[int, str, str]] = []
    for row in rows:
        item_id = int(row[0])
        path = row[1] or ""
        if not path.endswith(".strm") or not item_root(path):
            continue
        checked += 1
        if not full and not needs_metadata_refresh(row):
            continue
        needed += 1
        try:
            if refresh_item(item_id, token, full):
                success += 1
                print(f"REFRESH_OK|{item_id}|{path}")
            else:
                failures.append((item_id, path, "http_not_2xx"))
        except Exception as exc:
            failures.append((item_id, path, repr(exc)))
            print(f"REFRESH_FAIL|{item_id}|{path}|{exc}", file=sys.stderr)
    return checked, needed, success, failures


def main() -> int:
    roots = configured_roots()
    folders_scanned = 0
    strm_folders = 0
    copy_needed = 0
    copy_success = 0
    copy_failures: list[tuple[Path | None, Path, str]] = []
    copy_missing_sources: list[tuple[Path | None, Path, str]] = []
    print(f"RUN|image_metadata|mode={os.environ.get('FIX_REFRESH_MODE', 'missing')}|roots={','.join(str(root) for root in roots) or '-'}")
    for root in roots:
        if not root.exists():
            copy_failures.append((None, root, "root_missing"))
            print(f"ROOT_MISSING|{root}", file=sys.stderr)
            continue
        for folder in root.rglob("*"):
            if not folder.is_dir():
                continue
            folders_scanned += 1
            try:
                changes, failures, missing_sources = fix_folder(folder)
            except Exception as exc:
                copy_failures.append((None, folder, repr(exc)))
                print(f"COPY_SCAN_FAIL|{folder}|{exc}", file=sys.stderr)
                continue
            if changes or failures or missing_sources:
                strm_folders += 1
            copy_needed += len(changes) + len(failures) + len(missing_sources)
            for src, dst in changes:
                copy_success += 1
                print(f"COPY_OK|{src}|{dst}")
            for src, dst, reason in failures:
                copy_failures.append((src, dst, reason))
                print(f"COPY_FAIL|{src or '-'}|{dst}|{reason}", file=sys.stderr)
            copy_missing_sources.extend(missing_sources)
    mode = os.environ.get("FIX_REFRESH_MODE", "missing")
    refresh_checked, refresh_needed, refresh_success, refresh_failures = refresh_emby_missing_or_full(full=(mode == "full"))
    print(
        "SUMMARY|image_metadata|"
        f"roots={len(roots)}|folders_scanned={folders_scanned}|strm_folders={strm_folders}|"
        f"copy_needed={copy_needed}|copy_success={copy_success}|copy_missing_source={len(copy_missing_sources)}|copy_failed={len(copy_failures)}|"
        f"refresh_checked={refresh_checked}|refresh_needed={refresh_needed}|refresh_success={refresh_success}|refresh_failed={len(refresh_failures)}|mode={mode}"
    )
    if copy_missing_sources:
        print("MISSING_SOURCE|copy|showing_first=100")
        for src, dst, reason in copy_missing_sources[:100]:
            print(f"MISSING_SOURCE|copy|dst={dst}|reason={reason}")
        if len(copy_missing_sources) > 100:
            print(f"MISSING_SOURCE|copy|remaining={len(copy_missing_sources) - 100}")
    if copy_failures:
        print("FAILURES|copy")
        for src, dst, reason in copy_failures:
            print(f"FAIL|copy|src={src or '-'}|dst={dst}|reason={reason}")
    if refresh_failures:
        print("FAILURES|refresh")
        for item_id, path, reason in refresh_failures:
            print(f"FAIL|refresh|item={item_id}|path={path}|reason={reason}")
    print(f"changed={copy_success} refreshed={refresh_success} missing_source={len(copy_missing_sources)} failed={len(copy_failures) + len(refresh_failures)} mode={mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x "${SCRIPT}"

cat >"${SERVICE}" <<EOF
[Unit]
Description=Fill missing Emby STRM artwork and metadata
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ${SCRIPT}
EOF

cat >"${TIMER}" <<'EOF'
[Unit]
Description=Run STRM artwork and metadata fixer periodically

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true
Unit=emby-fix-strm-images.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now emby-fix-strm-images.timer
systemctl start emby-fix-strm-images.service || true
systemctl --no-pager --full status emby-fix-strm-images.timer || true
echo "Emby STRM 图片补齐器已安装。"
