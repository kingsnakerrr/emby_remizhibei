#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="/root/metadata-fix-backups"
TARGET="/root/docker-compose/emby-tools"
TOOL="${TARGET}/fix-strm-chinese-titles.py"
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

cat >"${TOOL}" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


DB = Path("/root/docker-compose/emby/config/data/library.db")
BACKUP_DIR = Path("/root/metadata-fix-backups")
CONFIG = Path("/root/docker-compose/emby-tools/strm-fixer-roots.json")
DEFAULT_ROOTS = [
    Path("/home/symedia_gd/movies"),
    Path("/home/symedia_rclone_zero/movies"),
]
CJK = re.compile(r"[\u4e00-\u9fff]")
FOLDER_RE = re.compile(r"(.+?) \(\d{4}\) \{tmdb-\d+\}$")
TITLE_RE = re.compile(r"(<title>)(.*?)(</title>)", re.S | re.I)
SORT_RE = re.compile(r"(<sorttitle>)(.*?)(</sorttitle>)", re.S | re.I)


def configured_roots() -> list[Path]:
    try:
        data = json.loads(CONFIG.read_text("utf-8"))
        roots = [Path(value) for value in data.get("title_roots", []) if isinstance(value, str)]
        roots = [root for root in roots if str(root).startswith("/home/")]
        return roots or DEFAULT_ROOTS
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


def fix_nfo(path: str, title: str, dry_run: bool) -> bool:
    nfo = Path(path).with_suffix(".nfo")
    if not nfo.exists():
        return False
    data = nfo.read_text("utf-8", errors="replace")
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
        nfo.write_text(data, "utf-8")
    return changed


def find_changes(cur: sqlite3.Cursor, dry_run: bool) -> tuple[list[tuple[int, str, str, str]], int]:
    cur.execute(
        "select Id, Name, SortName, OriginalTitle, Path from MediaItems "
        "where Path like '/home/%'"
    )
    changes: list[tuple[int, str, str, str]] = []
    nfo_changes = 0
    for item_id, name, sort_name, original_title, path in cur.fetchall():
        if not path or not path.endswith(".strm"):
            continue
        title = title_from_path(path)
        if not title:
            continue
        current = name or ""
        if current == title or CJK.search(current):
            continue
        changes.append((item_id, current, title, path))
        nfo_changes += int(fix_nfo(path, title, dry_run))
    return changes, nfo_changes


def main() -> int:
    dry_run = os.environ.get("DRY_RUN") == "1"
    if not DB.exists():
        raise SystemExit(f"missing db: {DB}")

    con = sqlite3.connect(DB)
    cur = con.cursor()
    changes, nfo_changes = find_changes(cur, dry_run)

    if dry_run:
        print(f"dry_run=1 changed={len(changes)} nfo_changed={nfo_changes}")
        for item_id, old_name, title, path in changes:
            print(f"WOULD_FIX|{item_id}|{old_name}|{title}|{path}")
        con.close()
        return 0

    if not changes:
        print("changed=0 nfo_changed=0")
        con.close()
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"library-before-title-fix-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(DB, backup)
    for item_id, old_name, title, path in changes:
        cur.execute(
            "update MediaItems set Name=?, SortName=? where Id=?",
            (title, title, item_id),
        )
        try:
            cur.execute("update fts_search9 set Name=? where rowid=?", (title, item_id))
        except sqlite3.DatabaseError:
            pass
    con.commit()
    con.execute("pragma wal_checkpoint(TRUNCATE)")
    con.close()

    print(f"backup={backup}")
    print(f"changed={len(changes)} nfo_changed={nfo_changes}")
    for item_id, old_name, title, path in changes:
        print(f"FIX|{item_id}|{old_name}|{title}|{path}")
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
  pending="$(DRY_RUN=1 python3 "${TOOL}" | sed -n 's/^dry_run=1 changed=\([0-9]\+\).*/\1/p' | tail -1)"
  if [[ "${pending:-0}" == "0" ]]; then
    echo "没有发现需要修正的英文标题，不重启 Emby。"
    exit 0
  fi
  echo "发现 ${pending} 个英文标题，停止 Emby 后修复……"
  docker stop emby >/dev/null
  python3 "${TOOL}"
  docker start emby >/dev/null
  echo "已重启 Emby。若客户端仍显示旧标题，刷新页面或清理客户端缓存。"
  exit 0
fi

cat >"${SERVICE}" <<EOF
[Unit]
Description=Fix English titles in Emby STRM libraries
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=${SELF} apply
EOF

cat >"${TIMER}" <<'EOF'
[Unit]
Description=Run Emby STRM Chinese title fixer periodically

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
