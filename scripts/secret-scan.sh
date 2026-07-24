#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"

patterns=(
  'ya29\.'
  '1//[A-Za-z0-9_-]'
  '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
  'client_secret_[A-Za-z0-9_-]+\.apps\.googleusercontent\.com'
  'SYMEDIA_LICENSE_KEY=[A-Za-z0-9+/=]{20,}'
  'EMBY_TOKEN=[A-Za-z0-9._-]{20,}'
  'GOOGLE_CLIENT_SECRET=[A-Za-z0-9._-]{20,}'
  'GOOGLE_REFRESH_TOKEN=[A-Za-z0-9/_-]{20,}'
)

failed=0
for pattern in "${patterns[@]}"; do
  if grep -RInE \
    --exclude-dir=.git \
    --exclude='*.example' \
    --exclude='secret-scan.sh' \
    -- "${pattern}" .; then
    failed=1
  fi
done

if find . -type f \( \
  -name '*.age' -o \
  -name '*.part-*' -o \
  -name 'token.json' -o \
  -name 'client_secret*.json' -o \
  -name '.env.private' \
  \) -print | grep -q .; then
  echo "仓库目录内出现应被隔离的私密文件。"
  failed=1
fi

if [[ ${failed} -ne 0 ]]; then
  echo "敏感信息扫描失败。"
  exit 1
fi

echo "敏感信息扫描通过。"
