#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Please run as root or with sudo."
  exit 1
fi

REMOTE_TARGET="${1:-${HOME_MEDIA_BACKUP_REMOTE:-}}"
CRON_SCHEDULE="${HOME_MEDIA_BACKUP_CRON:-*/30 * * * *}"
INSTALL_PATH="/root/scripts/rclone-home-backup.sh"
LOG_DIR="/var/log/rclone-home-backup"

if [[ -z "${REMOTE_TARGET}" ]]; then
  cat >&2 <<'EOF'
Usage:
  sudo ./scripts/install-home-media-backup.sh REMOTE:/media

Example:
  sudo ./scripts/install-home-media-backup.sh snake_zhangtianlong321:/media

This installs a file-first rclone copy job for:
  /home/symedia_gd  -> REMOTE:/media/symedia_gd
  /home/symedia_jav -> REMOTE:/media/symedia_jav
EOF
  exit 2
fi

if ! command -v rclone >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y rclone
fi

if ! rclone listremotes | grep -Fxq "${REMOTE_TARGET%%:*}:"; then
  echo "rclone remote not found: ${REMOTE_TARGET%%:*}:"
  echo "Run 'rclone config' first or copy a valid /root/.config/rclone/rclone.conf."
  exit 1
fi

install -d -m 0755 /root/scripts "${LOG_DIR}"
if [[ -f "${INSTALL_PATH}" ]]; then
  cp -a "${INSTALL_PATH}" "${INSTALL_PATH}.bak.$(date +%F-%H%M%S)"
fi

cat >"${INSTALL_PATH}" <<EOF
#!/usr/bin/env bash
set -u

LOG_DIR="${LOG_DIR}"
LOG_FILE="\${LOG_DIR}/backup-\$(date +%F).log"
RCLONE="/usr/bin/rclone"
REMOTE="${REMOTE_TARGET%/}"
COMMON_OPTS=(
  --transfers 24
  --checkers 12
  --multi-thread-streams 4
  --buffer-size 16M
  --log-level INFO
  --log-file "\${LOG_FILE}"
)

mkdir -p "\${LOG_DIR}"

{
  echo "===== \$(date '+%F %T') start home media backup ====="

  if [[ -d /home/symedia_gd ]]; then
    "\${RCLONE}" copy /home/symedia_gd "\${REMOTE}/symedia_gd" "\${COMMON_OPTS[@]}"
  fi

  if [[ -d /home/symedia_jav ]]; then
    "\${RCLONE}" copy /home/symedia_jav "\${REMOTE}/symedia_jav" "\${COMMON_OPTS[@]}"
  fi

  echo "===== \$(date '+%F %T') done home media backup ====="
} >>"\${LOG_FILE}" 2>&1
EOF

chmod 0755 "${INSTALL_PATH}"

tmp_cron="$(mktemp)"
crontab -l 2>/dev/null |
  grep -vF "${INSTALL_PATH}" >"${tmp_cron}" || true
printf '%s %s >/dev/null 2>&1\n' "${CRON_SCHEDULE}" "${INSTALL_PATH}" >>"${tmp_cron}"
crontab "${tmp_cron}"
rm -f "${tmp_cron}"

echo "Installed: ${INSTALL_PATH}"
echo "Remote target: ${REMOTE_TARGET%/}"
echo "Cron: ${CRON_SCHEDULE}"
echo "Log dir: ${LOG_DIR}"
echo
echo "Run once now:"
echo "  sudo ${INSTALL_PATH}"
echo
echo "Check progress:"
echo "  tail -f ${LOG_DIR}/backup-\$(date +%F).log"
