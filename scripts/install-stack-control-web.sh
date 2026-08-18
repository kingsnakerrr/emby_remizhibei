#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/root/docker-compose/stack-control"
SERVICE="/etc/systemd/system/emby-stack-control.service"
NGINX_SITE="${STACK_CONTROL_NGINX_SITE:-/etc/nginx/sites-available/emby-hdz-180o.conf}"
PUBLIC_PATH="${STACK_CONTROL_PUBLIC_PATH:-/control/}"
HOST="${STACK_CONTROL_HOST:-127.0.0.1}"
PORT="${STACK_CONTROL_PORT:-6011}"

case "${1:-install}" in
  install|status|uninstall) ;;
  *)
    echo "用法: $0 [install|status|uninstall]"
    exit 2
    ;;
esac

if [[ "${1:-install}" == "status" ]]; then
  systemctl --no-pager --full status emby-stack-control.service || true
  exit 0
fi

if [[ "${1:-install}" == "uninstall" ]]; then
  systemctl disable --now emby-stack-control.service 2>/dev/null || true
  rm -f "${SERVICE}"
  systemctl daemon-reload
  echo "Emby Stack Control 已卸载，保留配置目录：${TARGET}"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-flask python3-werkzeug nginx

install -d -m 0700 "${TARGET}"
install -m 0755 "${REPO_DIR}/scripts/stack-control-web.py" "${TARGET}/app.py"
install -m 0644 "${REPO_DIR}/systemd/emby-stack-control.service" "${SERVICE}"
sed -i \
  -e "s#--host 127.0.0.1#--host ${HOST}#" \
  -e "s#--port 6011#--port ${PORT}#" \
  "${SERVICE}"

/usr/bin/python3 "${TARGET}/app.py" --init

if [[ -f "${NGINX_SITE}" ]] && [[ -n "${PUBLIC_PATH}" ]]; then
  python3 - "${NGINX_SITE}" "${PUBLIC_PATH}" "${HOST}" "${PORT}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

site = Path(sys.argv[1])
public_path = sys.argv[2]
host = sys.argv[3]
port = sys.argv[4]

text = site.read_text(encoding="utf-8", errors="replace")
if not public_path.startswith("/"):
    public_path = "/" + public_path
if not public_path.endswith("/"):
    public_path += "/"

block = f"""
    location = {public_path.rstrip("/")} {{ return 301 {public_path}; }}
    location {public_path} {{
        proxy_pass http://{host}:{port}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix {public_path.rstrip("/")};
        proxy_redirect / {public_path};
        sub_filter_once off;
        sub_filter_types text/html text/css application/javascript text/javascript application/json;
        sub_filter 'href="/' 'href="{public_path}';
        sub_filter "href='/" "href='{public_path}";
        sub_filter 'action="/' 'action="{public_path}';
        sub_filter "action='/" "action='{public_path}";
    }}
"""

if f"location {public_path}" not in text:
    marker = "    location / {"
    idx = text.rfind(marker)
    if idx == -1:
        raise SystemExit(f"cannot find nginx location marker in {site}")
    text = text[:idx] + block + "\n" + text[idx:]
    site.write_text(text, encoding="utf-8")
PY
  nginx -t
  systemctl reload nginx
fi

systemctl daemon-reload
systemctl enable --now emby-stack-control.service
systemctl --no-pager --full status emby-stack-control.service | sed -n '1,18p'

echo "Emby Stack Control 已安装。"
echo "本机地址：http://${HOST}:${PORT}"
if [[ -n "${PUBLIC_PATH}" ]]; then
  echo "HTTPS 路径：${PUBLIC_PATH}"
fi
echo "初始账号密码：${TARGET}/credentials.txt"
