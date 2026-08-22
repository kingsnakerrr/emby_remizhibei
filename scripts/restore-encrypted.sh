#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

PARTS_DIR="${1:-}"
if [[ -z "${PARTS_DIR}" || ! -d "${PARTS_DIR}" ]]; then
  echo "用法: $0 /包含age分片和SHA256SUMS的目录"
  exit 2
fi

mapfile -t parts < <(
  find "${PARTS_DIR}" -maxdepth 1 -type f -name '*.age.part-*' -print |
    sort
)
if [[ ${#parts[@]} -eq 0 ]]; then
  echo "没有找到 *.age.part-*。"
  exit 2
fi

checksum_file="$(find "${PARTS_DIR}" -maxdepth 1 -type f \
  -name '*.SHA256SUMS' -print -quit)"
if [[ -n "${checksum_file}" ]]; then
  (
    cd "${PARTS_DIR}"
    sha256sum -c "$(basename "${checksum_file}")"
  )
fi

echo "此操作会把备份覆盖到 /root/docker-compose、/home/symedia_*。"
echo "只应在新的空白 VPS 或明确需要恢复的服务器上执行。"
read -r -p "输入 RESTORE 继续: " confirmation
if [[ "${confirmation}" != "RESTORE" ]]; then
  echo "已取消。"
  exit 1
fi

temporary_dir="$(mktemp -d /root/emby-restore-work.XXXXXX)"
encrypted="${temporary_dir}/emby-stack.tar.gz.age"
archive="${temporary_dir}/emby-stack.tar.gz"

cleanup() {
  case "${temporary_dir}" in
    /root/emby-restore-work.*) rm -rf -- "${temporary_dir}" ;;
  esac
}
trap cleanup EXIT

cat "${parts[@]}" > "${encrypted}"
echo "请输入备份加密密码。"
age -d -o "${archive}" "${encrypted}"

echo "归档前20项："
tar -tzf "${archive}" | head -20

docker stop emby symedia cd2 >/dev/null 2>&1 || true

tar --xattrs --acls -C / -xzf "${archive}"
systemctl daemon-reload

install -d -m 0755 \
  /CloudNAS/CloudDrive \
  /home/symedia_gd \
  /home/symedia_jav

"$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/audit-symedia.sh"

cd /root/docker-compose/clouddrive2
docker compose up -d
sleep 15
cd /root/docker-compose/symedia
docker compose up -d
cd /root/docker-compose/emby
docker compose up -d

echo "恢复完成，请运行仓库中的 ./healthcheck.sh。"
