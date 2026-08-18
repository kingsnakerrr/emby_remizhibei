#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Please run as root or with sudo."
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-}"

case "${ACTION}" in
  cd2)
    python3 "${REPO_DIR}/scripts/apply-cd2-settings.py"
    ;;
  strm-assistant)
    python3 "${REPO_DIR}/scripts/apply-strm-assistant-settings.py"
    ;;
  embystream)
    "${REPO_DIR}/scripts/configure-embystream.sh"
    ;;
  play-prewarm)
    "${REPO_DIR}/scripts/install-emby-play-prewarm.sh"
    ;;
  strm-image-fixer)
    "${REPO_DIR}/scripts/install-emby-strm-image-fixer.sh"
    ;;
  symedia)
    "${REPO_DIR}/scripts/audit-symedia.sh"
    ;;
  home-media-backup)
    "${REPO_DIR}/scripts/install-home-media-backup.sh" "${2:-}"
    ;;
  *)
    echo "Usage: $0 {cd2|strm-assistant|embystream|play-prewarm|strm-image-fixer|symedia|home-media-backup}"
    exit 2
    ;;
esac
