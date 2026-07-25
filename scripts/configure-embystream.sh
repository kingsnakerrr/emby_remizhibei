#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="/root/docker-compose/embystream"
PRIVATE_ENV="${TARGET}/.env.private"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "${REPO_DIR}/scripts/render-embystream-config.py" \
  "${PRIVATE_ENV}" \
  "${TARGET}/config/config.toml.example" \
  "${TARGET}/config/config.toml"

if [[ ! -s "${TARGET}/config/ssl/ssl-cert" ||
      ! -s "${TARGET}/config/ssl/ssl-key" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -subj "/CN=localhost" \
    -keyout "${TARGET}/config/ssl/ssl-key" \
    -out "${TARGET}/config/ssl/ssl-cert"
  chmod 0600 "${TARGET}/config/ssl/ssl-key"
fi

if command -v nginx >/dev/null 2>&1; then
  install -m 0644 "${REPO_DIR}/nginx/embystream-backend.conf" \
    /etc/nginx/conf.d/embystream-backend.conf
  nginx -t
  systemctl reload nginx
fi

started_at="$(date --iso-8601=seconds)"
systemctl enable embystream.service
systemctl restart embystream.service
sleep 3

if ! systemctl is-active --quiet embystream.service; then
  echo "EmbyStream 启动失败，请检查以下状态和日志。"
  systemctl --no-pager --full status embystream.service || true
  exit 1
fi

refresh_due_count="$(
  journalctl -u embystream.service --since "${started_at}" --no-pager |
    grep -c 'google_drive_refresh_scheduler_due' || true
)"
if (( refresh_due_count >= 20 )); then
  echo "检测到 EmbyStream Google Token 预刷新调度器高频死循环（${refresh_due_count} 次/约3秒）。"
  echo "这是 EmbyStream v0.0.43 的调度异常，不是 OAuth 授权失败，也不是服务器入侵。"
  systemctl stop embystream.service
  echo "已自动停止 EmbyStream，避免持续占满 CPU 和写爆日志；CD2/Emby 8096 主线路不受影响。"
  exit 1
fi

if journalctl -u embystream.service --since "${started_at}" --no-pager |
    grep -q 'google_drive_refresh_failed'; then
  echo "EmbyStream 已启动，但 Google OAuth 刷新失败。"
  journalctl -u embystream.service --since "${started_at}" --no-pager |
    grep -A 4 'google_drive_refresh_failed' | head -n 8
  systemctl stop embystream.service
  echo "已停止 EmbyStream，避免无效 OAuth 凭据导致高频重试。"
  echo "请使用同一组 Google Client ID/Secret 重新生成 Refresh Token。"
  exit 1
fi

systemctl --no-pager --full status embystream.service

