import os
import json
import html
import sqlite3
import secrets
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
try:
    import docker
except Exception:
    docker = None
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

DB_PATH = os.getenv("DB_PATH", "/data/app.db")
SESSION_SECRET_FILE = os.getenv("SESSION_SECRET_FILE", "/data/session_secret")
WEBHOOK_LOG_DIR = "/data/webhooks"
LOCAL_DOCKER_NETWORK = "emby-notify-net"

def load_or_create_session_secret():
    p = Path(SESSION_SECRET_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    s = secrets.token_urlsafe(48)
    p.write_text(s, encoding="utf-8")
    return s

app = FastAPI(title="Emby Telegram Notifier")
app.add_middleware(SessionMiddleware, secret_key=load_or_create_session_secret(), same_site="lax")
templates = Jinja2Templates(directory="/app/app/templates")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    Path(WEBHOOK_LOG_DIR).mkdir(parents=True, exist_ok=True)
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS app_settings(
      id INTEGER PRIMARY KEY CHECK(id=1),
      username TEXT NOT NULL DEFAULT 'admin',
      password_hash TEXT NOT NULL,
      global_bot_token TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS servers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      emby_url TEXT NOT NULL DEFAULT '',
      emby_api_key TEXT NOT NULL DEFAULT '',
      bot_token_override TEXT NOT NULL DEFAULT '',
      webhook_token TEXT NOT NULL UNIQUE,
      send_test_to_telegram INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS libraries(
      server_id INTEGER NOT NULL,
      id TEXT NOT NULL,
      name TEXT NOT NULL,
      paths_json TEXT DEFAULT '[]',
      PRIMARY KEY(server_id,id)
    );

    CREATE TABLE IF NOT EXISTS routes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      server_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      library_id TEXT NOT NULL,
      chat_id TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS webhook_status(
      server_id INTEGER PRIMARY KEY,
      received_at TEXT NOT NULL DEFAULT '',
      event TEXT NOT NULL DEFAULT '',
      source_name TEXT NOT NULL DEFAULT '',
      is_test INTEGER NOT NULL DEFAULT 0,
      telegram_count INTEGER NOT NULL DEFAULT 0,
      detail TEXT NOT NULL DEFAULT ''
    );
    """)
    # Schema migration for existing installations.
    server_columns = {r["name"] for r in conn.execute("PRAGMA table_info(servers)").fetchall()}
    if "send_test_to_telegram" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN send_test_to_telegram INTEGER NOT NULL DEFAULT 0")

    row = conn.execute("SELECT id FROM app_settings WHERE id=1").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO app_settings(id,username,password_hash,global_bot_token) VALUES(1,'admin',?,'')",
            (hash_password("admin"),)
        )
    count = conn.execute("SELECT COUNT(*) c FROM servers").fetchone()["c"]
    if count == 0:
        conn.execute(
            "INSERT INTO servers(name,webhook_token) VALUES(?,?)",
            ("Emby 1", make_webhook_token())
        )
    conn.commit()
    conn.close()


def make_webhook_token():
    # 32 random bytes -> ~43 URL-safe chars
    return secrets.token_urlsafe(32)


PBKDF2_ITERATIONS = 600_000

def hash_password(password: str):
    """Return a salted PBKDF2-SHA256 password hash."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        salt.hex(),
        digest.hex(),
    )

def verify_password(password: str, stored_hash: str):
    """Verify current PBKDF2 hashes and the legacy v2 SHA-256 hash."""
    if not stored_hash:
        return False, False

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt_hex, digest_hex = stored_hash.split("$", 3)
            calc = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(rounds),
            ).hex()
            return secrets.compare_digest(calc, digest_hex), False
        except Exception:
            return False, False

    # v2 compatibility: sha256("emby-tg-login-v2" + password)
    legacy = hashlib.sha256(("emby-tg-login-v2" + password).encode()).hexdigest()
    ok = secrets.compare_digest(legacy, stored_hash)
    return ok, ok


def require_login(request: Request):
    if not request.session.get("logged_in"):
        raise HTTPException(status_code=401)


def normalize_url(url: str):
    return url.strip().rstrip("/")


def external_base_url(request: Request) -> str:
    # Prefer reverse-proxy forwarded headers, otherwise use the page's own host.
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host")
    prefix = (request.headers.get("x-forwarded-prefix") or "").strip().rstrip("/")
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    if host:
        return f"{proto or request.url.scheme}://{host}{prefix}".rstrip("/")
    return f"{request.url.scheme}://{request.headers.get('host')}{prefix}".rstrip("/")


def get_settings():
    conn = db()
    row = conn.execute("SELECT * FROM app_settings WHERE id=1").fetchone()
    conn.close()
    return dict(row)


def wants_json_response(request: Request) -> bool:
    return request.headers.get("x-requested-with", "").lower() == "fetch"


def success_response(request: Request, message: str, server_id: Optional[int] = None, **data):
    if wants_json_response(request):
        return JSONResponse({"ok": True, "message": message, **data})
    target = "/"
    if server_id is not None:
        target = f"/?server_id={server_id}"
    sep = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{sep}msg={message}", status_code=303)


def failure_response(request: Request, message: str, server_id: Optional[int] = None, status_code: int = 400):
    if wants_json_response(request):
        return JSONResponse({"ok": False, "message": message}, status_code=status_code)
    target = "/"
    if server_id is not None:
        target = f"/?server_id={server_id}"
    sep = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{sep}msg={message}", status_code=303)


def update_webhook_status(server_id: int, event: str, source_name: str = "", is_test: bool = False,
                          telegram_count: int = 0, detail: str = ""):
    conn = db()
    conn.execute("""
      INSERT INTO webhook_status(server_id, received_at, event, source_name, is_test, telegram_count, detail)
      VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(server_id) DO UPDATE SET
        received_at=excluded.received_at,
        event=excluded.event,
        source_name=excluded.source_name,
        is_test=excluded.is_test,
        telegram_count=excluded.telegram_count,
        detail=excluded.detail
    """, (
        server_id,
        datetime.now(timezone.utc).isoformat(),
        event or "",
        source_name or "",
        1 if is_test else 0,
        int(telegram_count or 0),
        detail or ""
    ))
    conn.commit()
    conn.close()


def get_server(server_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM servers WHERE id=?", (server_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def bot_token_for_server(server: dict):
    override = (server.get("bot_token_override") or "").strip()
    if override:
        return override
    return (get_settings().get("global_bot_token") or "").strip()


async def emby_get(server: dict, path: str):
    base = normalize_url(server["emby_url"])
    if not base or not server["emby_api_key"]:
        raise RuntimeError("请先填写 Emby 地址和 API Key")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            f"{base}/emby{path}",
            headers={"X-Emby-Token": server["emby_api_key"]}
        )
        r.raise_for_status()
        return r.json()


async def refresh_libraries(server_id: int):
    server = get_server(server_id)
    data = await emby_get(server, "/Library/SelectableMediaFolders")
    items = data.get("Items") if isinstance(data, dict) else data
    items = items or []

    conn = db()
    seen = set()
    for item in items:
        lid = str(item.get("Id") or "")
        if not lid:
            continue
        name = item.get("Name") or lid
        paths = []
        for key in ("Path", "Locations", "Paths"):
            v = item.get(key)
            if isinstance(v, str):
                paths.append(v)
            elif isinstance(v, list):
                paths.extend(x for x in v if isinstance(x, str))
        for sub in item.get("SubFolders") or []:
            if sub.get("Path"):
                paths.append(sub["Path"])
        paths = list(dict.fromkeys(paths))
        conn.execute("""
          INSERT INTO libraries(server_id,id,name,paths_json)
          VALUES(?,?,?,?)
          ON CONFLICT(server_id,id)
          DO UPDATE SET name=excluded.name, paths_json=excluded.paths_json
        """, (server_id, lid, name, json.dumps(paths, ensure_ascii=False)))
        seen.add(lid)
    conn.commit()
    conn.close()
    return len(seen)


def bytes_size(n):
    if not n:
        return ""
    try:
        n = float(n)
    except Exception:
        return ""
    units = ["B", "K", "M", "G", "T"]
    i = 0
    while n >= 1024 and i < len(units)-1:
        n /= 1024
        i += 1
    if i == 0:
        return f"{int(n)}{units[i]}"
    return f"{n:.1f}{units[i]}"


def _clean_quality_text(value: str) -> str:
    if not value:
        return ""
    value = str(value).replace("_", " ").replace(".", " ")
    return " ".join(value.split())


def detect_source_quality(item: dict, media_source: dict, video: dict, audio: dict) -> str:
    """Best-effort quality string from Emby metadata + filename/path."""
    import re

    haystack = " ".join([
        str(item.get("Path") or ""),
        str(item.get("ResolvedMediaPath") or ""),
        str(item.get("Name") or ""),
        str(media_source.get("Path") or ""),
        str(media_source.get("Name") or ""),
        str(media_source.get("Container") or ""),
        str(video.get("DisplayTitle") or ""),
        str(audio.get("DisplayTitle") or ""),
        str(audio.get("Profile") or ""),
    ])
    h = haystack.lower()
    parts = []

    # Source / release type.
    if re.search(r'blu[ ._-]?ray|bdrip|bdremux|bluray', h):
        parts.append("BluRay")
    elif re.search(r'web[ ._-]?(dl|rip)', h):
        parts.append("WEB-DL" if re.search(r'web[ ._-]?dl', h) else "WEBRip")
    elif re.search(r'hdtv', h):
        parts.append("HDTV")
    elif re.search(r'dvdrip|dvd', h):
        parts.append("DVD")

    if re.search(r'\bremux\b|bdremux', h):
        parts.append("REMUX")

    # Resolution, normalized to familiar labels.
    height = video.get("Height")
    width = video.get("Width")
    try:
        height = int(height) if height is not None else None
    except Exception:
        height = None
    try:
        width = int(width) if width is not None else None
    except Exception:
        width = None

    if height:
        if height >= 2000 or (width and width >= 3800):
            parts.append("2160p")
        elif height >= 1000:
            parts.append("1080p")
        elif height >= 700:
            parts.append("720p")
        elif height >= 500:
            parts.append("576p")
        elif height >= 400:
            parts.append("480p")
    else:
        m = re.search(r'\b(2160|1080|720|576|480)p\b', h)
        if m:
            parts.append(m.group(1) + "p")

    # Video codec.
    vcodec = str(video.get("Codec") or "").lower()
    if vcodec in ("hevc", "h265", "h.265"):
        parts.append("HEVC")
    elif vcodec in ("h264", "avc", "h.264"):
        parts.append("H264")
    elif vcodec in ("av1",):
        parts.append("AV1")
    elif vcodec in ("vp9",):
        parts.append("VP9")
    elif vcodec:
        parts.append(vcodec.upper())

    # HDR / Dolby Vision when Emby exposes it or filename contains it.
    vr = str(video.get("VideoRange") or "").lower()
    vtype = str(video.get("VideoRangeType") or "").lower()
    if "dolbyvision" in vtype or "dolby vision" in h or re.search(r'\b(dv|dovi)\b', h):
        parts.append("DV")
    if "hdr" in vr or "hdr" in vtype or re.search(r'\bhdr10\+?\b|\bhdr\b', h):
        parts.append("HDR")
    elif vr == "sdr" or vtype == "sdr":
        parts.append("SDR")

    # Prefer Emby's audio display/profile because it contains DTS-HD MA / TrueHD etc.
    adisplay = _clean_quality_text(audio.get("DisplayTitle") or "")
    aprofile = _clean_quality_text(audio.get("Profile") or "")
    acodec = str(audio.get("Codec") or "").lower()

    audio_label = ""
    combined_audio = f"{adisplay} {aprofile}".lower()
    if "dts-hd ma" in combined_audio or "dts hd ma" in combined_audio:
        audio_label = "DTS-HD MA"
    elif "dts-hd" in combined_audio or "dts hd" in combined_audio:
        audio_label = "DTS-HD"
    elif "truehd" in combined_audio:
        audio_label = "TrueHD"
    elif "e-ac-3" in combined_audio or "eac3" in combined_audio or acodec in ("eac3", "e-ac-3"):
        audio_label = "E-AC-3"
    elif "ac-3" in combined_audio or acodec in ("ac3", "ac-3"):
        audio_label = "AC-3"
    elif "dts" in combined_audio or acodec == "dts":
        audio_label = "DTS"
    elif "flac" in combined_audio or acodec == "flac":
        audio_label = "FLAC"
    elif "aac" in combined_audio or acodec == "aac":
        audio_label = "AAC"
    elif acodec:
        audio_label = acodec.upper()

    if audio_label:
        parts.append(audio_label)

    channels = audio.get("Channels")
    layout = str(audio.get("ChannelLayout") or "").lower()
    channel_label = ""
    try:
        ch = int(channels) if channels is not None else 0
    except Exception:
        ch = 0
    if ch == 8:
        channel_label = "7.1"
    elif ch == 7:
        channel_label = "6.1"
    elif ch == 6:
        channel_label = "5.1"
    elif ch == 2:
        channel_label = "2.0"
    elif ch == 1:
        channel_label = "1.0"
    elif "7.1" in layout:
        channel_label = "7.1"
    elif "5.1" in layout:
        channel_label = "5.1"
    if channel_label:
        parts.append(channel_label)

    # De-duplicate while preserving order.
    out = []
    for part in parts:
        if part and part not in out:
            out.append(part)
    return " ".join(out)


def format_caption(item: dict):
    typ = item.get("Type") or ""
    name = item.get("Name") or "新媒体"
    year = item.get("ProductionYear")
    series = item.get("SeriesName")
    season = item.get("ParentIndexNumber")
    episode = item.get("IndexNumber")

    type_lower = typ.lower()
    is_episode = type_lower == "episode"
    is_tvshow = type_lower in ("episode", "series", "season")
    if is_episode:
        title = f"🎬 <b>{html.escape(series or name)}</b>"
        ep_parts = ["TVshow"]
        if season is not None:
            try:
                ep_parts.append(f"S{int(season):02d}季")
            except Exception:
                ep_parts.append(f"S{season}季")
        if episode is not None:
            try:
                ep_parts.append(f"E{int(episode):02d}集")
            except Exception:
                ep_parts.append(f"E{episode}集")
        if name and name != series:
            ep_parts.append(html.escape(name))
        title += "\n📺 " + " · ".join(ep_parts)
    else:
        title = f"🎬 <b>{html.escape(name)}</b>"
        if year:
            title += f" ({year})"

    media_sources = item.get("MediaSources") or []
    ms = media_sources[0] if media_sources else {}
    streams = ms.get("MediaStreams") or item.get("MediaStreams") or []
    video = next((x for x in streams if str(x.get("Type") or "").lower() == "video"), {})
    # Prefer default audio, otherwise first audio stream.
    audios = [x for x in streams if str(x.get("Type") or "").lower() == "audio"]
    audio = next((x for x in audios if x.get("IsDefault")), audios[0] if audios else {})

    size = bytes_size(ms.get("Size") or item.get("Size"))
    quality = detect_source_quality(item, ms, video, audio)

    lines = [title, "", "📥 <b>Emby 新媒体入库</b>"]
    if is_tvshow:
        lines.append("🏷 类型：TVshow")
    elif typ:
        lines.append(f"🏷 类型：{html.escape(typ)}")
    if quality:
        lines.append(f"🌟 质量：{html.escape(quality)}")
    if size:
        lines.append(f"💾 大小：{size}")
    return "\n".join(lines)


async def find_library_id(server_id: int, server: dict, item: dict) -> Optional[str]:
    conn = db()
    libs = conn.execute("SELECT * FROM libraries WHERE server_id=?", (server_id,)).fetchall()
    conn.close()
    lib_ids = {str(x["id"]) for x in libs}

    candidates = []
    for key in ("LibraryId", "CollectionFolderId", "TopParentId"):
        if item.get(key):
            candidates.append(str(item[key]))
    candidates += [str(x) for x in (item.get("AncestorIds") or [])]
    for c in candidates:
        if c in lib_ids:
            return c

    p = (item.get("Path") or "").replace("\\", "/").lower()
    if p:
        best, best_len = None, -1
        for lib in libs:
            for lp in json.loads(lib["paths_json"] or "[]"):
                lpn = lp.replace("\\", "/").rstrip("/").lower()
                if lpn and p.startswith(lpn) and len(lpn) > best_len:
                    best, best_len = lib["id"], len(lpn)
        if best:
            return best

    if item.get("Id"):
        try:
            ancestors = await emby_get(server, f"/Items/{item['Id']}/Ancestors")
            for a in ancestors or []:
                aid = str(a.get("Id") or "")
                if aid in lib_ids:
                    return aid
        except Exception:
            pass
    return None


async def download_poster(server: dict, item: dict):
    item_id = item.get("Id")
    if not item_id:
        return None
    url = f"{normalize_url(server['emby_url'])}/emby/Items/{item_id}/Images/Primary"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                url,
                params={"MaxWidth": 900, "Quality": 90},
                headers={"X-Emby-Token": server["emby_api_key"]}
            )
            if r.status_code == 200 and r.content:
                return r.content
    except Exception:
        return None
    return None


async def _get_user_item_details(server: dict, item_id: str):
    """Return (user_id, full_item) using an Emby user-scoped Item endpoint."""
    try:
        users = await emby_get(server, "/Users")
    except Exception:
        users = []

    if not isinstance(users, list):
        return None, None

    # Try every visible user. A library can be hidden from one user but visible to another.
    for user in users:
        user_id = str((user or {}).get("Id") or "").strip()
        if not user_id:
            continue
        try:
            full = await emby_get(
                server,
                f"/Users/{user_id}/Items/{item_id}?Fields=MediaSources,MediaStreams,Path,Overview"
            )
            if isinstance(full, dict) and str(full.get("Id") or "") == str(item_id):
                return user_id, full
        except Exception:
            continue
    return None, None


async def _get_playback_info(server: dict, item_id: str, user_id: str):
    if not item_id or not user_id:
        return None
    try:
        data = await emby_get(
            server,
            f"/Items/{item_id}/PlaybackInfo?UserId={user_id}"
        )
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _media_details_are_useful(item: dict) -> bool:
    sources = item.get("MediaSources") or []
    if not sources:
        return bool(item.get("MediaStreams"))
    source = sources[0] or {}
    streams = source.get("MediaStreams") or item.get("MediaStreams") or []
    size = source.get("Size") or item.get("Size") or 0
    return bool(streams or size)


async def enrich_item_for_notification(server: dict, item: dict) -> dict:
    """
    Complete the technical media data used by Telegram notifications.

    Emby library.new webhooks are often minimal, especially for .strm items.
    For those items the normal user-scoped Item API can still return Size=0 and
    no streams, while PlaybackInfo contains the resolved MP4/MKV size and
    MediaStreams. Therefore the fallback order is:

      webhook -> /Users/{user}/Items/{item} -> /Items/{item}/PlaybackInfo
    """
    if not isinstance(item, dict):
        return {}

    merged = dict(item)
    item_id = str(item.get("Id") or "").strip()
    if not item_id:
        return merged

    # Webhook already has real technical data: no extra API round-trip needed.
    if _media_details_are_useful(merged):
        return merged

    user_id, full = await _get_user_item_details(server, item_id)
    if isinstance(full, dict):
        for key, value in full.items():
            if value is not None:
                merged[key] = value

    # Critical .strm fallback: PlaybackInfo resolves the real file and probes it.
    if not _media_details_are_useful(merged) and user_id:
        playback = await _get_playback_info(server, item_id, user_id)
        if isinstance(playback, dict):
            playback_sources = playback.get("MediaSources") or []
            if playback_sources:
                merged["MediaSources"] = playback_sources
                first = playback_sources[0] or {}
                if first.get("MediaStreams"):
                    merged["MediaStreams"] = first.get("MediaStreams")
                if first.get("Size"):
                    merged["Size"] = first.get("Size")
                # Keep the original .strm Path for library matching, but use the
                # resolved path as an extra quality hint (BluRay/REMUX/WEB-DL etc.).
                if first.get("Path"):
                    merged["ResolvedMediaPath"] = first.get("Path")

    return merged


async def tg_send_text(server: dict, chat_id: str, text: str):
    token = bot_token_for_server(server)
    if not token:
        raise RuntimeError("当前服务器没有可用的 Telegram Bot Token")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(str(data))


async def tg_send(server: dict, chat_id: str, item: dict):
    item = await enrich_item_for_notification(server, item)
    token = bot_token_for_server(server)
    if not token:
        raise RuntimeError("当前服务器没有可用的 Telegram Bot Token")
    caption = format_caption(item)
    poster = await download_poster(server, item)
    async with httpx.AsyncClient(timeout=30) as c:
        if poster:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": ("poster.jpg", poster, "image/jpeg")}
            )
        else:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML"}
            )
        r.raise_for_status()
        j = r.json()
        if not j.get("ok"):
            raise RuntimeError(str(j))




def docker_client():
    if docker is None or not Path("/var/run/docker.sock").exists():
        return None
    try:
        return docker.from_env()
    except Exception:
        return None


def get_self_container(client):
    try:
        hostname = os.getenv("HOSTNAME", "")
        if hostname:
            return client.containers.get(hostname)
    except Exception:
        pass

    # Fallback to the configured container name used by docker-compose.yml.
    try:
        return client.containers.get("emby-tg-notifier")
    except Exception:
        return None


def ensure_local_network():
    """
    Create emby-notify-net if needed and make sure this notifier container
    is connected to it. Safe to call repeatedly.
    """
    client = docker_client()
    if not client:
        return False, "Docker socket 不可用"

    try:
        try:
            network = client.networks.get(LOCAL_DOCKER_NETWORK)
        except Exception:
            network = client.networks.create(LOCAL_DOCKER_NETWORK, driver="bridge")

        me = get_self_container(client)
        if me is None:
            return False, "无法识别通知程序容器"

        current = set((me.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
        if LOCAL_DOCKER_NETWORK not in current:
            network.connect(me)
            me.reload()

        return True, LOCAL_DOCKER_NETWORK
    except Exception as e:
        return False, str(e)


def detect_local_emby_containers():
    """
    Detect likely Emby containers and whether they share a network with
    this notifier. This only reads Docker metadata.
    """
    result = []
    client = docker_client()
    if not client:
        return result

    try:
        me = get_self_container(client)
        my_networks = set()
        if me is not None:
            me.reload()
            my_networks = set((me.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())

        for c in client.containers.list():
            if me is not None and c.id == me.id:
                continue

            c.reload()
            attrs = c.attrs or {}
            config = attrs.get("Config") or {}
            image = (config.get("Image") or "").lower()
            name = (c.name or "").lower()
            labels = config.get("Labels") or {}
            ports = ((attrs.get("NetworkSettings") or {}).get("Ports") or {})

            looks_like_emby = (
                "emby" in name
                or "emby" in image
                or any("emby" in str(v).lower() for v in labels.values())
                or "8096/tcp" in ports
            )
            if not looks_like_emby:
                continue

            networks = set(((attrs.get("NetworkSettings") or {}).get("Networks") or {}).keys())
            shared = sorted(my_networks & networks)

            result.append({
                "name": c.name,
                "image": config.get("Image") or "",
                "suggested_url": f"http://{c.name}:8096",
                "shared_networks": shared,
                "can_use_container_name": bool(shared),
                "on_managed_network": LOCAL_DOCKER_NETWORK in networks,
            })
    except Exception:
        return []

    return result


async def connect_local_emby_container(container_name: str):
    """
    One-click setup:
    1) ensure emby-notify-net exists
    2) connect notifier
    3) connect selected Emby container
    4) test http://<container>:8096 from this notifier container
    """
    client = docker_client()
    if not client:
        raise RuntimeError("Docker socket 不可用，无法自动连接本机容器")

    ok, msg = ensure_local_network()
    if not ok:
        raise RuntimeError(f"通知程序加入 Docker 网络失败：{msg}")

    try:
        network = client.networks.get(LOCAL_DOCKER_NETWORK)
        target = client.containers.get(container_name)
        target.reload()
        networks = set((target.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
        if LOCAL_DOCKER_NETWORK not in networks:
            network.connect(target)
            target.reload()
    except Exception as e:
        raise RuntimeError(f"Emby 容器加入 Docker 网络失败：{e}")

    test_url = f"http://{container_name}:8096"
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(test_url)
            # Emby root may redirect or return 2xx/3xx; both mean networking works.
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
    except Exception as e:
        raise RuntimeError(f"网络已连接，但访问 {test_url} 失败：{e}")

    return test_url


def local_webhook_url(server: dict) -> str:
    # This works when Emby and notifier share a Docker network and this
    # service is reachable by its compose/container name.
    return f"http://emby-tg-notifier:8787/webhook/emby/{server['id']}/{server['webhook_token']}"



async def parse_emby_webhook_request(request: Request):
    """
    Emby can send webhook payloads as either:
      - application/json
      - multipart/form-data, usually with JSON in a field named "data"

    Some Emby/platform combinations have historically emitted multipart bodies
    that generic parsers dislike, so we also keep a raw-body JSON fallback.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    # Standard JSON mode.
    if "application/json" in content_type:
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    raw_body = await request.body()

    # Standard multipart/form-data mode.
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        try:
            form = await request.form()
            candidates = []

            # Current/typical Emby webhook field.
            if "data" in form:
                candidates.append(form.get("data"))

            # A few webhook integrations use payload_json.
            if "payload_json" in form:
                candidates.append(form.get("payload_json"))

            # Fallback: inspect all form values.
            candidates.extend(v for _, v in form.multi_items())

            for value in candidates:
                if value is None:
                    continue

                if hasattr(value, "read"):
                    try:
                        value = await value.read()
                    except Exception:
                        continue

                if isinstance(value, bytes):
                    value = value.decode("utf-8", "ignore")

                if isinstance(value, str):
                    value = value.strip()
                    if not value:
                        continue
                    try:
                        payload = json.loads(value)
                        if isinstance(payload, dict):
                            return payload
                    except Exception:
                        pass
        except Exception:
            # Continue to raw-body fallback below.
            pass

    # Raw body fallback.
    text = raw_body.decode("utf-8", "ignore").strip()
    if text:
        # Sometimes the whole body is JSON despite the declared content type.
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

        # Multipart fallback: find a JSON object embedded inside the body.
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(text[i:])
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue

    raise ValueError("无法解析 Emby Webhook 请求内容")


def extract_event_and_item(payload):
    event = (
        payload.get("Event")
        or payload.get("event")
        or payload.get("NotificationType")
        or payload.get("Type")
        or ""
    )
    item = payload.get("Item") or payload.get("item")
    if not isinstance(item, dict):
        data = payload.get("Data")
        if isinstance(data, dict):
            item = data.get("Item") or data.get("item") or data
    return str(event), item if isinstance(item, dict) else {}


@app.on_event("startup")
def startup():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    init_db()
    # Best-effort: on every container start/recreate, automatically reconnect
    # the notifier itself to emby-notify-net. No SSH command is required.
    ensure_local_network()


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, msg: str = ""):
    if request.session.get("logged_in"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "msg": msg})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    s = get_settings()
    ok, needs_upgrade = verify_password(password, s["password_hash"])
    if username == s["username"] and ok:
        # Transparently migrate old v2 hashes after a successful login.
        if needs_upgrade:
            conn = db()
            conn.execute(
                "UPDATE app_settings SET password_hash=? WHERE id=1",
                (hash_password(password),)
            )
            conn.commit()
            conn.close()

        request.session.clear()
        request.session["logged_in"] = True
        request.session["username"] = username
        return RedirectResponse("/", status_code=303)

    return RedirectResponse("/login?msg=账号或密码错误", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, server_id: Optional[int] = None, msg: str = ""):
    if not request.session.get("logged_in"):
        return RedirectResponse("/login", status_code=303)

    conn = db()
    servers = conn.execute("SELECT * FROM servers ORDER BY id").fetchall()
    if not servers:
        conn.close()
        return HTMLResponse("No server")
    if server_id is None:
        server_id = servers[0]["id"]
    server = conn.execute("SELECT * FROM servers WHERE id=?", (server_id,)).fetchone()
    if not server:
        server = servers[0]
        server_id = server["id"]

    libraries = conn.execute(
        "SELECT * FROM libraries WHERE server_id=? ORDER BY name", (server_id,)
    ).fetchall()
    routes = conn.execute("""
      SELECT r.*, l.name library_name
      FROM routes r
      LEFT JOIN libraries l ON l.server_id=r.server_id AND l.id=r.library_id
      WHERE r.server_id=?
      ORDER BY r.id DESC
    """, (server_id,)).fetchall()
    settings = conn.execute("SELECT * FROM app_settings WHERE id=1").fetchone()
    webhook_status = conn.execute(
        "SELECT * FROM webhook_status WHERE server_id=?",
        (server_id,)
    ).fetchone()
    conn.close()

    webhook_url = f"{external_base_url(request)}/webhook/emby/{server_id}/{server['webhook_token']}"
    webhook_local_url = local_webhook_url(dict(server))
    local_emby_containers = detect_local_emby_containers()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "servers": servers,
        "server": server,
        "libraries": libraries,
        "routes": routes,
        "settings": settings,
        "webhook_url": webhook_url,
        "webhook_local_url": webhook_local_url,
        "local_emby_containers": local_emby_containers,
        "webhook_status": webhook_status,
        "msg": msg
    })


@app.post("/servers/add")
async def add_server(request: Request, name: str = Form("新 Emby")):
    require_login(request)
    conn = db()
    cur = conn.execute(
        "INSERT INTO servers(name,webhook_token) VALUES(?,?)",
        (name.strip() or "新 Emby", make_webhook_token())
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return RedirectResponse(f"/?server_id={sid}&msg=已新增服务器页面", status_code=303)



@app.post("/servers/{server_id}/local-emby/connect")
async def connect_local_emby(
    request: Request,
    server_id: int,
    container_name: str = Form(...)
):
    require_login(request)
    try:
        url = await connect_local_emby_container(container_name.strip())
        conn = db()
        conn.execute("UPDATE servers SET emby_url=? WHERE id=?", (url, server_id))
        conn.commit()
        conn.close()
        return RedirectResponse(
            f"/?server_id={server_id}&msg=本机 Emby 已连接成功，地址已自动填写：{url}",
            status_code=303
        )
    except Exception as e:
        return RedirectResponse(
            f"/?server_id={server_id}&msg=连接本机 Emby 失败：{e}",
            status_code=303
        )


@app.post("/servers/{server_id}/save")
async def save_server(
    request: Request,
    server_id: int,
    name: str = Form(...),
    emby_url: str = Form(...),
    emby_api_key: str = Form(...),
    bot_token_override: str = Form(""),
    send_test_to_telegram: Optional[str] = Form(None)
):
    require_login(request)
    clean_name = name.strip()
    conn = db()
    conn.execute("""
      UPDATE servers
      SET name=?, emby_url=?, emby_api_key=?, bot_token_override=?, send_test_to_telegram=?
      WHERE id=?
    """, (
        clean_name,
        normalize_url(emby_url),
        emby_api_key.strip(),
        bot_token_override.strip(),
        1 if send_test_to_telegram else 0,
        server_id
    ))
    conn.commit()
    conn.close()
    return success_response(
        request,
        "服务器设置已保存",
        server_id=server_id,
        server_name=clean_name
    )


@app.post("/servers/{server_id}/delete")
async def delete_server(request: Request, server_id: int):
    require_login(request)
    conn = db()
    conn.execute("DELETE FROM routes WHERE server_id=?", (server_id,))
    conn.execute("DELETE FROM libraries WHERE server_id=?", (server_id,))
    conn.execute("DELETE FROM servers WHERE id=?", (server_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/?msg=服务器页面已删除", status_code=303)


@app.post("/servers/{server_id}/rotate-webhook")
async def rotate_webhook(request: Request, server_id: int):
    require_login(request)
    token = make_webhook_token()
    conn = db()
    conn.execute("UPDATE servers SET webhook_token=? WHERE id=?", (token, server_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/?server_id={server_id}&msg=Webhook 地址已重新生成，旧地址立即失效", status_code=303)


@app.post("/settings/bot")
async def save_global_bot(request: Request, global_bot_token: str = Form("")):
    require_login(request)
    conn = db()
    conn.execute("UPDATE app_settings SET global_bot_token=? WHERE id=1", (global_bot_token.strip(),))
    conn.commit()
    conn.close()
    sid_raw = request.query_params.get("server_id", "")
    try:
        sid = int(sid_raw)
    except Exception:
        sid = None
    return success_response(request, "通知 Telegram Bot 已保存", server_id=sid)


@app.post("/settings/login")
async def save_login(
    request: Request,
    username: str = Form(...),
    current_password: str = Form(...),
    new_password: str = Form(""),
    confirm_password: str = Form("")
):
    require_login(request)
    s = get_settings()

    ok, _ = verify_password(current_password, s["password_hash"])
    if not ok:
        return failure_response(request, "当前密码不正确，登录设置未修改")

    username = username.strip()
    if not username:
        return failure_response(request, "登录账号不能为空")

    wants_password_change = bool(new_password or confirm_password)
    if wants_password_change:
        if len(new_password) < 6:
            return failure_response(request, "新密码至少 6 位")
        if new_password != confirm_password:
            return failure_response(request, "两次输入的新密码不一致")

    conn = db()
    if wants_password_change:
        conn.execute(
            "UPDATE app_settings SET username=?, password_hash=? WHERE id=1",
            (username, hash_password(new_password))
        )
    else:
        conn.execute(
            "UPDATE app_settings SET username=? WHERE id=1",
            (username,)
        )
    conn.commit()
    conn.close()

    if wants_password_change:
        request.session.clear()
        if wants_json_response(request):
            return JSONResponse({
                "ok": True,
                "message": "密码已修改，请使用新密码重新登录",
                "logout_required": True,
                "redirect": "/login?msg=密码已修改，请使用新密码重新登录"
            })
        return RedirectResponse(
            "/login?msg=密码已修改，请使用新密码重新登录",
            status_code=303
        )

    request.session["username"] = username
    return success_response(request, "登录账号已保存")


@app.post("/libraries/{server_id}/refresh")
async def refresh(request: Request, server_id: int):
    require_login(request)
    try:
        n = await refresh_libraries(server_id)
        msg = f"已刷新媒体库，共 {n} 个"
    except Exception as e:
        msg = f"刷新失败：{e}"
    return RedirectResponse(f"/?server_id={server_id}&msg={msg}", status_code=303)


@app.post("/routes/{server_id}/add")
async def add_route(
    request: Request,
    server_id: int,
    name: str = Form(...),
    library_id: str = Form(...),
    chat_id: str = Form(...)
):
    require_login(request)
    conn = db()
    conn.execute(
        "INSERT INTO routes(server_id,name,library_id,chat_id,enabled) VALUES(?,?,?,?,1)",
        (server_id, name.strip(), library_id, chat_id.strip())
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/?server_id={server_id}&msg=通知任务已添加", status_code=303)


@app.post("/routes/{server_id}/{route_id}/toggle")
async def toggle_route(request: Request, server_id: int, route_id: int):
    require_login(request)
    conn = db()
    conn.execute(
        "UPDATE routes SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id=? AND server_id=?",
        (route_id, server_id)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/?server_id={server_id}&msg=任务状态已更新", status_code=303)


@app.post("/routes/{server_id}/{route_id}/delete")
async def delete_route(request: Request, server_id: int, route_id: int):
    require_login(request)
    conn = db()
    conn.execute("DELETE FROM routes WHERE id=? AND server_id=?", (route_id, server_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/?server_id={server_id}&msg=任务已删除", status_code=303)


@app.post("/telegram/test/{server_id}")
async def test_tg(request: Request, server_id: int, chat_id: str = Form(...)):
    require_login(request)
    server = get_server(server_id)
    fake = {
        "Id": "",
        "Type": "Movie",
        "Name": f"{server['name']} Telegram 测试",
        "ProductionYear": 2026,
    }
    try:
        await tg_send(server, chat_id.strip(), fake)
        msg = "Telegram 测试发送成功"
    except Exception as e:
        msg = f"Telegram 测试失败：{e}"
    return RedirectResponse(f"/?server_id={server_id}&msg={msg}", status_code=303)


@app.post("/webhook/emby/{server_id}/{token}")
async def webhook(server_id: int, token: str, request: Request):
    server = get_server(server_id)
    if not server or not secrets.compare_digest(token, server["webhook_token"]):
        raise HTTPException(status_code=404)

    try:
        payload = await parse_emby_webhook_request(request)
    except Exception as e:
        raw = await request.body()
        update_webhook_status(server_id, "parse.error", detail=f"Webhook 解析失败：{e}")
        return JSONResponse(
            {
                "ok": False,
                "error": "无法解析 Emby Webhook 请求",
                "detail": str(e),
                "content_type": request.headers.get("content-type", ""),
                "raw": raw[:500].decode("utf-8", "ignore")
            },
            status_code=400
        )

    try:
        Path(WEBHOOK_LOG_DIR).mkdir(parents=True, exist_ok=True)
        Path(f"{WEBHOOK_LOG_DIR}/server_{server_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    event, item = extract_event_and_item(payload)
    low = event.lower()

    source_name = ""
    if isinstance(payload.get("Server"), dict):
        source_name = payload["Server"].get("Name") or ""
    source_name = source_name or server.get("name") or ""

    # Emby 4.9 test notification:
    #   system.notificationtest
    # Some versions/plugins may use system.webhooktest.
    is_test_event = (
        low == "system.notificationtest"
        or "notificationtest" in low
        or "webhooktest" in low
    )
    if is_test_event:
        telegram_count = 0
        telegram_errors = []

        if int(server.get("send_test_to_telegram") or 0):
            conn = db()
            route_rows = conn.execute(
                "SELECT DISTINCT chat_id FROM routes WHERE server_id=? AND enabled=1",
                (server_id,)
            ).fetchall()
            conn.close()

            text = (
                "✅ <b>Emby Webhook 测试成功</b>\n\n"
                f"服务器：{html.escape(source_name)}\n"
                f"事件：<code>{html.escape(event)}</code>\n"
                "连接：Emby → 通知程序正常"
            )
            for row in route_rows:
                try:
                    await tg_send_text(server, row["chat_id"], text)
                    telegram_count += 1
                except Exception as e:
                    telegram_errors.append(str(e))

        detail = "Emby 测试通知接收成功"
        if int(server.get("send_test_to_telegram") or 0):
            detail += f"，Telegram 已发送 {telegram_count} 个频道"
            if telegram_errors:
                detail += f"，失败 {len(telegram_errors)} 个"

        update_webhook_status(
            server_id,
            event,
            source_name=source_name,
            is_test=True,
            telegram_count=telegram_count,
            detail=detail
        )
        return {
            "ok": True,
            "test": True,
            "event": event,
            "server_id": server_id,
            "telegram_count": telegram_count
        }

    is_new = (
        "library.new" in low
        or "itemadded" in low
        or "new media" in low
        or (not event and bool(item))
    )

    if not is_new:
        update_webhook_status(
            server_id,
            event,
            source_name=source_name,
            detail="事件已收到，但不是已配置的入库事件"
        )
        return {"ok": True, "ignored": True, "event": event}

    if not item:
        update_webhook_status(
            server_id,
            event,
            source_name=source_name,
            detail="入库事件已收到，但未找到 Item 数据"
        )
        return {"ok": True, "ignored": True, "reason": "no item"}

    library_id = await find_library_id(server_id, server, item)
    if not library_id:
        update_webhook_status(
            server_id,
            event,
            source_name=source_name,
            detail=f"入库事件已收到，但无法匹配媒体库：{item.get('Name') or ''}"
        )
        return {
            "ok": True,
            "ignored": True,
            "reason": "library_not_matched",
            "item": item.get("Name")
        }

    conn = db()
    routes = conn.execute(
        "SELECT * FROM routes WHERE server_id=? AND enabled=1 AND library_id=?",
        (server_id, library_id)
    ).fetchall()
    conn.close()

    results = []
    sent_count = 0
    for r in routes:
        try:
            await tg_send(server, r["chat_id"], item)
            sent_count += 1
            results.append({"route": r["id"], "ok": True})
        except Exception as e:
            results.append({"route": r["id"], "ok": False, "error": str(e)})

    update_webhook_status(
        server_id,
        event,
        source_name=source_name,
        telegram_count=sent_count,
        detail=f"入库事件处理完成，匹配媒体库 {library_id}，Telegram 成功发送 {sent_count} 个任务"
    )

    return {
        "ok": True,
        "server_id": server_id,
        "event": event,
        "library_id": library_id,
        "routes": results
    }


@app.get("/api/servers/{server_id}/webhook-status")
async def webhook_status_api(request: Request, server_id: int):
    require_login(request)
    conn = db()
    row = conn.execute(
        "SELECT * FROM webhook_status WHERE server_id=?",
        (server_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"ok": True, "status": None}
    return {"ok": True, "status": dict(row)}


@app.get("/health")
def health():
    return {"ok": True}
