#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

ACTION="${1:-install}"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="/root/docker-compose/symedia/config/archive_retry"
TARGET="${TARGET_DIR}/retry.py"
UNIT="/etc/systemd/system/symedia-archive-retry.service"

case "${ACTION}" in
  install|status|run|uninstall) ;;
  *) echo "用法: $0 [install|status|run|uninstall]"; exit 2 ;;
esac

if [[ "${ACTION}" == "uninstall" ]]; then
  systemctl disable --now symedia-archive-retry.service 2>/dev/null || true
  rm -f "${UNIT}"
  systemctl daemon-reload
  echo "Symedia 归档重试服务已卸载，状态数据库和脚本已保留。"
  exit 0
fi

if [[ "${ACTION}" == "status" ]]; then
  systemctl --no-pager --full status symedia-archive-retry.service || true
  exit 0
fi

install -d -m 0755 "${TARGET_DIR}"
install -m 0755 "${REPO_DIR}/scripts/symedia-archive-retry.py" "${TARGET}"

config="/root/docker-compose/symedia/config/config.yaml"
if [[ -s "${config}" ]]; then
  cp -a "${config}" "${config}.before-archive-retry-$(date +%Y%m%d-%H%M%S)"
  python3 - "${config}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text("utf-8")
text = text.replace("message_listener_enabled: true", "message_listener_enabled: false")
text = text.replace("/GoogleDrive/zero/media/symedia_GD", "/GoogleDrive/zero/media/symedia_gd")
path.write_text(text, "utf-8")
PY
fi

cat >"${UNIT}" <<EOF
[Unit]
Description=Conservative retry of failed Symedia CD2 archive transfers
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/docker exec symedia python3 -u /app/config/archive_retry/retry.py --execute
Restart=on-failure
RestartSec=60
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now symedia-archive-retry.service

if [[ "${ACTION}" == "run" ]]; then
  docker exec symedia python3 -u /app/config/archive_retry/retry.py --execute --once
else
  echo "Symedia 归档自动重试已安装；每60秒检查，最多重试3次。"
fi
