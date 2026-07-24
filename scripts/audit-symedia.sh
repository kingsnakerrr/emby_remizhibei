#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_ROOT="/root/docker-compose/symedia/config"
DB="${CONFIG_ROOT}/symedia.db"
SKIP_DB=0

if [[ "${1:-}" == "--skip-db" ]]; then
  SKIP_DB=1
elif [[ $# -gt 0 ]]; then
  echo "用法: $0 [--skip-db]"
  exit 2
fi

required_files=(
  "${CONFIG_ROOT}/config.yaml"
  "${CONFIG_ROOT}/category.yaml"
  "${CONFIG_ROOT}/.secret_key"
  "${DB}"
)

failed=0
for path in "${required_files[@]}"; do
  if [[ -s "${path}" ]]; then
    printf '[OK]   %s\n' "${path}"
  else
    printf '[FAIL] %s 不存在或为空\n' "${path}"
    failed=1
  fi
done

for path in \
  /home/symedia_gd \
  /home/symedia_jav \
  /CloudNAS/CloudDrive; do
  if [[ -d "${path}" ]]; then
    printf '[OK]   %s\n' "${path}"
  else
    printf '[FAIL] %s 不存在\n' "${path}"
    failed=1
  fi
done

if [[ -s "${DB}" && ${SKIP_DB} -eq 0 ]]; then
  result="$(
    python3 - "${DB}" <<'PY'
import sqlite3
import sys

uri = "file:" + sys.argv[1] + "?mode=ro"
connection = sqlite3.connect(uri, uri=True, timeout=30)
try:
    print(connection.execute("PRAGMA quick_check").fetchone()[0])
finally:
    connection.close()
PY
  )"
  if [[ "${result}" == "ok" ]]; then
    echo "[OK]   Symedia SQLite quick_check"
  else
    echo "[FAIL] Symedia SQLite: ${result}"
    failed=1
  fi
elif [[ ${SKIP_DB} -eq 1 ]]; then
  echo "[SKIP] Symedia 正在运行，跳过 SQLite 全盘检查"
fi

if [[ ${failed} -ne 0 ]]; then
  exit 1
fi

echo "Symedia 配置、密钥、数据库和固定路径检查通过。"
