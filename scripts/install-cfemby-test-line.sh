#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。" >&2
  exit 1
fi

ACTION="${1:-install}"
DOMAIN="${CF_EMBY_DOMAIN:-cfemby.rmzb.de}"
WEBROOT="/var/www/letsencrypt"
ACME_CONF="/etc/nginx/conf.d/00-cfemby-acme.conf"
HTTPS_CONF="/etc/nginx/conf.d/10-cfemby-https.conf"

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || [[ "$DOMAIN" != *.* ]]; then
  echo "无效域名：${DOMAIN}" >&2
  exit 2
fi

case "$ACTION" in
  status)
    nginx -t
    headers="$(curl -fsSI --max-time 15 "https://${DOMAIN}")"
    grep -qi '^x-emby-line: cloudflare-test' <<<"$headers"
    grep -qi '^cf-cache-status: DYNAMIC' <<<"$headers"
    certbot certificates | grep -F -A2 "Certificate Name: ${DOMAIN}"
    echo "Cloudflare Emby测试线路正常，响应未缓存。"
    exit 0
    ;;
  install) ;;
  *) echo "用法: CF_EMBY_DOMAIN=域名 $0 [install|status]" >&2; exit 2 ;;
esac

apt-get update
apt-get install -y nginx certbot curl

backup_dir="/root/cfemby-test-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "$backup_dir/nginx-conf.d"
cp -a /etc/nginx/conf.d/. "$backup_dir/nginx-conf.d/"

install -d -m 0755 "$WEBROOT/.well-known/acme-challenge"
cat >"$ACME_CONF" <<EOF
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

cat >"$HTTPS_CONF" <<EOF
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${DOMAIN};
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache shared:CfEmbySSL:10m;
    ssl_session_tickets off;
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
        proxy_hide_header Cache-Control;
        add_header Cache-Control "private, no-store" always;
        add_header X-Emby-Line "cloudflare-test" always;
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy strict-origin-when-cross-origin always;
    }
}
EOF

nginx -t
systemctl reload nginx
curl -fsS --max-time 15 "https://${DOMAIN}/emby/System/Info/Public" >/dev/null
echo "完成：https://${DOMAIN}；正式直连线路未修改。"
echo "回滚备份：${backup_dir}"
