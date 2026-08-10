#!/usr/bin/env bash
set -Eeuo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STACK_ROOT="/root/docker-compose"
RESTORE_DIR=""
INSTALLER_REPO="${INSTALLER_REPO:-kingsnakerrr/emby_remizhibei}"
INSTALLER_REF="${INSTALLER_REF:-main}"
INSTALLER_DIR="${STACK_ROOT}/emby-stack-installer"
LOG_FILE="/var/log/emby-stack-installer.log"

if [[ "${EMBY_STACK_LOG_ACTIVE:-0}" != "1" ]]; then
  touch "${LOG_FILE}"
  chmod 0600 "${LOG_FILE}"
  export EMBY_STACK_LOG_ACTIVE=1
  exec > >(tee -a "${LOG_FILE}") 2>&1
fi

on_error() {
  local status=$?
  echo
  echo "安装失败：第 ${BASH_LINENO[0]:-?} 行，退出码 ${status}。"
  echo "完整日志：${LOG_FILE}"
  echo "修复问题后可直接重跑同一条一键安装命令。"
  exit "${status}"
}
trap on_error ERR

repair_interrupted_dpkg() {
  local audit grub_status

  command -v dpkg >/dev/null 2>&1 || return 0
  audit="$(dpkg --audit 2>/dev/null || true)"
  [[ -n "${audit}" ]] || return 0

  echo "检测到上次未完成的软件包配置，正在修复……"
  grub_status="$(
    dpkg-query -W -f='${db:Status-Abbrev}' grub-pc 2>/dev/null || true
  )"
  if [[ -n "${grub_status}" && "${grub_status}" != "ii " ]]; then
    echo "检测到未完成的 grub-pc 配置；允许云主机使用空安装设备继续。"
    {
      echo "grub-pc grub-pc/install_devices_empty boolean true"
      echo "grub-pc grub-pc/install_devices multiselect"
    } | debconf-set-selections
  fi

  DEBIAN_FRONTEND=noninteractive dpkg --configure -a
  DEBIAN_FRONTEND=noninteractive apt-get -f install -y
}

bootstrap_from_github() {
  local temporary_dir archive_url

  export DEBIAN_FRONTEND=noninteractive
  repair_interrupted_dpkg
  if ! command -v curl >/dev/null 2>&1 ||
    ! command -v tar >/dev/null 2>&1; then
    apt-get update
    apt-get install -y ca-certificates curl tar gzip
  fi

  temporary_dir="$(mktemp -d /tmp/emby-stack-bootstrap.XXXXXX)"
  archive_url="https://codeload.github.com/${INSTALLER_REPO}/tar.gz/refs/heads/${INSTALLER_REF}"
  echo "下载安装包：${INSTALLER_REPO}@${INSTALLER_REF}"
  curl -fL --retry 3 --connect-timeout 15 \
    "${archive_url}" -o "${temporary_dir}/installer.tar.gz"

  install -d -m 0755 "${INSTALLER_DIR}"
  tar -xzf "${temporary_dir}/installer.tar.gz" \
    --strip-components=1 -C "${INSTALLER_DIR}"
  chmod +x \
    "${INSTALLER_DIR}"/*.sh \
    "${INSTALLER_DIR}"/scripts/*.sh

  case "${temporary_dir}" in
    /tmp/emby-stack-bootstrap.*)
      rm -rf -- "${temporary_dir}"
      ;;
  esac

  if [[ -r /dev/tty ]]; then
    exec bash "${INSTALLER_DIR}/setup-wizard.sh" "$@" </dev/tty
  fi
  exec bash "${INSTALLER_DIR}/setup-wizard.sh" "$@"
}

# raw.githubusercontent.com 只下载到这一个文件时，自动获取完整仓库。
if [[ ! -f "${REPO_DIR}/setup-wizard.sh" ||
  ! -f "${REPO_DIR}/compose/emby.yml" ]]; then
  bootstrap_from_github "$@"
fi

usage() {
  cat <<'EOF'
用法:
  sudo ./install.sh
  sudo ./install.sh --restore /包含加密备份分片的目录

不带 --restore：创建全新服务骨架，登录和授权后再配置。
带 --restore：安装基础依赖后，直接恢复原服务器的完整配置和数据。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restore)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      RESTORE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

install_packages() {
  local distro codename arch

  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE=a

  if [[ ! -r /etc/os-release ]]; then
    echo "仅支持 Ubuntu/Debian。"
    exit 3
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  distro="${ID:-}"
  codename="${VERSION_CODENAME:-}"
  case "${distro}" in
    ubuntu|debian) ;;
    *)
      echo "当前系统 ${distro:-unknown} 不在已验证范围，仅支持 Ubuntu/Debian。"
      exit 3
      ;;
  esac
  if [[ -z "${codename}" ]]; then
    echo "无法识别系统代号 VERSION_CODENAME。"
    exit 3
  fi

  repair_interrupted_dpkg
  echo "更新软件包索引……"
  apt-get update
  if [[ "${EMBY_STACK_FULL_UPGRADE:-0}" == "1" ]]; then
    echo "已显式要求整机升级；开始执行 apt-get upgrade……"
    apt-get upgrade -y
  else
    echo "跳过内核、GRUB和整机升级，只安装本项目必要依赖。"
  fi
  apt-get install -y \
    ca-certificates curl gnupg lsb-release \
    python3 sqlite3 jq age tar gzip openssl nginx \
    fuse3 kmod

  if ! command -v docker >/dev/null 2>&1 ||
    ! docker compose version >/dev/null 2>&1; then
    echo "安装 Docker Engine 与 Docker Compose v2……"
    apt-get remove -y \
      docker.io docker-compose docker-compose-v2 docker-doc \
      podman-docker containerd runc 2>/dev/null || true

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${distro}/gpg" |
      gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    arch="$(dpkg --print-architecture)"
    printf \
      'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/%s %s stable\n' \
      "${arch}" "${distro}" "${codename}" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y \
      docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin
  fi

  systemctl enable --now docker
  docker compose version
  modprobe fuse 2>/dev/null || true
  if [[ ! -e /dev/fuse ]]; then
    echo "未检测到 /dev/fuse，当前 VPS 内核不支持 CD2 FUSE 挂载。"
    exit 4
  fi
}

copy_if_missing() {
  local source_path="$1"
  local target_path="$2"
  if [[ ! -e "${target_path}" ]]; then
    install -D -m 0644 "${source_path}" "${target_path}"
  fi
}

install_play_prewarm() {
  if [[ -x "${REPO_DIR}/scripts/install-emby-play-prewarm.sh" ]]; then
    echo "安装 Emby 播放预热器……"
    bash "${REPO_DIR}/scripts/install-emby-play-prewarm.sh"
  else
    echo "未找到播放预热器安装脚本，跳过。"
  fi
}

install_packages

if [[ -f /var/run/reboot-required ]]; then
  echo
  echo "系统已有待生效升级，需要重启；安装会继续，完成后请执行 reboot。"
fi

if [[ -n "${RESTORE_DIR}" ]]; then
  bash "${REPO_DIR}/scripts/restore-encrypted.sh" "${RESTORE_DIR}"
  install_play_prewarm
  bash "${REPO_DIR}/healthcheck.sh"
  exit 0
fi

install -d -m 0755 \
  "${STACK_ROOT}/clouddrive2/config" \
  "${STACK_ROOT}/emby/config/plugins/configurations" \
  "${STACK_ROOT}/emby/config/mediainfo-json" \
  "${STACK_ROOT}/symedia/config" \
  /CloudNAS \
  /home/symedia_gd \
  /home/symedia_jav

install -m 0644 "${REPO_DIR}/compose/clouddrive2.yml" \
  "${STACK_ROOT}/clouddrive2/docker-compose.yml"
install -m 0644 "${REPO_DIR}/compose/emby.yml" \
  "${STACK_ROOT}/emby/docker-compose.yml"
install -m 0644 "${REPO_DIR}/compose/symedia.yml" \
  "${STACK_ROOT}/symedia/docker-compose.yml"

copy_if_missing \
  "${REPO_DIR}/templates/clouddrive2/config.toml" \
  "${STACK_ROOT}/clouddrive2/config/config.toml"
copy_if_missing \
  "${REPO_DIR}/templates/clouddrive2/systemsettings.json" \
  "${STACK_ROOT}/clouddrive2/config/systemsettings.json"
copy_if_missing \
  "${REPO_DIR}/templates/symedia/.env.example" \
  "${STACK_ROOT}/symedia/.env"

chmod 0600 "${STACK_ROOT}/symedia/.env"

cd "${STACK_ROOT}/clouddrive2"
docker compose up -d

cd "${STACK_ROOT}/emby"
docker compose up -d

install_play_prewarm

echo
echo "基础安装完成。"
echo "1. 打开 http://VPS-IP:19798 登录 CD2，添加名为 /GoogleDrive 的 Google Drive。"
echo "2. 完成后运行: ${REPO_DIR}/post-auth.sh cd2"
echo "3. 打开 http://VPS-IP:8096 完成 Emby 初始化。"
echo "4. 神医助手安装授权后运行: ${REPO_DIR}/post-auth.sh strm-assistant"
echo "5. 填写 ${STACK_ROOT}/symedia/.env 后再启动 Symedia。"
echo "6. Emby 播放预热器已默认安装；CD2、Emby 和媒体库准备好后会自动生效。"
echo "7. EmbyStream 是可选备用线路，在 setup-wizard.sh 最后按需安装。"
echo "8. Rclone 单向同步控制台由向导自动安装，端口为 6096。"
