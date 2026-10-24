#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_SCRIPT="${ROOT_DIR}/scripts/legacy-refresh-new-media.sh"
TARGET_SCRIPT="/root/scripts/shuaxinyuansu.sh"
SERVICE_FILE="/etc/systemd/system/emby-refresh.service"
TIMER_FILE="/etc/systemd/system/emby-refresh.timer"

require_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
}

install_refresh() {
  require_root
  command -v python3 >/dev/null
  command -v jq >/dev/null
  install -D -m 0755 "$SOURCE_SCRIPT" "$TARGET_SCRIPT"
  cat >"$SERVICE_FILE" <<'EOF'
[Unit]
Description=Refresh metadata for recently added Emby items
After=network-online.target docker.service

[Service]
Type=oneshot
ExecStart=/root/scripts/shuaxinyuansu.sh
EOF
  cat >"$TIMER_FILE" <<'EOF'
[Unit]
Description=Run recent Emby metadata refresh every five minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now emby-refresh.timer
  echo "Installed emby-refresh.timer."
}

uninstall_refresh() {
  require_root
  systemctl disable --now emby-refresh.timer 2>/dev/null || true
  rm -f "$SERVICE_FILE" "$TIMER_FILE" "$TARGET_SCRIPT"
  systemctl daemon-reload
  echo "Removed recent-item refresh service and timer."
}

case "${1:-install}" in
  install) install_refresh ;;
  run) require_root; "$TARGET_SCRIPT" ;;
  status) systemctl status emby-refresh.timer --no-pager; systemctl status emby-refresh.service --no-pager || true ;;
  uninstall) uninstall_refresh ;;
  *) echo "Usage: $0 {install|run|status|uninstall}" >&2; exit 2 ;;
esac
