#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

OUTPUT_DIR="${1:-/root/emby-stack-backup}"
case "${OUTPUT_DIR}" in
  /root/*|/mnt/*|/opt/*) ;;
  *)
    echo "备份输出目录必须是 /root、/mnt 或 /opt 下的明确路径。"
    exit 2
    ;;
esac

install -d -m 0700 "${OUTPUT_DIR}"
temporary_dir="$(mktemp -d /root/emby-backup-work.XXXXXX)"
archive="${temporary_dir}/emby-stack.tar.gz"
encrypted="${temporary_dir}/emby-stack.tar.gz.age"
services_stopped=0

cleanup() {
  if [[ ${services_stopped} -eq 1 ]]; then
    docker start cd2 >/dev/null 2>&1 || true
    sleep 10
    docker start symedia emby >/dev/null 2>&1 || true
  fi
  case "${temporary_dir}" in
    /root/emby-backup-work.*) rm -rf -- "${temporary_dir}" ;;
  esac
}
trap cleanup EXIT

docker stop emby symedia cd2 >/dev/null 2>&1 || true
services_stopped=1

# Symedia 必须停机后再归档，保证 symedia.db、config.yaml 与 .secret_key
# 来自同一个一致时间点。缺少 .secret_key 会导致部分加密配置无法解密。
symedia_required=(
  /root/docker-compose/symedia/config/config.yaml
  /root/docker-compose/symedia/config/category.yaml
  /root/docker-compose/symedia/config/.secret_key
  /root/docker-compose/symedia/config/symedia.db
)
for required_path in "${symedia_required[@]}"; do
  if [[ ! -s "${required_path}" ]]; then
    echo "Symedia 关键文件缺失或为空：${required_path}"
    exit 3
  fi
done

python3 - /root/docker-compose/symedia/config/symedia.db <<'PY'
import sqlite3
import sys

uri = "file:" + sys.argv[1] + "?mode=ro"
connection = sqlite3.connect(uri, uri=True, timeout=30)
try:
    result = connection.execute("PRAGMA quick_check").fetchone()[0]
finally:
    connection.close()
if result != "ok":
    raise SystemExit("Symedia 数据库检查失败：" + result)
print("Symedia 数据库检查通过。")
PY

paths=(
  root/docker-compose/clouddrive2
  root/docker-compose/emby
  root/docker-compose/symedia
)

# 下列目录全是可重建缓存、日志、更新包或历史调参备份。排除它们不会
# 影响账号、任务、数据库和优化参数。媒体文件、STRM、NFO、封面以及
# Emby 海报元数据不在备份范围内。
tar --xattrs --acls \
  --exclude='root/docker-compose/clouddrive2/config/file_buffer_cache' \
  --exclude='root/docker-compose/clouddrive2/config/log' \
  --exclude='root/docker-compose/clouddrive2/config/temp' \
  --exclude='root/docker-compose/clouddrive2/config/updates' \
  --exclude='root/docker-compose/clouddrive2/backups' \
  --exclude='root/docker-compose/emby/config/cache' \
  --exclude='root/docker-compose/emby/config/logs' \
  --exclude='root/docker-compose/emby/config/metadata' \
  --exclude='root/docker-compose/emby/config/mediainfo-json' \
  --exclude='root/docker-compose/emby/config/transcoding-temp' \
  --exclude='root/docker-compose/symedia/config/logs' \
  --exclude='root/docker-compose/symedia/config/cache' \
  --exclude='root/docker-compose/symedia/config/temp' \
  -C / -czf "${archive}" "${paths[@]}"
echo "请输入强密码加密备份。密码遗失后无法恢复。"
age -p -o "${encrypted}" "${archive}"

stamp="$(date +%Y%m%d-%H%M%S)"
split -b 1800M -d -a 3 \
  "${encrypted}" \
  "${OUTPUT_DIR}/emby-stack-config-${stamp}.tar.gz.age.part-"

(
  cd "${OUTPUT_DIR}"
  sha256sum "emby-stack-config-${stamp}.tar.gz.age.part-"* \
    > "emby-stack-config-${stamp}.SHA256SUMS"
)

echo "加密备份完成：${OUTPUT_DIR}"
echo "只上传 .age.part-* 和 SHA256SUMS；不要上传任何临时明文归档。"
