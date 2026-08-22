#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STACK_ROOT="/root/docker-compose"
CD2_DATA="${STACK_ROOT}/clouddrive2/config/cloudapidata.json"
EMBY_SYSTEM="${STACK_ROOT}/emby/config/system.xml"
PLUGIN_ROOT="${STACK_ROOT}/emby/config/plugins"
PLUGIN_DLL="${PLUGIN_ROOT}/StrmAssistantPro.dll"
PLUGIN_CONFIG="${PLUGIN_ROOT}/configurations"

pause_for_user() {
  echo
  read -r -p "$1 完成后按 Enter 继续……" _
}

ask_yes_no() {
  local prompt="$1"
  local answer
  read -r -p "${prompt} [y/N]: " answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

cd2_is_ready() {
  [[ -s "${CD2_DATA}" ]] &&
    grep -qE '"dir_name"[[:space:]]*:[[:space:]]*"/GoogleDrive"' \
      "${CD2_DATA}"
}

emby_is_initialized() {
  [[ -s "${EMBY_SYSTEM}" ]] &&
    grep -qiE '<IsStartupWizardCompleted>[[:space:]]*true' \
      "${EMBY_SYSTEM}"
}

strm_assistant_is_staged() {
  [[ -s "${PLUGIN_DLL}" ]] &&
    [[ -d "${PLUGIN_CONFIG}" ]] &&
    find "${PLUGIN_CONFIG}" -maxdepth 1 -type f ! -name '*.json' \
      -print -quit | grep -q .
}

apply_strm_assistant_optimizations() {
  if bash "${REPO_DIR}/post-auth.sh" strm-assistant; then
    return 0
  fi
  cat <<EOF

神医助手尚未生成完整配置。
请打开 Emby 后台 → 插件 → 神医助手，确认授权并点击一次“保存”。
EOF
  pause_for_user "请完成神医助手首次加载和保存。"
  docker restart emby >/dev/null
  sleep 15
  bash "${REPO_DIR}/post-auth.sh" strm-assistant
}

if [[ "${1:-}" == "--restore" ]]; then
  [[ $# -eq 2 ]] || {
    echo "用法: sudo ./setup-wizard.sh --restore /加密备份分片目录"
    exit 2
  }
  bash "${REPO_DIR}/install.sh" --restore "$2"
  echo
  echo "配置恢复完成。若 Google OAuth 或商业授权与旧机器绑定，请按后台提示重新授权。"
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "用法: sudo ./setup-wizard.sh [--restore /加密备份分片目录]"
  exit 2
fi

bash "${REPO_DIR}/install.sh"

server_ip="$(
  curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null ||
    hostname -I | awk '{print $1}'
)"

if cd2_is_ready; then
  echo
  echo "检测到已添加 /GoogleDrive，跳过 CD2 登录授权。"
else
  cat <<EOF

第一步：CD2 登录和 Google Drive 授权
打开：http://${server_ip}:19798
登录 CD2，添加 Google Drive，名称必须是 GoogleDrive。
确认团队盘路径能看到：/GoogleDrive/zero
不要在终端输入 Google 账号密码。
EOF
  pause_for_user "请在浏览器完成 CD2/Google 授权。"
fi
bash "${REPO_DIR}/post-auth.sh" cd2

if emby_is_initialized; then
  echo
  echo "检测到 Emby 已完成首次初始化，跳过初始化等待。"
else
  cat <<EOF

第二步：Emby 首次初始化
打开：http://${server_ip}:8096
创建管理员并完成初始设置。
EOF
  pause_for_user "请完成 Emby 初始化。"
fi

if strm_assistant_is_staged; then
  echo
  echo "检测到 Emby 最终目录中的神医助手 DLL 和授权文件，直接安装并优化。"
  bash "${REPO_DIR}/scripts/install-strm-assistant-local.sh" \
    "${PLUGIN_ROOT}"
  apply_strm_assistant_optimizations
elif ask_yes_no "是否现在从本地目录导入神医助手 DLL 和授权文件？"; then
  read -r -p \
    "导入目录（默认 /root/strm-assistant-import）: " plugin_source
  plugin_source="${plugin_source:-/root/strm-assistant-import}"
  bash "${REPO_DIR}/scripts/install-strm-assistant-local.sh" "${plugin_source}"
  apply_strm_assistant_optimizations
else
  cat <<'EOF'
已跳过神医助手。稍后把文件按以下结构放好：
  /root/strm-assistant-import/
  ├── StrmAssistantPro.dll
  └── configurations/
      ├── 授权ID文件
      └── 授权文件.lic

然后运行：
  sudo ./scripts/install-strm-assistant-local.sh /root/strm-assistant-import
  sudo ./post-auth.sh strm-assistant
EOF
fi

echo
echo "第三步：Symedia License"
read -r -s -p "请输入 Symedia License（输入内容不会回显）: " symedia_license
echo
if [[ -n "${symedia_license}" ]]; then
  umask 077
  printf 'SYMEDIA_LICENSE_KEY=%s\n' "${symedia_license}" \
    > "${STACK_ROOT}/symedia/.env"
  unset symedia_license
  (
    cd "${STACK_ROOT}/symedia"
    docker compose up -d
  )
else
  echo "未输入 License，暂不启动 Symedia。"
fi

echo
echo "第四步：Rclone 单向同步控制台"
rclone_settings="${STACK_ROOT}/rclone-sync/settings.json"
if [[ -s "${rclone_settings}" ]]; then
  rclone_web_user="$(jq -r '.username // "admin"' "${rclone_settings}")"
  rclone_password_summary="保留原密码"
  echo "检测到已有控制台账号 ${rclone_web_user}，保留原账号密码。"
  bash "${REPO_DIR}/scripts/install-rclone-sync-web.sh"
else
  read -r -p "控制台账号（默认 admin）: " rclone_web_user
  rclone_web_user="${rclone_web_user:-admin}"
  while (( ${#rclone_web_user} < 3 )); do
    echo "账号至少需要 3 个字符。"
    read -r -p "控制台账号（默认 admin）: " rclone_web_user
    rclone_web_user="${rclone_web_user:-admin}"
  done
  while true; do
    read -r -s -p "控制台密码（直接回车使用 admin）: " rclone_web_password
    echo
    rclone_web_password="${rclone_web_password:-admin}"
    if [[ "${rclone_web_password}" == "admin" ||
      ${#rclone_web_password} -ge 8 ]]; then
      break
    fi
    echo "自定义密码至少需要 8 个字符。"
  done
  RCLONE_SYNC_INITIAL_USER="${rclone_web_user}" \
  RCLONE_SYNC_INITIAL_PASSWORD="${rclone_web_password}" \
    bash "${REPO_DIR}/scripts/install-rclone-sync-web.sh"
  if [[ "${rclone_web_password}" == "admin" ]]; then
    rclone_password_summary="admin（首次登录必须修改）"
  else
    rclone_password_summary="安装时输入的自定义密码（不写入日志）"
  fi
  unset rclone_web_password
fi

echo
bash "${REPO_DIR}/healthcheck.sh" || true
echo
cat <<EOF
访问地址和后续手动操作
1. CD2：http://${server_ip}:19798（需手动登录并授权 Google Drive）
2. Emby：http://${server_ip}:8096（需手动完成初始化和媒体库设置）
3. Rclone 同步：http://${server_ip}:6096
   账号：${rclone_web_user}
   密码：${rclone_password_summary}
   登录后上传 /root/.config/rclone/rclone.conf，选择团队盘备份目录和本地目录。
4. Symedia：只有填写有效 License 后才会启动。
EOF
echo
echo "安装向导结束。以上标为 FAIL 的项目完成相应授权后再运行 sudo ./healthcheck.sh。"
