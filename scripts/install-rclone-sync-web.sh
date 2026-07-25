#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/root/docker-compose/rclone-sync"
INITIAL_USER="${RCLONE_SYNC_INITIAL_USER:-admin}"
INITIAL_PASSWORD="${RCLONE_SYNC_INITIAL_PASSWORD:-admin}"
EXISTING_SETTINGS=0
if [[ -s "${TARGET}/settings.json" ]]; then
  EXISTING_SETTINGS=1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y rclone python3-flask

install -d -m 0700 \
  "${TARGET}" \
  "${TARGET}/logs" \
  "${TARGET}/data" \
  /root/.config/rclone
install -m 0755 "${REPO_DIR}/scripts/rclone-sync-web.py" \
  "${TARGET}/app.py"

RCLONE_SYNC_INITIAL_USER="${INITIAL_USER}" \
RCLONE_SYNC_INITIAL_PASSWORD="${INITIAL_PASSWORD}" \
  /usr/bin/python3 "${TARGET}/app.py" --init

install -m 0644 "${REPO_DIR}/systemd/rclone-sync-web.service" \
  /etc/systemd/system/rclone-sync-web.service
systemctl daemon-reload
systemctl enable --now rclone-sync-web.service

echo "Rclone 和同步控制台已安装。"
echo "控制台：http://VPS-IP:6096"
if (( EXISTING_SETTINGS )); then
  echo "检测到已有控制台配置，保留原账号、密码和同步任务。"
elif [[ "${INITIAL_USER}" != "admin" || "${INITIAL_PASSWORD}" != "admin" ]]; then
  echo "本次已使用安装时输入的自定义账号密码。"
else
  echo "默认账号：admin"
  echo "默认密码：admin"
  echo "首次登录必须修改默认密码后才能使用控制台。"
fi
echo "请在网页上传 /root/.config/rclone/rclone.conf，选择团队盘目录和本地目录。"
