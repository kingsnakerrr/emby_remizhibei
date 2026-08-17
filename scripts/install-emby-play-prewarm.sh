#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="/root/docker-compose/emby-play-prewarm"
SERVICE="/etc/systemd/system/emby-play-prewarm.service"
SCRIPT="${TARGET}/emby_play_prewarm.py"

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 root 或 sudo 运行。"
  exit 1
fi

case "${1:-install}" in
  install|status|uninstall) ;;
  *)
    echo "用法: $0 [install|status|uninstall]"
    exit 2
    ;;
esac

if [[ "${1:-install}" == "status" ]]; then
  systemctl --no-pager --full status emby-play-prewarm.service
  exit 0
fi

if [[ "${1:-install}" == "uninstall" ]]; then
  systemctl disable --now emby-play-prewarm.service 2>/dev/null || true
  rm -f "${SERVICE}"
  systemctl daemon-reload
  echo "Emby 播放预热器已卸载，保留目录：${TARGET}"
  exit 0
fi

install -d -m 0755 "${TARGET}"

cat >"${SCRIPT}" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor


LOG_PATH = "/root/docker-compose/emby/config/logs/embyserver.txt"
EMBY_BASE = "http://127.0.0.1:8096"
CONFIG_TOKEN_FILE = "/root/docker-compose/embystream-test/config/config.toml"
DEFAULT_USER_ID = "3b5504d86b09414eb10c12765bea1e5d"
HEAD_BYTES = int(os.environ.get("EMBY_PREWARM_HEAD_BYTES", str(8 * 1024 * 1024)))
TAIL_BYTES = int(os.environ.get("EMBY_PREWARM_TAIL_BYTES", str(1024 * 1024)))
COOLDOWN_SECONDS = int(os.environ.get("EMBY_PREWARM_COOLDOWN_SECONDS", "240"))
MAX_WORKERS = int(os.environ.get("EMBY_PREWARM_MAX_WORKERS", "2"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("emby-play-prewarm")

PLAYBACK_RE = re.compile(r"/emby/Items/(\d+)/PlaybackInfo\?([^ ]*)", re.I)
TOKEN_RE = re.compile(r'Token="([^"]+)"|api_key=([^&\s]+)', re.I)
USER_RE = re.compile(r"UserId=([0-9a-f-]{16,})", re.I)

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
recent: dict[str, float] = {}
recent_lock = threading.Lock()


def fallback_token() -> str:
    try:
        with open(CONFIG_TOKEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
            match = re.search(r'token\s*=\s*"([^"]+)"', f.read())
            return match.group(1) if match else ""
    except OSError:
        return ""


FALLBACK_TOKEN = fallback_token()
LAST_TOKEN = FALLBACK_TOKEN
TOKEN_LOCK = threading.Lock()


def clean_token(token: str) -> str:
    return "".join(ch for ch in urllib.parse.unquote(token) if ch.isalnum())


def remember_token(token: str) -> str:
    global LAST_TOKEN
    token = clean_token(token)
    if len(token) >= 20:
        with TOKEN_LOCK:
            LAST_TOKEN = token
    return token


def current_token() -> str:
    with TOKEN_LOCK:
        return LAST_TOKEN


def seed_token_from_log() -> None:
    try:
        with open(LOG_PATH, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 2 * 1024 * 1024))
            text = f.read().decode("utf-8", "ignore")
    except OSError:
        return
    for first, second in TOKEN_RE.findall(text):
        token = clean_token(first or second)
        if len(token) >= 20:
            remember_token(token)


def token_from_line(line: str) -> str:
    matches = TOKEN_RE.findall(line)
    for first, second in matches:
        token = clean_token(first or second)
        if len(token) >= 20:
            return remember_token(token)
    return current_token()


def user_from_line(line: str) -> str:
    match = USER_RE.search(line)
    return match.group(1) if match else DEFAULT_USER_ID


def get_json(url: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Accept-Encoding", "identity")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def playback_info(item_id: str, token: str, user_id: str) -> tuple[str, str]:
    query = urllib.parse.urlencode({"api_key": token, "UserId": user_id})
    data = get_json(f"{EMBY_BASE}/emby/Items/{item_id}/PlaybackInfo?{query}")
    media_source = (data.get("MediaSources") or [{}])[0]
    container = media_source.get("Container") or "mkv"
    if container == "strm":
        path = media_source.get("Path") or ""
        container = path.rsplit(".", 1)[-1] if "." in path else "mkv"
    stream_query = {
        "api_key": token,
        "UserId": user_id,
        "MediaSourceId": media_source.get("Id") or ("mediasource_" + item_id),
        "Static": "true",
    }
    stream_url = (
        f"{EMBY_BASE}/emby/videos/{item_id}/original.{container}?"
        f"{urllib.parse.urlencode(stream_query)}"
    )
    return container, stream_url


def range_read(url: str, start: int, end: int) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Range", f"bytes={start}-{end}")
    req.add_header("Accept-Encoding", "identity")
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = resp.read()
        content_range = resp.headers.get("Content-Range", "")
        total = None
        match = re.search(r"/(\d+)$", content_range)
        if match:
            total = int(match.group(1))
        return {
            "status": resp.status,
            "bytes": len(data),
            "range": content_range,
            "total": total,
        }


def prewarm(item_id: str, token: str, user_id: str) -> None:
    started = time.perf_counter()
    try:
        container, stream_url = playback_info(item_id, token, user_id)
        head = range_read(stream_url, 0, HEAD_BYTES - 1)
        tail = None
        total = head.get("total")
        if total:
            tail_start = max(0, int(total) - TAIL_BYTES)
            tail = range_read(stream_url, tail_start, int(total) - 1)
        log.info(
            "prewarm item=%s container=%s head=%s tail=%s seconds=%.3f",
            item_id,
            container,
            head,
            tail,
            time.perf_counter() - started,
        )
    except Exception as exc:
        log.warning("prewarm failed item=%s error=%r", item_id, exc)


def schedule(item_id: str, token: str, user_id: str) -> None:
    if not token:
        return
    key = f"{item_id}:{token[:8]}"
    now = time.time()
    with recent_lock:
        if recent.get(key, 0) > now:
            return
        recent[key] = now + COOLDOWN_SECONDS
    executor.submit(prewarm, item_id, token, user_id)


def follow(path: str):
    while not os.path.exists(path):
        log.info("waiting for %s", path)
        time.sleep(3)
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        handle.seek(0, os.SEEK_END)
        inode = os.fstat(handle.fileno()).st_ino
        while True:
            line = handle.readline()
            if line:
                yield line
                continue
            time.sleep(0.2)
            try:
                stat = os.stat(path)
                if stat.st_ino != inode or stat.st_size < handle.tell():
                    log.info("log rotated, reopening")
                    return
            except FileNotFoundError:
                return


def main() -> None:
    seed_token_from_log()
    log.info("started, watching %s token_seeded=%s", LOG_PATH, bool(current_token()))
    while True:
        for line in follow(LOG_PATH):
            token_from_line(line)
            match = PLAYBACK_RE.search(line)
            if not match or "IsPlayback=true" not in line:
                continue
            item_id = match.group(1)
            token = token_from_line(line)
            user_id = user_from_line(line)
            log.info("schedule item=%s user=%s", item_id, user_id)
            schedule(item_id, token, user_id)
        time.sleep(1)


if __name__ == "__main__":
    main()
PY

chmod 0755 "${SCRIPT}"

cat >"${SERVICE}" <<UNIT
[Unit]
Description=Emby Playback CD2 Prewarmer
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${SCRIPT}
Restart=always
RestartSec=3
WorkingDirectory=${TARGET}

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now emby-play-prewarm.service
systemctl restart emby-play-prewarm.service
sleep 1
systemctl --no-pager --full status emby-play-prewarm.service | sed -n '1,18p'
