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

systemctl enable --now embystream.service
systemctl --no-pager --full status embystream.service

