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
import shutil
import sys


CONFIG = Path("/root/docker-compose/emby-tools/strm-fixer-roots.json")
DEFAULT_ROOTS = [
    # Keep this focused on movie STRM libraries. Wider scans can be expensive
    # and may copy artwork in unrelated folders.
    Path("/home/symedia_gd/movies"),
    Path("/home/symedia_rclone_zero/movies"),
]
IMAGE_KINDS = ["poster.jpg", "fanart.jpg", "clearlogo.png"]
VIDEO_SUFFIXES = {".strm"}


def configured_roots() -> list[Path]:
    try:
        data = json.loads(CONFIG.read_text("utf-8"))
        roots = [Path(value) for value in data.get("image_roots", []) if isinstance(value, str)]
        roots = [root for root in roots if str(root).startswith("/home/")]
        return roots or DEFAULT_ROOTS
    except (OSError, json.JSONDecodeError):
        return DEFAULT_ROOTS


def safe_copy(src: Path | None, dst: Path) -> bool:
    if src is None or not src.exists() or dst.exists():
        return False
    if src.stat().st_size <= 0:
        return False
    try:
        if src.resolve() == dst.resolve():
            return False
    except OSError:
        return False
    shutil.copy2(src, dst)
    return True


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


def fix_folder(folder: Path) -> list[tuple[Path, Path]]:
    strms = [
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if not strms:
        return []

    changed: list[tuple[Path, Path]] = []
    for kind in IMAGE_KINDS:
        dst = folder / kind
        src = find_source(folder, kind)
        if safe_copy(src, dst):
            changed.append((src, dst))

    for strm in strms:
        for kind in IMAGE_KINDS:
            dst = folder / f"{strm.stem}-{kind}"
            src = find_source(folder, kind)
            if safe_copy(src, dst):
                changed.append((src, dst))

    return changed


def main() -> int:
    total = 0
    for root in configured_roots():
        if not root.exists():
            continue
        for folder in root.rglob("*"):
            if not folder.is_dir():
                continue
            try:
                changes = fix_folder(folder)
            except Exception as exc:
                print(f"ERR|{folder}|{exc}", file=sys.stderr)
                continue
            for src, dst in changes:
                total += 1
                print(f"COPY|{src}|{dst}")
    print(f"changed={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x "${SCRIPT}"

cat >"${SERVICE}" <<EOF
[Unit]
Description=Fill missing Emby STRM version artwork
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ${SCRIPT}
EOF

cat >"${TIMER}" <<'EOF'
[Unit]
Description=Run STRM artwork fixer periodically

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
