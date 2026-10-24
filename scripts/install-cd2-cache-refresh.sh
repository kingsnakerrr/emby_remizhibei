#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

ACTION="${1:-install}"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/root/docker-compose/symedia/cache-refresh"
RUNNER="${TARGET}/run.sh"

case "${ACTION}" in
  install|status|run|uninstall) ;;
  *) echo "用法: $0 [install|status|run|uninstall]"; exit 2 ;;
esac

write_crontab() {
  local temporary
  temporary="$(mktemp)"
  crontab -l 2>/dev/null |
    sed '/# BEGIN CD2 CACHE REFRESH/,/# END CD2 CACHE REFRESH/d' >"${temporary}" || true
  if [[ "$1" == "add" ]]; then
    cat >>"${temporary}" <<EOF
# BEGIN CD2 CACHE REFRESH
2,17,32,47 * * * * ${RUNNER} shallow
# END CD2 CACHE REFRESH
EOF
  fi
  crontab "${temporary}"
  rm -f "${temporary}"
}

if [[ "${ACTION}" == "uninstall" ]]; then
  write_crontab remove
  echo "CD2 删除缓存刷新计划已卸载，脚本和日志已保留。"
  exit 0
fi

if [[ "${ACTION}" == "status" ]]; then
  crontab -l 2>/dev/null | sed -n '/# BEGIN CD2 CACHE REFRESH/,/# END CD2 CACHE REFRESH/p'
  tail -30 "${TARGET}/logs/refresh-$(date +%F).log" 2>/dev/null || true
  exit 0
fi

install -d -m 0755 "${TARGET}/logs"
install -m 0700 "${REPO_DIR}/scripts/refresh-cd2-cache.py" "${TARGET}/refresh_cd2_cache.py"
cat >"${RUNNER}" <<'EOF'
#!/bin/sh
set -eu
MODE="${1:-shallow}"
BASE_DIR="/root/docker-compose/symedia/cache-refresh"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"
find "$LOG_DIR" -type f -name '*.log' -mtime +14 -delete
exec /usr/bin/flock -n /run/cd2-cache-refresh.lock \
  /bin/sh -c "/usr/bin/docker exec -i symedia python3 - '$MODE' < '$BASE_DIR/refresh_cd2_cache.py'" \
  >> "$LOG_DIR/refresh-$(date +%F).log" 2>&1
EOF
chmod 0700 "${RUNNER}"
write_crontab add

if [[ "${ACTION}" == "run" ]]; then
  "${RUNNER}" shallow
else
  echo "CD2 删除缓存刷新已安装；每小时运行4次，日志保留14天。"
fi
