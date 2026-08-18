#!/usr/bin/env bash
set -Eeuo pipefail

DB="/root/docker-compose/emby/config/data/library.db"
BACKUP_DIR="/root/metadata-fix-backups"
TOOL_DIR="/root/docker-compose/emby-tools"
TOOL="${TOOL_DIR}/fix-strm-chinese-titles.py"
DRY_RUN=0

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

case "${1:-apply}" in
  apply) ;;
  dry-run) DRY_RUN=1 ;;
  *)
    echo "用法: $0 [apply|dry-run]"
    exit 2
    ;;
esac

install -d -m 0755 "${TOOL_DIR}"
install -d -m 0755 "${BACKUP_DIR}"

cat >"${TOOL}" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


DB = Path("/root/docker-compose/emby/config/data/library.db")
BACKUP_DIR = Path("/root/metadata-fix-backups")
CJK = re.compile(r"[\u4e00-\u9fff]")
FOLDER_RE = re.compile(
    r"/home/(?:symedia_rclone_zero|symedia_gd)/movies/[^/]+/"
    r"([^/]+?) \(\d{4}\) \{tmdb-\d+\}/"
)
TITLE_RE = re.compile(r"(<title>)(.*?)(</title>)", re.S | re.I)
SORT_RE = re.compile(r"(<sorttitle>)(.*?)(</sorttitle>)", re.S | re.I)


def title_from_path(path: str) -> str | None:
    match = FOLDER_RE.search(path or "")
    if not match:
        return None
    title = match.group(1).strip()
    return title if CJK.search(title) else None


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


def main() -> int:
    dry_run = os.environ.get("DRY_RUN") == "1"
    if not DB.exists():
        raise SystemExit(f"missing db: {DB}")

    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(
        "select Id, Name, SortName, OriginalTitle, Path from MediaItems "
        "where Path like '/home/symedia_rclone_zero/movies/%' "
        "or Path like '/home/symedia_gd/movies/%'"
    )
    changes = []
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

    if dry_run:
        print(f"dry_run=1 changed={len(changes)} nfo_changed={nfo_changes}")
        for item_id, old_name, title, path in changes:
            print(f"WOULD_FIX|{item_id}|{old_name}|{title}|{path}")
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

if [[ ${DRY_RUN} -eq 1 ]]; then
  DRY_RUN=1 python3 "${TOOL}"
  exit 0
fi

echo "停止 Emby，备份并修复 STRM 中文标题……"
docker stop emby >/dev/null
python3 "${TOOL}"
docker start emby >/dev/null
echo "已重启 Emby。若客户端仍显示旧标题，刷新页面或清理客户端缓存。"
