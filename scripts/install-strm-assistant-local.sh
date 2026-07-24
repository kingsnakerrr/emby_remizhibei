#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

SOURCE_DIR="${1:-/root/strm-assistant-import}"
PLUGIN_ROOT="/root/docker-compose/emby/config/plugins"
CONFIG_ROOT="${PLUGIN_ROOT}/configurations"
DLL="${SOURCE_DIR}/StrmAssistantPro.dll"
SOURCE_CONFIG="${SOURCE_DIR}/configurations"
IN_PLACE=false

if [[ "$(readlink -f -- "${SOURCE_DIR}")" == \
      "$(readlink -f -- "${PLUGIN_ROOT}")" ]]; then
  IN_PLACE=true
fi

if [[ ! -s "${DLL}" ]]; then
  echo "缺少 ${DLL}"
  exit 2
fi
if [[ ! -d "${SOURCE_CONFIG}" ]]; then
  echo "缺少授权文件目录 ${SOURCE_CONFIG}"
  exit 2
fi

mapfile -t authorization_files < <(
  find "${SOURCE_CONFIG}" -maxdepth 1 -type f ! -name '*.json' -print
)
if [[ ${#authorization_files[@]} -eq 0 ]]; then
  echo "${SOURCE_CONFIG} 中没有非 JSON 授权文件。"
  exit 2
fi

backup_dir="/root/docker-compose/emby/config/backups/strm-assistant-import-$(date +%Y%m%d-%H%M%S)"
install -d -m 0755 "${CONFIG_ROOT}" "${backup_dir}"

docker stop emby >/dev/null 2>&1 || true

if [[ -f "${PLUGIN_ROOT}/StrmAssistantPro.dll" ]]; then
  cp -a "${PLUGIN_ROOT}/StrmAssistantPro.dll" "${backup_dir}/"
fi

if [[ "${IN_PLACE}" == "true" ]]; then
  chmod 0644 "${PLUGIN_ROOT}/StrmAssistantPro.dll"
else
  install -m 0644 "${DLL}" "${PLUGIN_ROOT}/StrmAssistantPro.dll"
fi
for source_path in "${authorization_files[@]}"; do
  filename="$(basename -- "${source_path}")"
  target_path="${CONFIG_ROOT}/${filename}"
  if [[ "$(readlink -f -- "${source_path}")" == \
        "$(readlink -f -- "${target_path}")" ]]; then
    chmod 0600 "${target_path}"
  else
    install -m 0600 "${source_path}" "${target_path}"
  fi
done

chown -R root:root "${PLUGIN_ROOT}"
docker start emby >/dev/null

echo "等待 Emby 加载神医助手……"
for _ in $(seq 1 30); do
  if docker logs --since 2m emby 2>&1 |
    grep -qiE 'StrmAssistant|Strm Assistant'; then
    echo "Emby 日志已检测到神医助手。"
    exit 0
  fi
  sleep 2
done

echo "插件已复制并重启 Emby，但日志中暂未检测到加载记录。"
echo "请进入 Emby 插件页面确认授权状态。"
