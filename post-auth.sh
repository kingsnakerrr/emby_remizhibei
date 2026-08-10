#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
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
  symedia)
    "${REPO_DIR}/scripts/audit-symedia.sh"
    ;;
  *)
    echo "用法: $0 {cd2|strm-assistant|embystream|play-prewarm|symedia}"
    exit 2
    ;;
esac