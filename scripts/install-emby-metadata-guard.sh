#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

ACTION="${1:-install}"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="/usr/local/sbin/emby-metadata-guard.py"
SERVICE="/etc/systemd/system/emby-metadata-guard.service"
TIMER="/etc/systemd/system/emby-metadata-guard.timer"

case "${ACTION}" in
  install|status|run|uninstall) ;;
  *) echo "用法: $0 [install|status|run|uninstall]"; exit 2 ;;
esac

if [[ "${ACTION}" == "uninstall" ]]; then
  systemctl disable --now emby-metadata-guard.timer 2>/dev/null || true
  rm -f "${SERVICE}" "${TIMER}"
  systemctl daemon-reload
  echo "Emby 元数据守护已卸载，工具和NFO备份已保留。"
  exit 0
fi

if [[ "${ACTION}" == "status" ]]; then
  systemctl --no-pager --full status emby-metadata-guard.timer || true
  systemctl --no-pager --full status emby-metadata-guard.service || true
  exit 0
fi

install -m 0755 "${REPO_DIR}/scripts/emby-metadata-guard.py" "${TOOL}"

cat >"${SERVICE}" <<EOF
[Unit]
Description=Normalize Emby Chinese NFO titles and audit metadata
After=network-online.target docker.service

[Service]
Type=oneshot
EnvironmentFile=-/etc/emby-metadata-guard.conf
ExecStart=${TOOL}
EOF

cat >"${TIMER}" <<'EOF'
[Unit]
Description=Run Emby metadata guard periodically

[Timer]
OnBootSec=10min
OnUnitActiveSec=15min
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now emby-metadata-guard.timer
if [[ "${ACTION}" == "run" ]]; then
  systemctl start emby-metadata-guard.service
  systemctl --no-pager --full status emby-metadata-guard.service
else
  echo "Emby 元数据守护已安装；默认从 Emby 本地认证数据库读取活动令牌。"
fi
