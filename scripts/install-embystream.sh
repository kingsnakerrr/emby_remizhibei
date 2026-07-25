#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="v0.0.43"
ARCHIVE="embystream-amd64-linux.tar.gz"
BASE_URL="https://github.com/PiliPili-Team/EmbyStream/releases/download/${VERSION}"
TARGET="/root/docker-compose/embystream"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

install -d -m 0755 \
  "${TARGET}/bin" \
  "${TARGET}/config/ssl" \
  "${TARGET}/auth" \
  "${TARGET}/logs"

case "$(uname -m)" in
  x86_64|amd64) ;;
  *)
    echo "当前安装模板只固定了 amd64 EmbyStream。"
    exit 1
    ;;
esac

if [[ -x "${TARGET}/bin/embystream" ]]; then
  echo "EmbyStream 已存在，跳过下载。"
else
  temporary_dir="$(mktemp -d)"
  trap 'rm -rf -- "${temporary_dir}"' EXIT
  curl -fL --retry 3 -o "${temporary_dir}/${ARCHIVE}" \
    "${BASE_URL}/${ARCHIVE}"
  curl -fL --retry 3 -o "${temporary_dir}/embystream.sha512sum" \
    "${BASE_URL}/embystream.sha512sum"
  expected_sha="$(
    awk -v archive="${ARCHIVE}" \
      '$NF == archive || $NF ~ ("/" archive "$") { print $1; exit }' \
      "${temporary_dir}/embystream.sha512sum"
  )"
  if [[ ! "${expected_sha}" =~ ^[0-9a-fA-F]{128}$ ]]; then
    echo "官方校验文件中没有找到 ${ARCHIVE} 的有效 SHA-512。"
    exit 1
  fi
  actual_sha="$(
    sha512sum "${temporary_dir}/${ARCHIVE}" | awk '{ print $1 }'
  )"
  if [[ "${actual_sha,,}" != "${expected_sha,,}" ]]; then
    echo "EmbyStream 下载包 SHA-512 校验失败。"
    exit 1
  fi
  echo "${ARCHIVE}: SHA-512 校验通过。"
  tar -xzf "${temporary_dir}/${ARCHIVE}" -C "${temporary_dir}"
  binary="$(find "${temporary_dir}" -type f -name embystream -print -quit)"
  if [[ -z "${binary}" ]]; then
    echo "发布包中没有找到 embystream。"
    exit 1
  fi
  install -m 0755 "${binary}" "${TARGET}/bin/embystream"
fi

# The example contains no credentials. Always refresh it so an existing
# installation receives fields required by newer EmbyStream releases.
install -m 0644 "${REPO_DIR}/templates/embystream/config.toml.example" \
  "${TARGET}/config/config.toml.example"
if [[ ! -e "${TARGET}/.env.private" ]]; then
  install -m 0600 "${REPO_DIR}/templates/embystream/.env.private.example" \
    "${TARGET}/.env.private"
fi
install -m 0644 "${REPO_DIR}/systemd/embystream.service" \
  /etc/systemd/system/embystream.service
systemctl daemon-reload
echo "EmbyStream ${VERSION} 已安装，等待 OAuth 配置。"
