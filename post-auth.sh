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
  play-prewarm)
    "${REPO_DIR}/scripts/install-emby-play-prewarm.sh"
    ;;
  strm-image-fixer)
    "${REPO_DIR}/scripts/install-emby-strm-image-fixer.sh"
    ;;
  strm-title-fixer)
    "${REPO_DIR}/scripts/fix-emby-strm-chinese-titles.sh" "${2:-install}"
    ;;
  stack-control)
    "${REPO_DIR}/scripts/install-stack-control-web.sh" "${2:-install}"
    ;;
  symedia)
    "${REPO_DIR}/scripts/audit-symedia.sh"
    ;;
  home-media-backup)
    "${REPO_DIR}/scripts/install-home-media-backup.sh" "${2:-}"
    ;;
  *)
    echo "Usage: $0 {cd2|strm-assistant|play-prewarm|strm-image-fixer|strm-title-fixer|stack-control|symedia|home-media-backup}"
    exit 2
    ;;
esac
