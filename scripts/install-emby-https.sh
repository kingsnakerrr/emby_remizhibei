#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。" >&2
  exit 1
fi

ACTION="${1:-install}"
DOMAIN="${EMBY_DOMAIN:-emby.rmzb.de}"
OLD_DOMAIN="${OLD_EMBY_DOMAIN:-}"
COMPOSE_FILE="${EMBY_COMPOSE_FILE:-/root/docker-compose/emby/docker-compose.yml}"
WEBROOT="/var/www/letsencrypt"

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || [[ "$DOMAIN" != *.* ]]; then
  echo "无效域名：${DOMAIN}" >&2
  exit 2
fi

case "$ACTION" in
  status)
    nginx -t
    curl -fsS --max-time 10 "https://${DOMAIN}/emby/System/Info/Public" >/dev/null
    ss -lnt | grep -qE '127\.0\.0\.1:8096[[:space:]]'
    certbot certificates | grep -F -A2 "Certificate Name: ${DOMAIN}"
    echo "Emby HTTPS 和本机 8096 状态正常。"
    exit 0
    ;;
  install) ;;
  *) echo "用法: EMBY_DOMAIN=域名 OLD_EMBY_DOMAIN=旧域名 $0 [install|status]" >&2; exit 2 ;;
esac

[[ -s "$COMPOSE_FILE" ]] || { echo "找不到 ${COMPOSE_FILE}" >&2; exit 1; }
apt-get update
apt-get install -y nginx certbot curl

backup_dir="/root/emby-https-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "$backup_dir/nginx-conf.d"
cp -a "$COMPOSE_FILE" "$backup_dir/docker-compose.yml"
cp -a /etc/nginx/conf.d/. "$backup_dir/nginx-conf.d/"

install -d -m 0755 "$WEBROOT/.well-known/acme-challenge"
cat >"/etc/nginx/conf.d/00-emby-rmzb-acme.conf" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location ^~ /.well-known/acme-challenge/ {
        root ${WEBROOT};
        default_type text/plain;
    }
    location / { return 301 https://${DOMAIN}\$request_uri; }
}
EOF
nginx -t
systemctl reload nginx

certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN" --cert-name "$DOMAIN" \
  --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring

cat >"/etc/nginx/conf.d/10-emby-rmzb-https.conf" <<EOF
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${DOMAIN};
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache shared:EmbySSL:10m;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    client_max_body_size 0;
    proxy_buffering off;
    proxy_request_buffering off;
    location / {
        proxy_pass http://127.0.0.1:8096;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
EOF

if [[ -n "$OLD_DOMAIN" ]]; then
  if [[ ! "$OLD_DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || [[ "$OLD_DOMAIN" != *.* ]]; then
    echo "无效旧域名：${OLD_DOMAIN}" >&2
    exit 2
  fi
  if [[ -s "/etc/letsencrypt/live/${OLD_DOMAIN}/fullchain.pem" ]]; then
    cat >"/etc/nginx/conf.d/00-hdz-acme.conf" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${OLD_DOMAIN};
    location ^~ /.well-known/acme-challenge/ {
        root ${WEBROOT};
        default_type text/plain;
    }
    location / { return 301 https://${DOMAIN}\$request_uri; }
}
EOF
    cat >"/etc/nginx/conf.d/10-emby-hdz-https.conf" <<EOF
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${OLD_DOMAIN};
    ssl_certificate /etc/letsencrypt/live/${OLD_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${OLD_DOMAIN}/privkey.pem;
    return 301 https://${DOMAIN}\$request_uri;
}
EOF
  fi
fi

if grep -q '"8096:8096"' "$COMPOSE_FILE"; then
  sed -i 's|"8096:8096"|"127.0.0.1:8096:8096"|' "$COMPOSE_FILE"
fi
grep -q '"127.0.0.1:8096:8096"' "$COMPOSE_FILE" || {
  echo "没有找到可安全修改的 8096 端口映射，已停止。" >&2
  exit 1
}

nginx -t
systemctl reload nginx
docker compose -f "$COMPOSE_FILE" config --quiet
docker compose -f "$COMPOSE_FILE" up -d

for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:8096/emby/System/Info/Public >/dev/null; then
    echo "完成：https://${DOMAIN}；公网 8096 已改为仅本机监听。"
    echo "回滚备份：${backup_dir}"
    exit 0
  fi
  sleep 2
done
echo "Emby 重启后未在 60 秒内就绪，请检查 docker logs emby。" >&2
exit 1
