#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${REPO_DIR}/compose/emby-tg-notifier"
TARGET="/root/docker-compose/emby-tg-notifier"
NGINX_SITE="${EMBY_TG_NGINX_SITE:-/etc/nginx/sites-available/emby-hdz-180o.conf}"
DOMAIN_NAME="${EMBY_TG_DOMAIN:-hdz.180o.222321.xyz}"
PUBLIC_PATH="${EMBY_TG_PUBLIC_PATH:-/tg/}"
LOCAL_PORT="${EMBY_TG_LOCAL_PORT:-8787}"

if [[ ! -f "${SOURCE}/docker-compose.yml" ]]; then
  echo "找不到 ${SOURCE}/docker-compose.yml"
  exit 1
fi

install -d -m 0755 "${TARGET}" "${TARGET}/app" "${TARGET}/app/templates" "${TARGET}/data"
install -m 0644 "${SOURCE}/docker-compose.yml" "${TARGET}/docker-compose.yml"
install -m 0644 "${SOURCE}/Dockerfile" "${TARGET}/Dockerfile"
install -m 0644 "${SOURCE}/requirements.txt" "${TARGET}/requirements.txt"
install -m 0644 "${SOURCE}/README.md" "${TARGET}/README.md"
install -m 0644 "${SOURCE}/app/main.py" "${TARGET}/app/main.py"
install -m 0644 "${SOURCE}/app/templates/index.html" "${TARGET}/app/templates/index.html"
install -m 0644 "${SOURCE}/app/templates/login.html" "${TARGET}/app/templates/login.html"

cd "${TARGET}"
docker compose up -d --build

if [[ -f "${NGINX_SITE}" ]]; then
  python3 - "${NGINX_SITE}" "${PUBLIC_PATH}" "${LOCAL_PORT}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

site = Path(sys.argv[1])
public_path = sys.argv[2]
local_port = sys.argv[3]
text = site.read_text(encoding="utf-8", errors="replace")
if not public_path.startswith("/"):
    public_path = "/" + public_path
if not public_path.endswith("/"):
    public_path += "/"
marker = f"location {public_path}"

block = f"""
    location = {public_path.rstrip("/")} {{ return 301 {public_path}; }}
    location ^~ {public_path} {{
        proxy_pass http://127.0.0.1:{local_port}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Prefix {public_path.rstrip("/")};
        proxy_redirect / {public_path};
        sub_filter_once off;
        sub_filter_types text/html text/css application/javascript text/javascript application/json;
        sub_filter 'href="/' 'href="{public_path}';
        sub_filter "href='/" "href='{public_path}";
        sub_filter 'action="/' 'action="{public_path}';
        sub_filter "action='/" "action='{public_path}";
        sub_filter 'fetch(`/' 'fetch(`{public_path}';
        sub_filter 'fetch("/' 'fetch("{public_path}';
        sub_filter "fetch('/" "fetch('{public_path}";
        sub_filter 'window.location.href="/' 'window.location.href="{public_path}';
    }}
"""

if marker not in text:
    server_marker = "    location / {"
    idx = text.find(server_marker)
    if idx == -1:
        raise SystemExit(f"cannot find main server location marker in {site}")
    text = text[:idx] + block + "\n" + text[idx:]
    site.write_text(text, encoding="utf-8")
PY
  nginx -t
  systemctl reload nginx
fi

docker ps --filter name=emby-tg-notifier --format "{{.Names}} {{.Status}} {{.Ports}}"
echo "Emby Telegram 通知已安装： https://${DOMAIN_NAME}${PUBLIC_PATH}"
echo "初始账号密码：admin / admin"
