#!/usr/bin/env bash
set -Eeuo pipefail

failed=0

check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '[OK]   %s\n' "${label}"
  else
    printf '[FAIL] %s\n' "${label}"
    failed=1
  fi
}

check "Docker" docker info
check "CD2 容器" sh -c \
  "[ \"$(docker inspect -f '{{.State.Running}}' cd2 2>/dev/null)\" = true ]"
check "Emby 容器" sh -c \
  "[ \"$(docker inspect -f '{{.State.Running}}' emby 2>/dev/null)\" = true ]"
if docker inspect symedia >/dev/null 2>&1; then
  check "Symedia 容器" sh -c \
    "[ \"$(docker inspect -f '{{.State.Running}}' symedia 2>/dev/null)\" = true ]"
  check "Symedia 配置和数据库" \
    "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/scripts/audit-symedia.sh" \
    --skip-db
fi
check "CD2 挂载点" findmnt /CloudNAS/CloudDrive
check "宿主机 GoogleDrive/zero" test -d /CloudNAS/CloudDrive/GoogleDrive/zero
check "Emby 能看到云盘" docker exec emby test -d /CloudNAS/CloudDrive/GoogleDrive/zero
check "Emby 能看到本地 STRM 根目录" docker exec emby test -d /home/symedia_gd
check "Emby 8096" curl -fsS --max-time 5 http://127.0.0.1:8096/emby/System/Info/Public
check "Rclone" rclone version
if systemctl list-unit-files emby-play-prewarm.service >/dev/null 2>&1; then
  check "Emby 播放预热器" systemctl is-active --quiet emby-play-prewarm.service
fi
if systemctl list-unit-files emby-fix-strm-images.timer >/dev/null 2>&1; then
  check "Emby STRM 图片补齐器" systemctl is-active --quiet emby-fix-strm-images.timer
fi
if systemctl list-unit-files rclone-sync-web.service >/dev/null 2>&1; then
  check "Rclone 同步控制台服务" systemctl is-active --quiet rclone-sync-web.service
  check "Rclone 同步控制台 6096" \
    curl -fsS --max-time 5 http://127.0.0.1:6096/healthz
fi

if systemctl list-unit-files embystream.service >/dev/null 2>&1; then
  embystream_healthy() {
    local active_since refresh_due_count
    systemctl is-active --quiet embystream.service || return 1
    active_since="$(
      systemctl show embystream.service \
        -p ActiveEnterTimestamp --value
    )"
    if journalctl -u embystream.service --since "${active_since}" --no-pager |
        grep -q 'google_drive_refresh_failed'; then
      return 1
    fi
    refresh_due_count="$(
      journalctl -u embystream.service --since "10 seconds ago" --no-pager |
        grep -c 'google_drive_refresh_scheduler_due' || true
    )"
    (( refresh_due_count < 20 ))
  }
  check "EmbyStream 服务、Google OAuth 和刷新调度器" embystream_healthy
fi

if [[ ${failed} -ne 0 ]]; then
  exit 1
fi

echo "基础验收通过。"
