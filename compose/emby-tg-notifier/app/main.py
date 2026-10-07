import os
import base64
import json
import asyncio
import time
import html
import sqlite3
import secrets
import hashlib
import hmac
import re
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote

import httpx
try:
    import docker
except Exception:
    docker = None
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

DB_PATH = os.getenv("DB_PATH", "/data/app.db")
SESSION_SECRET_FILE = os.getenv("SESSION_SECRET_FILE", "/data/session_secret")
WEBHOOK_LOG_DIR = "/data/webhooks"
LOCAL_DOCKER_NETWORK = "emby-notify-net"

# Keep strong references to delayed cleanup tasks.  asyncio only keeps weak
# references to tasks created with create_task(); without this set a 10-second
# Telegram cleanup task can be garbage-collected before it runs.
BACKGROUND_TASKS: set[asyncio.Task] = set()

def spawn_background(coro):
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task

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
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


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
      global_bot_token TEXT DEFAULT '',
      binding_admin_ids TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS servers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      emby_url TEXT NOT NULL DEFAULT '',
      emby_api_key TEXT NOT NULL DEFAULT '',
      bot_token_override TEXT NOT NULL DEFAULT '',
      webhook_token TEXT NOT NULL UNIQUE,
      send_test_to_telegram INTEGER NOT NULL DEFAULT 0,
      senplayer_emby_url TEXT NOT NULL DEFAULT '',
      notifier_public_url TEXT NOT NULL DEFAULT '',
      senplayer_user TEXT NOT NULL DEFAULT '',
      tv_batch_minutes INTEGER NOT NULL DEFAULT 30,
      tg_binding_enabled INTEGER NOT NULL DEFAULT 0,
      tg_binding_bot_id TEXT NOT NULL DEFAULT '',
      tg_binding_bot_token TEXT NOT NULL DEFAULT '',
      tg_binding_admin_ids TEXT NOT NULL DEFAULT '',
      senplayer_progress_sync INTEGER NOT NULL DEFAULT 0
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

    CREATE TABLE IF NOT EXISTS tv_batches(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      server_id INTEGER NOT NULL,
      route_id INTEGER NOT NULL,
      chat_id TEXT NOT NULL,
      series_key TEXT NOT NULL,
      series_name TEXT NOT NULL DEFAULT '',
      season_key TEXT NOT NULL DEFAULT '',
      episodes_json TEXT NOT NULL DEFAULT '{}',
      message_ids_json TEXT NOT NULL DEFAULT '[]',
      last_item_json TEXT NOT NULL DEFAULT '{}',
      last_seen_at REAL NOT NULL DEFAULT 0,
      created_at REAL NOT NULL DEFAULT 0,
      UNIQUE(server_id, route_id, series_key, season_key)
    );

    CREATE TABLE IF NOT EXISTS tg_bindings(
      server_id INTEGER NOT NULL,
      tg_user_id INTEGER NOT NULL,
      tg_username TEXT NOT NULL DEFAULT '',
      tg_display_name TEXT NOT NULL DEFAULT '',
      emby_user_id TEXT NOT NULL,
      emby_username TEXT NOT NULL,
      created_at REAL NOT NULL DEFAULT 0,
      updated_at REAL NOT NULL DEFAULT 0,
      PRIMARY KEY(server_id, tg_user_id)
    );

    CREATE TABLE IF NOT EXISTS tg_bind_states(
      bot_id TEXT NOT NULL,
      tg_user_id INTEGER NOT NULL,
      server_id INTEGER NOT NULL DEFAULT 0,
      state TEXT NOT NULL DEFAULT '',
      pending_username TEXT NOT NULL DEFAULT '',
      message_ids TEXT NOT NULL DEFAULT '[]',
      updated_at REAL NOT NULL DEFAULT 0,
      PRIMARY KEY(bot_id, tg_user_id)
    );

    CREATE TABLE IF NOT EXISTS tg_bot_offsets(
      bot_id TEXT PRIMARY KEY,
      next_offset INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS senplayer_tickets(
      token TEXT PRIMARY KEY,
      server_id INTEGER NOT NULL,
      item_id TEXT NOT NULL,
      tg_user_id INTEGER NOT NULL,
      expires_at REAL NOT NULL,
      used_at REAL NOT NULL DEFAULT 0,
      created_at REAL NOT NULL,
      tg_chat_id TEXT NOT NULL DEFAULT '',
      tg_message_id INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS tg_cleanup_jobs(
      token_hash TEXT NOT NULL,
      chat_id TEXT NOT NULL,
      message_id INTEGER NOT NULL,
      due_at REAL NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(token_hash, chat_id, message_id)
    );
    """)
    # Schema migration for existing installations.
    server_columns = {r["name"] for r in conn.execute("PRAGMA table_info(servers)").fetchall()}
    if "send_test_to_telegram" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN send_test_to_telegram INTEGER NOT NULL DEFAULT 0")
    if "senplayer_emby_url" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN senplayer_emby_url TEXT NOT NULL DEFAULT ''")
    if "notifier_public_url" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN notifier_public_url TEXT NOT NULL DEFAULT ''")
    if "senplayer_user" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN senplayer_user TEXT NOT NULL DEFAULT ''")
    if "tv_batch_minutes" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN tv_batch_minutes INTEGER NOT NULL DEFAULT 30")
    if "tg_binding_enabled" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN tg_binding_enabled INTEGER NOT NULL DEFAULT 0")
    if "tg_binding_bot_id" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN tg_binding_bot_id TEXT NOT NULL DEFAULT ''")
    if "tg_binding_bot_token" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN tg_binding_bot_token TEXT NOT NULL DEFAULT ''")
    ticket_columns = {r["name"] for r in conn.execute("PRAGMA table_info(senplayer_tickets)").fetchall()}
    if "player" not in ticket_columns:
        conn.execute("ALTER TABLE senplayer_tickets ADD COLUMN player TEXT NOT NULL DEFAULT 'sp'")
    if "tg_chat_id" not in ticket_columns:
        conn.execute("ALTER TABLE senplayer_tickets ADD COLUMN tg_chat_id TEXT NOT NULL DEFAULT ''")
    if "tg_message_id" not in ticket_columns:
        conn.execute("ALTER TABLE senplayer_tickets ADD COLUMN tg_message_id INTEGER NOT NULL DEFAULT 0")
    if "tg_binding_admin_ids" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN tg_binding_admin_ids TEXT NOT NULL DEFAULT ''")
    if "senplayer_progress_sync" not in server_columns:
        conn.execute("ALTER TABLE servers ADD COLUMN senplayer_progress_sync INTEGER NOT NULL DEFAULT 0")
    bind_state_columns = {r["name"] for r in conn.execute("PRAGMA table_info(tg_bind_states)").fetchall()}
    if "message_ids" not in bind_state_columns:
        conn.execute("ALTER TABLE tg_bind_states ADD COLUMN message_ids TEXT NOT NULL DEFAULT '[]'")

    app_columns = {r["name"] for r in conn.execute("PRAGMA table_info(app_settings)").fetchall()}
    if "binding_admin_ids" not in app_columns:
        conn.execute("ALTER TABLE app_settings ADD COLUMN binding_admin_ids TEXT NOT NULL DEFAULT ''")

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
    if host:
        return f"{proto or request.url.scheme}://{host}".rstrip("/")
    return f"{request.url.scheme}://{request.headers.get('host')}".rstrip("/")


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


def binding_bot_token_for_server(server: dict) -> str:
    """Bot used for TG binding. If an independent token is set, it also becomes
    this server's effective notification bot so channel callbacks return to the same bot.
    """
    token = str(server.get("tg_binding_bot_token") or "").strip()
    return token or bot_token_for_server(server)


def effective_bot_token_for_server(server: dict) -> str:
    # When TG binding is enabled with an independent bot, the same bot must send
    # the channel message; Telegram callback_query always returns to the sending bot.
    if int(server.get("tg_binding_enabled") or 0):
        token = str(server.get("tg_binding_bot_token") or "").strip()
        if token:
            return token
    return bot_token_for_server(server)


def _parse_tg_ids(raw: str) -> set[int]:
    out=set()
    for x in re.split(r"[,，;；\s]+", str(raw or "").strip()):
        if x.isdigit():
            try: out.add(int(x))
            except Exception: pass
    return out


def _binding_admin_ids_for_token(token: str) -> set[int]:
    ids=set()
    conn=db(); rows=conn.execute("SELECT * FROM servers WHERE tg_binding_enabled=1").fetchall(); conn.close()
    for r in rows:
        s=dict(r)
        if binding_bot_token_for_server(s) == token:
            ids |= _parse_tg_ids(s.get("tg_binding_admin_ids") or "")
    # Backward-compatible global admins from v14/v14.1.
    ids |= _binding_admin_ids()
    return ids


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

    if height or width:
        # Cinemascope video is commonly stored as 1920x800-960 or 3840x1600.
        # Classify the source tier using both dimensions instead of treating the
        # cropped picture height as a lower-resolution encode.
        if (width and width >= 3800) or (height and height >= 2000):
            parts.append("2160p")
        elif (width and width >= 1900) or (height and height >= 1000):
            parts.append("1080p")
        elif (width and width >= 1260) or (height and height >= 700):
            parts.append("720p")
        elif height and height >= 500:
            parts.append("576p")
        elif height and height >= 400:
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



def _unique_keep_order(values):
    out = []
    seen = set()
    for value in values:
        value = " ".join(str(value or "").split()).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _item_paths(item: dict):
    values = [
        item.get("Path"),
        item.get("ResolvedMediaPath"),
    ]
    for source in item.get("MediaSources") or []:
        if isinstance(source, dict):
            values.append(source.get("Path"))
    return _unique_keep_order([x for x in values if x])


def _looks_like_jav_code(value: str) -> bool:
    """Conservative JAV code check used only as a secondary hint."""
    base = Path(str(value or "")).stem.upper()
    return bool(re.search(r'(?<![A-Z0-9])[A-Z]{2,10}-?\d{2,6}(?![A-Z0-9])', base))


def is_jav_item(item: dict) -> bool:
    """Identify JAV primarily from the configured media path / JAV metadata."""
    paths = [str(x).replace('\\\\', '/').lower() for x in _item_paths(item)]
    path_markers = (
        '/symedia_jav/', '/media/jav/', '/jav/', '/jav-', '/jav_',
    )
    if any(any(marker in path for marker in path_markers) for path in paths):
        return True

    metadata = []
    for key in ("Genres", "Tags"):
        value = item.get(key) or []
        if isinstance(value, list):
            metadata.extend(str(x) for x in value)
    for key in ("GenreItems", "TagItems"):
        value = item.get(key) or []
        if isinstance(value, list):
            metadata.extend(str((x or {}).get("Name") or "") for x in value if isinstance(x, dict))
    joined = " ".join(metadata)
    if "片商:" in joined or "发行:" in joined:
        return True

    # Secondary hint only: code-like filename + sidecar NFO available.
    original_path = str(item.get("Path") or "")
    if _looks_like_jav_code(original_path):
        nfo = _find_sidecar_nfo(item)
        if nfo:
            return True
    return False


def _find_sidecar_nfo(item: dict):
    """Find NFO beside the Emby .strm/video path. Prefer same basename."""
    for raw_path in _item_paths(item):
        try:
            media_path = Path(str(raw_path))
        except Exception:
            continue
        parent = media_path.parent
        if not parent.exists() or not parent.is_dir():
            continue

        preferred = parent / (media_path.stem + '.nfo')
        if preferred.exists() and preferred.is_file():
            return preferred

        # If a .strm points to an MP4, the sidecar normally shares the title code.
        try:
            candidates = sorted(parent.glob('*.nfo'))
        except Exception:
            candidates = []
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            stem = media_path.stem.casefold()
            for candidate in candidates:
                if candidate.stem.casefold() == stem:
                    return candidate
    return None


def _parse_jav_nfo(nfo_path: Path):
    result = {"actors": [], "directors": [], "tags": []}
    if not nfo_path:
        return result
    try:
        root = ET.parse(str(nfo_path)).getroot()
    except Exception:
        return result

    directors = []
    for node in root.findall('.//director'):
        if node.text:
            directors.append(node.text.strip())
    directors = _unique_keep_order(directors)
    director_keys = {x.casefold() for x in directors}

    actors = []
    for actor in root.findall('.//actor'):
        name_node = actor.find('name')
        name = (name_node.text or '').strip() if name_node is not None else ''
        if name and name.casefold() not in director_keys:
            actors.append(name)
    actors = _unique_keep_order(actors)

    tags = []
    for node in root.findall('./tag'):
        if node.text:
            tags.append(node.text.strip())
    if not tags:
        for node in root.findall('./genre'):
            if node.text:
                tags.append(node.text.strip())

    result["actors"] = actors
    result["directors"] = directors
    result["tags"] = _unique_keep_order(tags)
    return result


def _jav_folder_actor_fallback(item: dict) -> str:
    """
    Folder layout is normally .../<actress>/<code>/<code>.strm.
    Skip the code directory and take its parent. If it explicitly says 多人, keep 多人.
    """
    path = str(item.get("Path") or "").replace('\\\\', '/')
    if not path:
        return "未知"
    try:
        media_path = Path(path)
        code_dir = media_path.parent
        actor_dir = code_dir.parent
        code_name = code_dir.name.strip()
        actor_name = actor_dir.name.strip()
    except Exception:
        return "未知"

    multi_words = {"多人", "多人作品", "多人合集", "合集", "multi", "multiple"}
    for value in (code_name, actor_name):
        if value.casefold() in {x.casefold() for x in multi_words} or "多人" in value:
            return "多人"

    # If the immediate parent is not code-like, it may already be the actress folder.
    if code_name and not _looks_like_jav_code(code_name):
        if code_name.casefold() not in {"h2606", "jav", "movies", "movie"}:
            return code_name

    if actor_name and actor_name.casefold() not in {"h2606", "jav", "movies", "movie", "media"}:
        return actor_name
    return "未知"


def _filter_jav_tags(tags, actors=None, directors=None, max_tags=4):
    actors = actors or []
    directors = directors or []
    names = {x.casefold() for x in actors + directors if x}
    out = []

    # Technical / organization metadata that should not appear after "类型：JAV".
    technical = {
        '4k', '8k', '2160p', '1080p', '720p', 'sd', 'hd', 'uhd',
        'hevc', 'h264', 'h265', 'av1', 'hdr', 'hdr10', 'dolby vision', 'dv',
        '单体作品', '纪录片', '出道作品', '精选合集', '4小时+',
    }

    for tag in tags or []:
        tag = " ".join(str(tag or "").split()).strip()
        if not tag:
            continue
        low = tag.casefold()
        if low in names or low in technical:
            continue
        if tag.startswith(('系列:', '片商:', '发行:', '系列：', '片商：', '发行：')):
            continue
        # Product/label codes such as ROE, IPZZ, SNOS, CJOB.
        if re.fullmatch(r'[A-Za-z]{2,12}', tag):
            continue
        # Code-like tags such as IPZZ-927.
        if _looks_like_jav_code(tag):
            continue
        if tag not in out:
            out.append(tag)
        if len(out) >= max_tags:
            break
    return out


def get_jav_metadata(item: dict):
    nfo_path = _find_sidecar_nfo(item)
    parsed = _parse_jav_nfo(nfo_path) if nfo_path else {"actors": [], "directors": [], "tags": []}

    actors = parsed.get("actors") or []
    if not actors:
        actors = [_jav_folder_actor_fallback(item)]
    actors = _unique_keep_order(actors) or ["未知"]

    tags = _filter_jav_tags(
        parsed.get("tags") or [],
        actors=actors,
        directors=parsed.get("directors") or [],
        max_tags=4,
    )
    return {
        "is_jav": True,
        "actors": actors,
        "tags": tags,
        "nfo_path": str(nfo_path) if nfo_path else "",
    }


def _notification_genres(item: dict):
    values = item.get("NotificationGenres") or item.get("Genres") or []
    if not isinstance(values, list):
        values = re.split(r"[,，;/、]", str(values or ""))
    return _unique_keep_order(values)


def _notification_overview(item: dict) -> str:
    value = item.get("NotificationOverview") or item.get("Overview") or ""
    value = html.unescape(str(value)).replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", value)
    value = re.sub(r"(?i)</\s*(?:p|div|li)\s*>", "\n", value)
    value = re.sub(r"(?i)<\s*li(?:\s[^>]*)?>", "• ", value)
    value = re.sub(r"<[^>]+>", "", value)

    lines = []
    pending_blank = False
    for raw_line in value.split("\n"):
        line = " ".join(raw_line.replace("\u3000", " ").split()).strip()
        if line:
            if pending_blank and lines:
                lines.append("")
            lines.append(line)
            pending_blank = False
        elif lines:
            pending_blank = True
    return "\n".join(lines).strip()


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

    lines = [title]
    jav = None
    if not is_tvshow and is_jav_item(item):
        jav = get_jav_metadata(item)
        jav_tags = jav.get("tags") or []
        genres = jav_tags or _notification_genres(item)
        if genres:
            lines.append(f"🎭 类型：{html.escape('、'.join(genres))}")
        actress_text = "、".join(jav.get("actors") or ["未知"])
        lines.append(f"👩 老湿：{html.escape(actress_text)}")
    else:
        genres = _notification_genres(item)
        if genres:
            lines.append(f"🎭 类型：{html.escape('、'.join(genres))}")
    overview = _notification_overview(item)
    if overview:
        lines.append(f"📝 简介：{html.escape(overview)}")
    lines.extend(["", "📥 <b>Emby 新媒体入库</b>"])
    category = "JAV" if jav else ("TVshow" if is_tvshow else typ)
    if category:
        lines.append(f"🏷 类别：{html.escape(category)}")
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


def _read_sidecar_poster(item: dict):
    media_path = str(item.get("Path") or "").strip()
    if not media_path:
        return None

    path = Path(media_path)
    candidates = [
        path.parent / "poster.jpg",
        path.parent / f"{path.stem}-poster.jpg",
        path.parent / "folder.jpg",
        path.parent / "cover.jpg",
    ]
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            content = candidate.read_bytes()
            if 4 <= len(content) <= 10 * 1024 * 1024 and content.startswith(b"\xff\xd8\xff"):
                return content
        except OSError:
            continue
    return None


async def download_poster(server: dict, item: dict):
    sidecar = _read_sidecar_poster(item)
    if sidecar:
        return sidecar

    item_id = item.get("Id")
    if not item_id:
        return None
    url = f"{normalize_url(server['emby_url'])}/emby/Items/{item_id}/Images/Primary"
    async with httpx.AsyncClient(timeout=20) as c:
        for delay in (0, 2, 5):
            if delay:
                await asyncio.sleep(delay)
            try:
                r = await c.get(
                    url,
                    params={"MaxWidth": 900, "Quality": 90},
                    headers={"X-Emby-Token": server["emby_api_key"]},
                )
                if r.status_code == 200 and r.content:
                    return r.content
            except Exception:
                continue
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
                f"/Users/{user_id}/Items/{item_id}?Fields=MediaSources,MediaStreams,Path,Overview,Genres,Tags,ParentId,SeasonId,SeriesId"
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

    user_id, full = await _get_user_item_details(server, item_id)
    if isinstance(full, dict):
        for key, value in full.items():
            if value is not None:
                merged[key] = value

    # PlaybackInfo resolves the real file behind .strm. It is the most reliable
    # source for size, dimensions, codecs, range and audio layout.
    is_strm = any(str(path).lower().endswith('.strm') for path in _item_paths(merged))
    if user_id and (is_strm or not _media_details_are_useful(merged)):
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

    # Episode NFO summaries are often individual plot text. For TV notifications
    # the requested description is the season NFO, falling back to the series NFO.
    type_lower = str(merged.get("Type") or "").lower()
    if user_id and type_lower in ("episode", "season", "series"):
        season_item = None
        series_item = None
        season_id = str(merged.get("SeasonId") or (merged.get("ParentId") if type_lower == "episode" else "") or "")
        series_id = str(merged.get("SeriesId") or (merged.get("ParentId") if type_lower == "season" else "") or "")
        if season_id:
            try:
                season_item = await emby_get(server, f"/Users/{user_id}/Items/{season_id}?Fields=Overview,Genres")
            except Exception:
                season_item = None
        if series_id:
            try:
                series_item = await emby_get(server, f"/Users/{user_id}/Items/{series_id}?Fields=Overview,Genres")
            except Exception:
                series_item = None
        season_item = season_item if isinstance(season_item, dict) else {}
        series_item = series_item if isinstance(series_item, dict) else {}
        if type_lower == "series":
            merged["NotificationOverview"] = str(merged.get("Overview") or "")
            merged["NotificationGenres"] = merged.get("Genres") or []
        else:
            merged["NotificationOverview"] = str(season_item.get("Overview") or series_item.get("Overview") or "")
            merged["NotificationGenres"] = season_item.get("Genres") or series_item.get("Genres") or merged.get("Genres") or []

    return merged




async def _resolve_senplayer_user(server: dict):
    """Resolve configured Emby user by username or id, using the server API key."""
    wanted = str(server.get("senplayer_user") or "").strip()
    if not wanted:
        return None
    try:
        users = await emby_get(server, "/Users")
    except Exception:
        return None
    for user in users or []:
        uid = str((user or {}).get("Id") or "").strip()
        name = str((user or {}).get("Name") or "").strip()
        if uid == wanted or name.casefold() == wanted.casefold():
            return {"Id": uid, "Name": name}
    return None


async def _senplayer_resume_seconds(server: dict, user_id: str, item_id: str) -> int:
    if not user_id or not item_id:
        return 0
    try:
        item = await emby_get(server, f"/Users/{user_id}/Items/{item_id}?Fields=UserData")
        ud = (item or {}).get("UserData") or {}
        ticks = int(ud.get("PlaybackPositionTicks") or 0)
        return max(0, ticks // 10_000_000)
    except Exception:
        return 0


async def _update_emby_resume(server: dict, user_id: str, item_id: str, position_seconds: int, finished: bool=False):
    if not user_id or not item_id:
        return False
    base = normalize_url(server.get("emby_url") or "")
    api_key = str(server.get("emby_api_key") or "").strip()
    if not base or not api_key:
        return False
    payload = {
        "PlaybackPositionTicks": max(0, int(position_seconds)) * 10_000_000,
        "LastPlayedDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if finished:
        payload["Played"] = True
        payload["PlaybackPositionTicks"] = 0
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{base}/emby/Users/{quote(user_id, safe='')}/Items/{quote(item_id, safe='')}/UserData",
                headers={"X-Emby-Token": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
        return True
    except Exception:
        return False

def _senplayer_signature(server: dict, item_id: str) -> str:
    secret = str(server.get("webhook_token") or "").encode("utf-8")
    msg = f"{server.get('id')}:{item_id}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


def _binding_play_sig(server: dict, item_id: str, tg_user_id: int) -> str:
    secret = str(server.get("webhook_token") or "").encode("utf-8")
    msg = f"bind:{server.get('id')}:{item_id}:{int(tg_user_id)}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


def _binding_callback_sig(server: dict, item_id: str) -> str:
    return _senplayer_signature(server, item_id)[:10]


def _binding_admin_ids() -> set[int]:
    raw = str(get_settings().get("binding_admin_ids") or "")
    out = set()
    for part in re.split(r"[,;\s]+", raw):
        try:
            if part.strip(): out.add(int(part.strip()))
        except Exception:
            pass
    return out


def get_tg_binding(server_id: int, tg_user_id: int):
    conn = db()
    row = conn.execute(
        "SELECT * FROM tg_bindings WHERE server_id=? AND tg_user_id=?",
        (int(server_id), int(tg_user_id)),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_tg_binding(server_id: int, tg_user: dict, emby_user: dict):
    now = time.time()
    conn = db()
    conn.execute("""
      INSERT INTO tg_bindings(server_id,tg_user_id,tg_username,tg_display_name,emby_user_id,emby_username,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(server_id,tg_user_id) DO UPDATE SET
        tg_username=excluded.tg_username,
        tg_display_name=excluded.tg_display_name,
        emby_user_id=excluded.emby_user_id,
        emby_username=excluded.emby_username,
        updated_at=excluded.updated_at
    """, (
        int(server_id), int(tg_user.get("id") or 0), str(tg_user.get("username") or ""),
        " ".join(x for x in [str(tg_user.get("first_name") or ""), str(tg_user.get("last_name") or "")] if x).strip(),
        str(emby_user.get("Id") or ""), str(emby_user.get("Name") or ""), now, now,
    ))
    conn.commit(); conn.close()


def set_bind_state(bot_id: str, tg_user_id: int, state: str, server_id: int=0, pending_username: str="", message_ids=None):
    conn = db()
    if not state:
        conn.execute("DELETE FROM tg_bind_states WHERE bot_id=? AND tg_user_id=?", (str(bot_id), int(tg_user_id)))
    else:
        if message_ids is None:
            old = conn.execute(
                "SELECT message_ids FROM tg_bind_states WHERE bot_id=? AND tg_user_id=?",
                (str(bot_id), int(tg_user_id))
            ).fetchone()
            raw_ids = old["message_ids"] if old else "[]"
        else:
            raw_ids = json.dumps([int(x) for x in message_ids if int(x) > 0])
        conn.execute("""
          INSERT INTO tg_bind_states(bot_id,tg_user_id,server_id,state,pending_username,message_ids,updated_at)
          VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(bot_id,tg_user_id) DO UPDATE SET
            server_id=excluded.server_id,state=excluded.state,pending_username=excluded.pending_username,
            message_ids=excluded.message_ids,updated_at=excluded.updated_at
        """, (str(bot_id), int(tg_user_id), int(server_id), state, pending_username, raw_ids, time.time()))
    conn.commit(); conn.close()


def get_bind_state(bot_id: str, tg_user_id: int):
    conn=db(); row=conn.execute("SELECT * FROM tg_bind_states WHERE bot_id=? AND tg_user_id=?", (str(bot_id), int(tg_user_id))).fetchone(); conn.close()
    return dict(row) if row else None


def bind_message_ids(bot_id: str, tg_user_id: int) -> list[int]:
    st = get_bind_state(bot_id, tg_user_id)
    if not st:
        return []
    try:
        vals = json.loads(st.get("message_ids") or "[]")
    except Exception:
        vals = []
    out=[]
    for v in vals if isinstance(vals, list) else []:
        try:
            iv=int(v)
            if iv>0 and iv not in out: out.append(iv)
        except Exception:
            pass
    return out


def track_bind_message(bot_id: str, tg_user_id: int, message_id) -> None:
    try:
        mid=int(message_id or 0)
    except Exception:
        mid=0
    if mid<=0:
        return
    st=get_bind_state(bot_id,tg_user_id)
    if not st:
        return
    ids=bind_message_ids(bot_id,tg_user_id)
    if mid not in ids:
        ids.append(mid)
    set_bind_state(bot_id,tg_user_id,str(st.get("state") or ""),int(st.get("server_id") or 0),str(st.get("pending_username") or ""),ids)


async def cleanup_bind_messages(token: str, chat_id, bot_id: str, tg_user_id: int, extra_ids=None):
    ids=bind_message_ids(bot_id,tg_user_id)
    for x in (extra_ids or []):
        try:
            ix=int(x or 0)
            if ix>0 and ix not in ids: ids.append(ix)
        except Exception:
            pass
    for mid in ids:
        await bot_delete_message(token,chat_id,mid)


def servers_for_binding_bot(token: str, actual_bot_id: str="") -> list[dict]:
    conn=db(); rows=conn.execute("SELECT * FROM servers WHERE tg_binding_enabled=1 ORDER BY id").fetchall(); conn.close()
    out=[]
    for r in rows:
        s=dict(r)
        if binding_bot_token_for_server(s) != token:
            continue
        out.append(s)
    return out


async def authenticate_emby_credentials(server: dict, username: str, password: str):
    base=normalize_url(server.get("emby_url") or "")
    if not base: return None
    auth='Emby Client="TG Binding Bot", Device="Telegram", DeviceId="emby-tg-notifier", Version="14.6"'
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.post(
                f"{base}/emby/Users/AuthenticateByName",
                headers={"X-Emby-Authorization": auth, "Content-Type": "application/json"},
                json={"Username": username, "Pw": password},
            )
            if r.status_code != 200:
                return None
            data=r.json() or {}
            user=data.get("User") or {}
            if isinstance(user, list): user=user[0] if user else {}
            uid=str(user.get("Id") or "").strip()
            if not uid: return None
            # We intentionally do not persist the password or user access token.
            token=str(data.get("AccessToken") or "")
            if token:
                try:
                    await c.post(f"{base}/emby/Sessions/Logout", headers={"X-Emby-Token": token, "X-Emby-Authorization": auth})
                except Exception:
                    pass
            return {"Id": uid, "Name": str(user.get("Name") or username)}
    except Exception:
        return None


def senplayer_button(server: dict, item: dict):
    # Only JAV gets the playback button.
    media_type = str(item.get("Type") or "").strip().lower()
    if media_type in {"episode", "series", "season"} or not is_jav_item(item):
        return None
    item_id = str(item.get("Id") or "").strip()
    if not item_id:
        return None
    if int(server.get("tg_binding_enabled") or 0):
        # CallbackQuery exposes the Telegram user who clicked the channel button.
        sig=_binding_callback_sig(server,item_id)
        data=f"sp:{server['id']}:{item_id}:{sig}"
        if len(data.encode("utf-8")) <= 64:
            return {"inline_keyboard": [[
                {"text": "▶️ SenPlayer 播放", "callback_data": data},
                {"text": "▶️ PotPlayer 播放", "callback_data": f"pp:{server['id']}:{item_id}:{sig}"},
            ]]}
    public_base = normalize_url(server.get("notifier_public_url") or "")
    if not public_base:
        return None
    sig = _senplayer_signature(server, item_id)
    url = f"{public_base}/senplayer/{server['id']}/{item_id}/{sig}"
    return {"inline_keyboard": [[{"text": "▶️ SenPlayer 播放", "url": url}]]}


def _verify_senplayer_signature(server: dict, item_id: str, sig: str) -> bool:
    return hmac.compare_digest(_senplayer_signature(server, item_id), sig)


def _verify_binding_play_sig(server: dict, item_id: str, tg_user_id: int, sig: str) -> bool:
    return hmac.compare_digest(_binding_play_sig(server,item_id,tg_user_id), sig)


async def tg_send_text(server: dict, chat_id: str, text: str):
    token = effective_bot_token_for_server(server)
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
        return data.get("result") or {}


async def tg_delete_messages(server: dict, chat_id: str, message_ids):
    token = effective_bot_token_for_server(server)
    if not token:
        return 0, ["missing bot token"]
    deleted = 0
    errors = []
    async with httpx.AsyncClient(timeout=30) as c:
        for mid in message_ids or []:
            try:
                r = await c.post(
                    f"https://api.telegram.org/bot{token}/deleteMessage",
                    data={"chat_id": chat_id, "message_id": int(mid)}
                )
                r.raise_for_status()
                data = r.json()
                if data.get("ok"):
                    deleted += 1
                else:
                    errors.append(str(data))
            except Exception as e:
                errors.append(str(e))
    return deleted, errors


@app.get("/console-mark.png")
def console_mark():
    return FileResponse(os.path.join(os.path.dirname(__file__), "downloads", "console-mark.png"), media_type="image/png")


_bot_identity_cache = {}


@app.get("/console-eye.svg")
def console_eye():
    return FileResponse(os.path.join(os.path.dirname(__file__), "downloads", "console-eye.svg"), media_type="image/svg+xml")


async def notification_binding_footer(server: dict) -> str:
    if not int(server.get("tg_binding_enabled") or 0):
        return ""
    token = binding_bot_token_for_server(server)
    if not token:
        return ""
    key = hashlib.sha256(token.encode()).hexdigest()
    cached = _bot_identity_cache.get(key)
    if cached and cached[0] > time.time():
        info = cached[1]
    else:
        try:
            info = await asyncio.wait_for(bot_api(token, "getMe"), timeout=5)
        except Exception:
            # A transient identity lookup failure must not drop the media notification.
            _bot_identity_cache[key] = (time.time() + 30, {})
            return ""
        _bot_identity_cache[key] = (time.time() + 300, info)
    username = str(info.get("username") or "")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        return ""
    name = html.escape(str(info.get("first_name") or username)[:128])
    return f'\n\n🔗 绑定 Emby：<a href="https://t.me/{username}?start=bind_{int(server["id"])}">{name}</a>'


async def tg_send(server: dict, chat_id: str, item: dict):
    item = await enrich_item_for_notification(server, item)
    token = effective_bot_token_for_server(server)
    if not token:
        raise RuntimeError("当前服务器没有可用的 Telegram Bot Token")
    caption = format_caption(item)
    if is_jav_item(item):
        caption += await notification_binding_footer(server)
    poster = await download_poster(server, item)
    keyboard = senplayer_button(server, item)
    reply_markup = json.dumps(keyboard, ensure_ascii=False) if keyboard else None
    message_ids = []
    async with httpx.AsyncClient(timeout=30) as c:
        if poster and len(caption) <= 1000:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={k: v for k, v in {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "reply_markup": reply_markup}.items() if v is not None},
                files={"photo": ("poster.jpg", poster, "image/jpeg")}
            )
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                raise RuntimeError(str(j))
            if j.get("result", {}).get("message_id") is not None:
                message_ids.append(int(j["result"]["message_id"]))
        elif poster:
            # Telegram photo captions are limited to 1024 characters. For large
            # multi-actress JAV entries, send the poster first and the full text next.
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id},
                files={"photo": ("poster.jpg", poster, "image/jpeg")}
            )
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                raise RuntimeError(str(j))
            if j.get("result", {}).get("message_id") is not None:
                message_ids.append(int(j["result"]["message_id"]))
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={k: v for k, v in {"chat_id": chat_id, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": "true", "reply_markup": reply_markup}.items() if v is not None}
            )
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                raise RuntimeError(str(j))
            if j.get("result", {}).get("message_id") is not None:
                message_ids.append(int(j["result"]["message_id"]))
        else:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={k: v for k, v in {"chat_id": chat_id, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": "true", "reply_markup": reply_markup}.items() if v is not None}
            )
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                raise RuntimeError(str(j))
            if j.get("result", {}).get("message_id") is not None:
                message_ids.append(int(j["result"]["message_id"]))
    return {"message_ids": message_ids, "item": item}


def _episode_size_bytes(item: dict) -> int:
    try:
        sources = item.get("MediaSources") or []
        if sources:
            return int((sources[0] or {}).get("Size") or item.get("Size") or 0)
        return int(item.get("Size") or 0)
    except Exception:
        return 0


def _episode_number(item: dict):
    value = item.get("IndexNumber")
    try:
        return int(value)
    except Exception:
        return None


def _season_number(item: dict):
    value = item.get("ParentIndexNumber")
    try:
        return int(value)
    except Exception:
        return value if value is not None else ""


def _series_batch_key(item: dict) -> str:
    return str(item.get("SeriesId") or item.get("SeriesName") or item.get("ParentId") or "").strip()


def _episode_range_text(numbers):
    nums = sorted({int(x) for x in numbers if x is not None})
    if not nums:
        return ""
    parts = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        if start == prev:
            parts.append(f"E{start:02d}")
        else:
            parts.append(f"E{start:02d}-E{prev:02d}")
        start = prev = n
    if start == prev:
        parts.append(f"E{start:02d}")
    else:
        parts.append(f"E{start:02d}-E{prev:02d}")
    return "、".join(parts)


def _tv_batch_quality(item: dict) -> str:
    media_sources = item.get("MediaSources") or []
    ms = media_sources[0] if media_sources else {}
    streams = ms.get("MediaStreams") or item.get("MediaStreams") or []
    video = next((x for x in streams if str(x.get("Type") or "").lower() == "video"), {})
    audios = [x for x in streams if str(x.get("Type") or "").lower() == "audio"]
    audio = next((x for x in audios if x.get("IsDefault")), audios[0] if audios else {})
    return detect_source_quality(item, ms, video, audio)


def format_tv_batch_caption(series_name: str, season, episodes: dict, last_item: dict) -> str:
    nums = sorted(int(k) for k in episodes.keys() if str(k).lstrip('-').isdigit())
    season_text = ""
    try:
        season_text = f"S{int(season):02d}季"
    except Exception:
        season_text = f"S{season}季" if str(season) else ""
    range_text = _episode_range_text(nums)
    ep_line = " · ".join(x for x in ["TVshow", season_text, range_text + "集" if range_text else ""] if x)
    title = series_name or last_item.get('SeriesName') or last_item.get('Name') or '电视剧'
    year = last_item.get("SeriesProductionYear") or last_item.get("ProductionYear")
    title_line = f"🎬 <b>{html.escape(title)}</b>" + (f" ({year})" if year else "")
    lines = [title_line, f"📺 {ep_line}"]
    genres = _notification_genres(last_item)
    if genres:
        lines.append(f"🎭 类型：{html.escape('、'.join(genres))}")
    overview = _notification_overview(last_item)
    if overview:
        lines.append(f"📝 简介：{html.escape(overview)}")
    lines.extend([
        "",
        "📥 <b>Emby 批量入库完成</b>",
        "🏷 类别：TVshow",
        f"📦 本次入库：{len(nums)}集",
    ])
    quality = _tv_batch_quality(last_item)
    if quality:
        lines.append(f"🌟 质量：{html.escape(quality)}")
    total_size = sum(int((episodes.get(str(n)) or {}).get("size") or 0) for n in nums)
    if total_size:
        lines.append(f"💾 总大小：{bytes_size(total_size)}")
    return "\n".join(lines)


async def tg_send_tv_batch(server: dict, chat_id: str, series_name: str, season, episodes: dict, last_item: dict):
    token = effective_bot_token_for_server(server)
    if not token:
        raise RuntimeError("当前服务器没有可用的 Telegram Bot Token")
    caption = format_tv_batch_caption(series_name, season, episodes, last_item)
    poster = await download_poster(server, last_item)
    async with httpx.AsyncClient(timeout=30) as c:
        if poster and len(caption) <= 1000:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": ("poster.jpg", poster, "image/jpeg")}
            )
        else:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": "true"}
            )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(str(data))
        return data.get("result") or {}


def record_tv_batch(server: dict, route: dict, sent: dict):
    item = sent.get("item") or {}
    if str(item.get("Type") or "").lower() != "episode":
        return
    series_key = _series_batch_key(item)
    ep = _episode_number(item)
    if not series_key or ep is None:
        return
    season = _season_number(item)
    season_key = str(season)
    now = time.time()
    conn = db()
    row = conn.execute(
        "SELECT * FROM tv_batches WHERE server_id=? AND route_id=? AND series_key=? AND season_key=?",
        (server["id"], route["id"], series_key, season_key)
    ).fetchone()
    episodes = json.loads(row["episodes_json"] or "{}") if row else {}
    message_ids = json.loads(row["message_ids_json"] or "[]") if row else []
    episodes[str(ep)] = {
        "size": _episode_size_bytes(item),
        "item_id": str(item.get("Id") or ""),
        "name": str(item.get("Name") or ""),
    }
    for mid in sent.get("message_ids") or []:
        if mid not in message_ids:
            message_ids.append(mid)
    series_name = str(item.get("SeriesName") or item.get("Name") or "电视剧")
    if row:
        conn.execute(
            """UPDATE tv_batches
               SET series_name=?, episodes_json=?, message_ids_json=?, last_item_json=?, last_seen_at=?
               WHERE id=?""",
            (series_name, json.dumps(episodes, ensure_ascii=False), json.dumps(message_ids),
             json.dumps(item, ensure_ascii=False), now, row["id"])
        )
    else:
        conn.execute(
            """INSERT INTO tv_batches(server_id,route_id,chat_id,series_key,series_name,season_key,
               episodes_json,message_ids_json,last_item_json,last_seen_at,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (server["id"], route["id"], str(route["chat_id"]), series_key, series_name, season_key,
             json.dumps(episodes, ensure_ascii=False), json.dumps(message_ids), json.dumps(item, ensure_ascii=False), now, now)
        )
    conn.commit()
    conn.close()


async def finalize_tv_batch(row: dict):
    server = get_server(int(row["server_id"]))
    if not server:
        return
    try:
        episodes = json.loads(row["episodes_json"] or "{}")
        message_ids = json.loads(row["message_ids_json"] or "[]")
        last_item = json.loads(row["last_item_json"] or "{}")
    except Exception:
        episodes, message_ids, last_item = {}, [], {}

    # One episode means a real single-episode arrival: keep the original notification as-is.
    if len(episodes) <= 1:
        conn = db()
        conn.execute("DELETE FROM tv_batches WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        return

    # For a batch: first try to remove all temporary single-episode notifications,
    # then send one NEW summary so Telegram generates a fresh notification.
    await tg_delete_messages(server, str(row["chat_id"]), message_ids)
    await tg_send_tv_batch(
        server,
        str(row["chat_id"]),
        str(row["series_name"] or "电视剧"),
        row["season_key"],
        episodes,
        last_item,
    )
    conn = db()
    conn.execute("DELETE FROM tv_batches WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()


async def tv_batch_worker():
    # Persistent SQLite state means pending TV batches survive a container restart.
    await asyncio.sleep(5)
    while True:
        try:
            now = time.time()
            conn = db()
            rows = conn.execute("""
                SELECT b.*, COALESCE(s.tv_batch_minutes,30) AS tv_batch_minutes
                FROM tv_batches b
                JOIN servers s ON s.id=b.server_id
                WHERE (? - b.last_seen_at) >= (COALESCE(s.tv_batch_minutes,30) * 60)
                ORDER BY b.last_seen_at ASC
            """, (now,)).fetchall()
            conn.close()
            for row in rows:
                try:
                    await finalize_tv_batch(dict(row))
                except Exception as e:
                    print(f"TV batch finalize failed id={row['id']}: {e}")
        except Exception as e:
            print(f"TV batch worker error: {e}")
        await asyncio.sleep(30)



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


BOT_POLLER_TASKS = {}

async def bot_api(token: str, method: str, data: dict | None=None):
    async with httpx.AsyncClient(timeout=35) as c:
        r=await c.post(f"https://api.telegram.org/bot{token}/{method}", data=data or {})
        r.raise_for_status()
        j=r.json()
        if not j.get("ok"):
            raise RuntimeError(str(j))
        return j.get("result")

async def bot_send(token: str, chat_id, text: str, reply_markup=None):
    data={"chat_id": str(chat_id), "text": text, "parse_mode":"HTML"}
    if reply_markup is not None: data["reply_markup"]=json.dumps(reply_markup, ensure_ascii=False)
    return await bot_api(token,"sendMessage",data)

async def bot_delete_message(token: str, chat_id, message_id) -> bool:
    if not token or not chat_id or not message_id:
        return False
    try:
        await bot_api(token,"deleteMessage",{"chat_id":str(chat_id),"message_id":str(message_id)})
        return True
    except httpx.HTTPStatusError as e:
        try:
            description = str(e.response.json().get("description", "")).lower()
        except Exception:
            description = ""
        if e.response.status_code == 400 and "message to delete not found" in description:
            return True
        print(f"[TG cleanup] HTTP {e.response.status_code} chat={chat_id} message={message_id}", flush=True)
        return False
    except Exception as e:
        # Do not break the user flow if Telegram refuses a cleanup, but keep a
        # visible log so cleanup failures are no longer silently swallowed.
        print(f"[TG cleanup] {type(e).__name__} chat={chat_id} message={message_id}", flush=True)
        return False

def bot_delete_message_later(token: str, chat_id, message_id, delay: int = 10):
    """Persist cleanup without storing another copy of the bot credential."""
    if not token or not chat_id or not message_id:
        return
    with db() as conn:
        conn.execute("""INSERT INTO tg_cleanup_jobs(token_hash,chat_id,message_id,due_at)
          VALUES(?,?,?,?) ON CONFLICT(token_hash,chat_id,message_id)
          DO UPDATE SET due_at=MIN(due_at,excluded.due_at)""",
          (hashlib.sha256(token.encode()).hexdigest(), str(chat_id), int(message_id),
           time.time() + max(0, int(delay))))
    conn.close()

async def run_cleanup_jobs():
    conn = db()
    rows = conn.execute("SELECT * FROM tg_cleanup_jobs WHERE due_at<=? ORDER BY due_at LIMIT 10", (time.time(),)).fetchall()
    servers = conn.execute("SELECT * FROM servers").fetchall()
    conn.close()
    tokens = {str(get_settings().get("global_bot_token") or "").strip()}
    for row in servers:
        server = dict(row)
        tokens.update((binding_bot_token_for_server(server), bot_token_for_server(server),
                       str(server.get("tg_binding_bot_token") or "").strip()))
    by_hash = {hashlib.sha256(t.encode()).hexdigest(): t for t in tokens if t}

    async def attempt(row):
        token = by_hash.get(row["token_hash"])
        ok = bool(token) and await bot_delete_message(token, row["chat_id"], row["message_id"])
        attempts = row["attempts"] + 1
        key = (row["token_hash"], row["chat_id"], row["message_id"])
        with db() as conn:
            if ok or attempts >= 6:
                conn.execute("DELETE FROM tg_cleanup_jobs WHERE token_hash=? AND chat_id=? AND message_id=?", key)
                if not ok:
                    print(f"[TG cleanup] exhausted retries chat={row['chat_id']} message={row['message_id']}", flush=True)
            else:
                conn.execute("UPDATE tg_cleanup_jobs SET attempts=?,due_at=? WHERE token_hash=? AND chat_id=? AND message_id=?",
                             (attempts, time.time() + min(300, 5 * 2 ** attempts), *key))
        conn.close()
    await asyncio.gather(*(attempt(row) for row in rows))

async def telegram_cleanup_worker():
    while True:
        try:
            await run_cleanup_jobs()
        except Exception as e:
            print(f"[TG cleanup] worker error: {type(e).__name__}", flush=True)
        await asyncio.sleep(1)

async def bot_send_temporary(token: str, chat_id, text: str, reply_markup=None, ttl: int = 10):
    sent = await bot_send(token, chat_id, text, reply_markup)
    if isinstance(sent, dict):
        bot_delete_message_later(token, sent.get("chat", {}).get("id", chat_id), sent.get("message_id"), ttl)
    return sent

async def delete_server_bot_message(server: dict, chat_id, message_id) -> bool:
    """Delete a message sent by this server's notification/binding bot.

    v14.x permits a per-server notification token and an optional independent
    binding token.  Try every plausible token, de-duplicated, so a playback
    message is removed even if the bot configuration changed after it was sent.
    """
    tokens=[]
    for tok in (
        binding_bot_token_for_server(server),
        effective_bot_token_for_server(server),
        bot_token_for_server(server),
        str(server.get("tg_binding_bot_token") or "").strip(),
    ):
        if tok and tok not in tokens:
            tokens.append(tok)
    for tok in tokens:
        if await bot_delete_message(tok, chat_id, message_id):
            return True
    return False


async def bot_delete_callback_message(token: str, q: dict):
    """Delete the private inline-menu message immediately after a button is used."""
    try:
        msg = q.get("message") or {}
        chat = msg.get("chat") or {}
        await bot_delete_message(token, chat.get("id"), msg.get("message_id"))
    except Exception:
        pass

async def bot_answer_callback(token: str, callback_id: str, text: str="", show_alert: bool=False, url: str=""):
    data={"callback_query_id":callback_id}
    if text: data["text"]=text
    if show_alert: data["show_alert"]="true"
    if url: data["url"]=url
    try: await bot_api(token,"answerCallbackQuery",data)
    except Exception: pass

async def bot_binding_menu(token: str, chat_id, actual_bot_id: str):
    servers=servers_for_binding_bot(token,actual_bot_id)
    kb={"inline_keyboard":[
        [{"text":"🔗 绑定 Emby","callback_data":"bm:bind"},{"text":"❌ 取消绑定","callback_data":"bm:unbind"}],
        [{"text":"📋 我的绑定","callback_data":"bm:status"}],
    ]}
    await bot_send_temporary(token,chat_id,"<b>Emby 账号绑定</b>\n\n请选择操作：",kb,10)

async def bot_choose_server(token: str, chat_id, actual_bot_id: str, action: str):
    servers=servers_for_binding_bot(token,actual_bot_id)
    if not servers:
        await bot_send_temporary(token,chat_id,"当前没有启用 TG 账号绑定的 Emby 服务器。",ttl=10)
        return
    if len(servers)==1:
        s=servers[0]
        if action=="bind":
            set_bind_state(actual_bot_id,int(chat_id),"await_username",s["id"],"")
            sent=await bot_send(token,chat_id,f"正在绑定 <b>{html.escape(s['name'])}</b>\n\n第一步：请发送你的 <b>Emby 账号</b>。\n发送 /cancel 可取消。")
            if isinstance(sent,dict): track_bind_message(actual_bot_id,int(chat_id),sent.get("message_id"))
        else:
            conn=db(); cur=conn.execute("DELETE FROM tg_bindings WHERE server_id=? AND tg_user_id=?",(s["id"],int(chat_id))); conn.commit(); conn.close()
            await bot_send(token,chat_id,f"已取消 <b>{html.escape(s['name'])}</b> 的绑定。" if cur.rowcount else "这个服务器目前没有你的绑定。")
        return
    rows=[]
    for s in servers:
        rows.append([{"text":s["name"],"callback_data":f"bm:{action}srv:{s['id']}"}])
    await bot_send_temporary(token,chat_id,"请选择 Emby 服务器：",{"inline_keyboard":rows},10)

async def bot_show_status(token: str, chat_id, actual_bot_id: str):
    servers=servers_for_binding_bot(token,actual_bot_id)
    lines=["<b>我的 Emby 绑定</b>"]
    found=False
    for s in servers:
        b=get_tg_binding(s["id"],int(chat_id))
        if b:
            found=True; lines.append(f"• {html.escape(s['name'])} → <b>{html.escape(b['emby_username'])}</b>")
    if not found: lines.append("尚未绑定。")
    await bot_send_temporary(token,chat_id,"\n".join(lines),ttl=10)

async def process_bot_message(token: str, bot_info: dict, msg: dict):
    chat=msg.get("chat") or {}; user=msg.get("from") or {}; text=str(msg.get("text") or "").strip()
    if chat.get("type") != "private" or not user.get("id"): return
    uid=int(user["id"]); chat_id=int(chat["id"]); bot_id=str(bot_info.get("id") or "")
    cmd=text.split()[0].split('@')[0].lower() if text.startswith('/') else ''
    if await pot_sync.bot_command(token, msg, cmd):
        return
    if cmd in {"/start","/help"}:
        bot_delete_message_later(token, chat_id, msg.get("message_id"), 10)
        set_bind_state(bot_id,uid,"",0,"")
        # Deep link from an unbound channel click: /start bind_<server_id>
        parts=text.split(maxsplit=1)
        if len(parts)>1 and parts[1].startswith("bind_"):
            try:
                sid=int(parts[1][5:]); s=get_server(sid)
                if s and int(s["tg_binding_enabled"] or 0) and binding_bot_token_for_server(dict(s))==token:
                    set_bind_state(bot_id,uid,"await_username",sid,"")
                    track_bind_message(bot_id,uid,msg.get("message_id"))
                    sent=await bot_send(token,chat_id,f"正在绑定 <b>{html.escape(s['name'])}</b>\n\n第一步：请发送你的 <b>Emby 账号</b>。\n发送 /cancel 可取消。")
                    if isinstance(sent,dict): track_bind_message(bot_id,uid,sent.get("message_id"))
                    return
            except Exception: pass
        await bot_binding_menu(token,chat_id,bot_id); return
    if cmd=="/bind": await bot_choose_server(token,chat_id,bot_id,"bind"); return
    if cmd=="/unbind": await bot_choose_server(token,chat_id,bot_id,"unbind"); return
    if cmd in {"/status","/me"}: await bot_show_status(token,chat_id,bot_id); return
    if cmd=="/cancel":
        await cleanup_bind_messages(token,chat_id,bot_id,uid,extra_ids=[msg.get("message_id")])
        set_bind_state(bot_id,uid,"",0,"")
        await bot_send_temporary(token,chat_id,"已取消当前操作。",ttl=10)
        return
    if cmd=="/bindings" and uid in _binding_admin_ids_for_token(token):
        allowed = [s["id"] for s in servers_for_binding_bot(token)
                   if uid in _binding_admin_ids() or uid in _parse_tg_ids(s.get("tg_binding_admin_ids") or "")]
        conn=db()
        placeholders = ",".join("?" for _ in allowed)
        rows = conn.execute(f"SELECT b.*,s.name server_name FROM tg_bindings b JOIN servers s ON s.id=b.server_id WHERE b.server_id IN ({placeholders}) ORDER BY b.updated_at DESC LIMIT 100", allowed).fetchall() if allowed else []
        conn.close()
        lines=["<b>最近绑定</b>"]+[f"• TG <code>{r['tg_user_id']}</code> → {html.escape(r['server_name'])} / {html.escape(r['emby_username'])}" for r in rows]
        await bot_send(token,chat_id,"\n".join(lines[:101])); return
    st=get_bind_state(bot_id,uid)
    if not st:
        await bot_binding_menu(token,chat_id,bot_id); return
    if st["state"]=="await_username":
        if not text or text.startswith('/'):
            await bot_send_temporary(token,chat_id,"请发送 Emby 账号。",ttl=10) ; return
        track_bind_message(bot_id,uid,msg.get("message_id"))
        set_bind_state(bot_id,uid,"await_password",int(st["server_id"]),text)
        sent=await bot_send(token,chat_id,"第二步：请发送 <b>Emby 密码</b>。\n密码只用于这次验证，验证后不会保存。绑定成功后，本次绑定过程的聊天记录会自动清理。")
        if isinstance(sent,dict): track_bind_message(bot_id,uid,sent.get("message_id"))
        return
    if st["state"]=="await_password":
        sid=int(st["server_id"]); srow=get_server(sid); username=str(st.get("pending_username") or "")
        if not srow:
            set_bind_state(bot_id,uid,"",0,""); await bot_send_temporary(token,chat_id,"服务器不存在，绑定已取消。",ttl=10); return
        track_bind_message(bot_id,uid,msg.get("message_id"))
        await bot_delete_message(token,chat_id,msg.get("message_id"))
        emby_user=await authenticate_emby_credentials(dict(srow),username,text)
        if not emby_user:
            # Wrong credentials: clear the previous username/prompt/error trail immediately,
            # keep only the in-memory/database pending username so the user can retry password.
            await cleanup_bind_messages(token,chat_id,bot_id,uid)
            set_bind_state(bot_id,uid,"await_password",sid,username,[])
            await bot_send_temporary(token,chat_id,"❌ Emby 账号或密码验证失败。\n请重新发送密码，或 /cancel 取消。",ttl=10)
            return
        upsert_tg_binding(sid,user,emby_user)
        await cleanup_bind_messages(token,chat_id,bot_id,uid)
        set_bind_state(bot_id,uid,"",0,"")
        await bot_send(token,chat_id,f"✅ 绑定“<b>{html.escape(srow['name'])}</b>”成功，愉快的屌之北吧。")


def create_senplayer_ticket(server_id: int, item_id: str, tg_user_id: int, ttl: int = 300, player: str = "sp") -> str:
    if player not in {"sp", "pp"}:
        raise ValueError("Unsupported player")
    token=secrets.token_urlsafe(32); now=time.time(); conn=db()
    conn.execute("DELETE FROM senplayer_tickets WHERE expires_at<? OR used_at>0",(now-3600,))
    conn.execute("INSERT INTO senplayer_tickets(token,server_id,item_id,tg_user_id,expires_at,used_at,created_at,player) VALUES(?,?,?,?,?,0,?,?)",(token,int(server_id),str(item_id),int(tg_user_id),now+ttl,now,player))
    conn.commit(); conn.close(); return token

def attach_senplayer_ticket_message(token: str, chat_id, message_id) -> None:
    try:
        conn=db()
        conn.execute("UPDATE senplayer_tickets SET tg_chat_id=?, tg_message_id=? WHERE token=?",
                     (str(chat_id or ""), int(message_id or 0), token))
        conn.commit(); conn.close()
    except Exception:
        pass

def consume_senplayer_ticket(token: str, player: str = "sp"):
    now=time.time(); conn=db(); row=conn.execute("SELECT * FROM senplayer_tickets WHERE token=? AND player=?",(token,player)).fetchone()
    if not row or float(row["expires_at"] or 0)<now or float(row["used_at"] or 0)>0: conn.close(); return None
    cur=conn.execute("UPDATE senplayer_tickets SET used_at=? WHERE token=? AND used_at=0",(now,token)); conn.commit(); conn.close()
    return dict(row) if cur.rowcount==1 else None

async def process_bot_callback(token: str, bot_info: dict, q: dict):
    qid=str(q.get("id") or ""); user=q.get("from") or {}; uid=int(user.get("id") or 0); data=str(q.get("data") or ""); bot_id=str(bot_info.get("id") or "")
    if not uid: return
    if data.startswith("ep:"):
        await bot_answer_callback(token,qid,"Emby 按钮已移除，请使用 SenPlayer 播放",True)
        return
    if data=="bm:bind":
        await bot_answer_callback(token,qid); await bot_delete_callback_message(token,q); await bot_choose_server(token,uid,bot_id,"bind"); return
    if data=="bm:unbind":
        await bot_answer_callback(token,qid); await bot_delete_callback_message(token,q); await bot_choose_server(token,uid,bot_id,"unbind"); return
    if data=="bm:status":
        await bot_answer_callback(token,qid); await bot_delete_callback_message(token,q); await bot_show_status(token,uid,bot_id); return
    m=re.fullmatch(r"bm:(bind|unbind)srv:(\d+)",data)
    if m:
        await bot_answer_callback(token,qid); await bot_delete_callback_message(token,q); action=m.group(1); sid=int(m.group(2)); s=get_server(sid)
        if not s: return
        if action=="bind":
            set_bind_state(bot_id,uid,"await_username",sid,"")
            qmsg=q.get("message") or {}
            track_bind_message(bot_id,uid,qmsg.get("message_id"))
            sent=await bot_send(token,uid,f"正在绑定 <b>{html.escape(s['name'])}</b>\n\n第一步：请发送你的 <b>Emby 账号</b>。")
            if isinstance(sent,dict): track_bind_message(bot_id,uid,sent.get("message_id"))
        else:
            conn=db(); cur=conn.execute("DELETE FROM tg_bindings WHERE server_id=? AND tg_user_id=?",(sid,uid)); conn.commit(); conn.close(); await bot_send(token,uid,f"已取消 <b>{html.escape(s['name'])}</b> 的绑定。" if cur.rowcount else "这个服务器目前没有你的绑定。")
        return
    m=re.fullmatch(r"(sp|pp):(\d+):([^:]+):([0-9a-f]{10})",data)
    if not m: return
    player=m.group(1); sid=int(m.group(2)); item_id=m.group(3); sig=m.group(4); srow=get_server(sid)
    if not srow or not hmac.compare_digest(_binding_callback_sig(dict(srow),item_id),sig):
        await bot_answer_callback(token,qid,"播放链接无效或已失效",True); return
    server=dict(srow); binding=get_tg_binding(sid,uid)
    if not int(server.get("tg_binding_enabled") or 0) or binding_bot_token_for_server(server) != token:
        await bot_answer_callback(token,qid,"播放入口已关闭或机器人不匹配",True); return
    if not binding:
        username=str(bot_info.get("username") or "")
        deep=f"https://t.me/{username}?start=bind_{sid}" if username else ""
        await bot_answer_callback(token,qid,"请先绑定你的 Emby 账号",True,deep)
        return
    public_base=normalize_url(server.get("notifier_public_url") or "")
    if not public_base:
        await bot_answer_callback(token,qid,"管理员尚未设置通知程序公网地址",True); return
    if player == "pp":
        try:
            await pot_sync.live_scope(sid, uid)
        except Exception:
            await bot_answer_callback(token,qid,"无法核验绑定的 Emby 用户（用户停用、已删除或服务器暂不可用），未启动播放。",True)
            return
        delivery = pot_sync.dispatch(server, uid, item_id)
        if delivery == 'sent':
            await bot_answer_callback(token,qid,"已发送到配对电脑，正在直接启动 PotPlayer。",True)
        elif delivery == 'busy':
            await bot_answer_callback(token,qid,"电脑正在播放或启动中，请先关闭当前影片。",True)
        else:
            await bot_answer_callback(token,qid,"电脑端未配对或当前离线。请启动“JAV频道点播”后台程序；现在不再使用 Chrome 备用播放。",True)
        return
    ticket=create_senplayer_ticket(sid,item_id,uid,300,player=player)
    player_name="PotPlayer" if player=="pp" else "SenPlayer"
    play_url=f"{public_base}/{'ps' if player == 'pp' else 'sp'}/{ticket}"
    markup={"inline_keyboard":[[{"text":f"▶️ 打开 {player_name}","url":play_url}]]}
    install_note = ""
    try:
        sent = await bot_send(token,uid,f"🎬 已按 Emby 用户 <b>{html.escape(binding['emby_username'])}</b> 准备播放。\n点击下面按钮打开 {player_name}：{install_note}",markup)
        if isinstance(sent, dict):
            play_chat_id = sent.get("chat", {}).get("id", uid)
            play_message_id = sent.get("message_id", 0)
            attach_senplayer_ticket_message(ticket, play_chat_id, play_message_id)
            bot_delete_message_later(token, play_chat_id, play_message_id, 10)
        await bot_answer_callback(token,qid,"已发送到机器人私聊")
    except Exception:
        username=str(bot_info.get("username") or "")
        deep=f"https://t.me/{username}?start=bind_{sid}" if username else ""
        await bot_answer_callback(token,qid,"请先私聊机器人 /start",True,deep)

async def telegram_bot_poller(token: str):
    info=await bot_api(token,"getMe")
    bot_id=str(info.get("id") or "")
    try:
        await bot_api(token,"setMyCommands",{"commands":json.dumps([
            {"command":"start","description":"打开绑定菜单"},{"command":"bind","description":"绑定 Emby 账号"},{"command":"unbind","description":"取消绑定"},{"command":"status","description":"查看我的绑定"},{"command":"cancel","description":"取消当前操作"},
            {"command":"pc","description":"JAV频道点播电脑配对"},{"command":"pc_off","description":"撤销电脑直达配对"}
        ],ensure_ascii=False)})
    except Exception: pass
    conn=db(); row=conn.execute("SELECT next_offset FROM tg_bot_offsets WHERE bot_id=?",(bot_id,)).fetchone(); offset=int(row["next_offset"] if row else 0); conn.close()
    while True:
        try:
            async with httpx.AsyncClient(timeout=40) as c:
                r=await c.get(f"https://api.telegram.org/bot{token}/getUpdates",params={"timeout":25,"offset":offset,"allowed_updates":json.dumps(["message","callback_query"])})
                r.raise_for_status(); j=r.json()
            if not j.get("ok"): raise RuntimeError(str(j))
            for upd in j.get("result") or []:
                offset=max(offset,int(upd.get("update_id") or 0)+1)
                try:
                    if upd.get("message"): await process_bot_message(token,info,upd["message"])
                    elif upd.get("callback_query"): await process_bot_callback(token,info,upd["callback_query"])
                except Exception as e:
                    print(f"[TG binding] update error: {e}")
            conn=db(); conn.execute("INSERT INTO tg_bot_offsets(bot_id,next_offset) VALUES(?,?) ON CONFLICT(bot_id) DO UPDATE SET next_offset=excluded.next_offset",(bot_id,offset)); conn.commit(); conn.close()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[TG binding] poller error bot={bot_id}: {e}")
            await asyncio.sleep(5)

async def telegram_binding_manager():
    while True:
        wanted={}
        conn=db(); rows=conn.execute("SELECT * FROM servers WHERE tg_binding_enabled=1").fetchall(); conn.close()
        for r in rows:
            s=dict(r); token=binding_bot_token_for_server(s)
            if token: wanted[token]=True
        for token in list(wanted):
            key=hashlib.sha256(token.encode()).hexdigest()[:16]
            if key not in BOT_POLLER_TASKS or BOT_POLLER_TASKS[key].done():
                BOT_POLLER_TASKS[key]=asyncio.create_task(telegram_bot_poller(token))
        for key,task in list(BOT_POLLER_TASKS.items()):
            if task.done(): BOT_POLLER_TASKS.pop(key,None)
        await asyncio.sleep(15)


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
async def startup():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    init_db()
    pot_sync.init_db()
    # Best-effort: on every container start/recreate, automatically reconnect
    # the notifier itself to emby-notify-net. No SSH command is required.
    ensure_local_network()
    asyncio.create_task(tv_batch_worker())
    asyncio.create_task(telegram_binding_manager())
    spawn_background(telegram_cleanup_worker())


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

    return templates.TemplateResponse("console.html", {
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
        "detected_public_base": external_base_url(request),
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
    send_test_to_telegram: Optional[str] = Form(None),
    senplayer_emby_url: str = Form(""),
    notifier_public_url: str = Form(""),
    senplayer_user: str = Form(""),
    tv_batch_minutes: int = Form(30),
    tg_binding_enabled: Optional[str] = Form(None),
    tg_binding_bot_id: str = Form(""),
    tg_binding_bot_token: str = Form(""),
    tg_binding_admin_ids: str = Form(""),
    senplayer_progress_sync: Optional[str] = Form(None)
):
    require_login(request)
    clean_name = name.strip()
    conn = db()
    conn.execute("""
      UPDATE servers
      SET name=?, emby_url=?, emby_api_key=?, bot_token_override=?, send_test_to_telegram=?,
          senplayer_emby_url=?, notifier_public_url=?, senplayer_user=?, tv_batch_minutes=?,
          tg_binding_enabled=?, tg_binding_bot_id=?, tg_binding_bot_token=?, tg_binding_admin_ids=?, senplayer_progress_sync=?
      WHERE id=?
    """, (
        clean_name,
        normalize_url(emby_url),
        emby_api_key.strip(),
        bot_token_override.strip(),
        1 if send_test_to_telegram else 0,
        normalize_url(senplayer_emby_url) if senplayer_emby_url.strip() else "",
        normalize_url(notifier_public_url) if notifier_public_url.strip() else "",
        senplayer_user.strip(),
        max(1, min(1440, int(tv_batch_minutes or 30))),
        1 if tg_binding_enabled else 0,
        re.sub(r"\D", "", tg_binding_bot_id or ""),
        tg_binding_bot_token.strip(),
        tg_binding_admin_ids.strip(),
        1 if senplayer_progress_sync else 0,
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
    conn.execute("DELETE FROM tg_bindings WHERE server_id=?", (server_id,))
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
async def save_global_bot(request: Request, global_bot_token: str = Form(""), binding_admin_ids: str = Form("")):
    require_login(request)
    conn = db()
    conn.execute("UPDATE app_settings SET global_bot_token=?, binding_admin_ids=? WHERE id=1", (global_bot_token.strip(), binding_admin_ids.strip()))
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


def notification_error_summary(error):
    if isinstance(error, httpx.HTTPStatusError):
        try:
            description = str(error.response.json().get("description") or "")
        except Exception:
            description = ""
        if "chat not found" in description.lower():
            return "Telegram 找不到频道：检查频道 ID，并将当前通知机器人加入频道、授予发布消息权限"
        if error.response.status_code == 403:
            return "Telegram 拒绝发送：检查机器人是否被移除或缺少频道发布权限"
        return f"通知接口返回 HTTP {error.response.status_code}，请检查服务配置"
    if isinstance(error, httpx.TimeoutException):
        return "通知请求超时，请检查网络连接"
    # Exception strings may contain authenticated URLs. Never expose them in the panel.
    return f"通知发送失败（{type(error).__name__}），请检查服务连接和配置"


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
            sent = await tg_send(server, r["chat_id"], item)
            if str((sent.get("item") or {}).get("Type") or "").lower() == "episode":
                record_tv_batch(server, dict(r), sent)
            sent_count += 1
            results.append({"route": r["id"], "ok": True})
        except Exception as e:
            reason = notification_error_summary(e)
            results.append({"route": r["id"], "ok": False, "error": reason})
            print(f"[notification failed] server={server_id} route={r['id']}: {reason}")

    failures = [r for r in results if not r["ok"]]
    detail = f"入库事件处理完成，匹配媒体库 {library_id}，Telegram 成功发送 {sent_count} 个任务"
    if not routes:
        detail += "；该媒体库没有启用的通知任务"
    if failures:
        detail += "；" + "；".join(f"任务 {r['route']}：{r['error']}" for r in failures)
    update_webhook_status(
        server_id,
        event,
        source_name=source_name,
        telegram_count=sent_count,
        detail=detail
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


@app.get("/ep/{token}")
@app.get("/emby-open/{server_id}/{item_id}/{sig}")
async def retired_emby_launch():
    raise HTTPException(status_code=410, detail="Emby 播放入口已移除，请使用 SenPlayer")


@app.get("/sp/{token}")
async def senplayer_ticket_open(token: str):
    return await player_ticket_open(token, "sp")


@app.get("/downloads/potplayer-browser-launcher.zip")
async def potplayer_installer_download():
    package = Path(__file__).resolve().parent / "downloads" / "potplayer-browser-launcher.zip"
    if not package.is_file():
        raise HTTPException(status_code=404, detail="安装包暂不可用，请联系管理员")
    return FileResponse(package, media_type="application/zip", filename="JAV频道点播-v15.9.zip",
                        headers={"Cache-Control":"no-store", "X-Content-Type-Options":"nosniff"})


@app.get("/pp/{token}")
async def potplayer_ticket_open(token: str):
    raise HTTPException(status_code=410, detail="PotPlayer 浏览器播放入口已移除，请使用已配对的电脑端直接播放")


async def player_ticket_open(token: str, player: str):
    ticket=consume_senplayer_ticket(token,player)
    if not ticket: return HTMLResponse("<h3>❌ 播放凭证已失效或已使用，请回 Telegram 频道重新点击播放。</h3>",status_code=403)
    srow=get_server(int(ticket["server_id"])); server=dict(srow) if srow else None
    if not server: raise HTTPException(status_code=404)
    if player == "pp" and not int(server.get("tg_binding_enabled") or 0):
        raise HTTPException(status_code=403,detail="播放入口已关闭")
    binding=get_tg_binding(int(ticket["server_id"]),int(ticket["tg_user_id"]))
    if not binding: return HTMLResponse("<h3>❌ 当前 Telegram 用户未绑定 Emby，无法播放。</h3>",status_code=403)
    # The private one-time player message is only an intermediate step.
    # Queue deletion when opened; Telegram network requests run in the worker.
    tg_chat_id=str(ticket.get("tg_chat_id") or "")
    tg_message_id=int(ticket.get("tg_message_id") or 0)
    if tg_chat_id and tg_message_id:
        bot_delete_message_later(binding_bot_token_for_server(server), tg_chat_id, tg_message_id, 0)
    item_id=str(ticket["item_id"]); emby_base=normalize_url(server.get("senplayer_emby_url") or server.get("emby_url") or ""); api_key=str(server.get("emby_api_key") or "").strip()
    if not emby_base or not api_key: raise HTTPException(status_code=503,detail="播放器 Emby 地址或 API Key 未配置")
    media_url=f"{emby_base}/emby/Videos/{quote(item_id,safe='')}/stream?Static=true&api_key={quote(api_key,safe='')}"
    if player == "pp":
        if urlsplit(emby_base).scheme not in {"http", "https"} or not urlsplit(emby_base).hostname:
            raise HTTPException(status_code=503,detail="PotPlayer 播放地址必须为 HTTP 或 HTTPS")
        # Our per-user Windows handler decodes one URL, without shell evaluation.
        payload=base64.urlsafe_b64encode(media_url.encode("utf-8")).decode("ascii").rstrip("=")
        return RedirectResponse("hdz-potplayer://play/"+payload,status_code=302,
                                headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})
    params=["url="+quote(media_url,safe="")]
    resume=await _senplayer_resume_seconds(server,binding["emby_user_id"],item_id)
    if resume>0: params.append(f"position={resume}")
    if int(server.get("senplayer_progress_sync") or 0):
        public_base=normalize_url(server.get("notifier_public_url") or ""); psig=_binding_play_sig(server,item_id,int(ticket["tg_user_id"]))
        if public_base:
            cb=f"{public_base}/senplayer-user-callback/{ticket['server_id']}/{quote(item_id,safe='')}/{ticket['tg_user_id']}/{psig}"; params.append("x-success="+quote(cb,safe=""))
    return RedirectResponse("SenPlayer://x-callback-url/play?"+"&".join(params),status_code=302)

@app.get("/senplayer-user/{server_id}/{item_id}/{tg_user_id}/{sig}")
async def senplayer_user_open(server_id: int, item_id: str, tg_user_id: int, sig: str):
    srow=get_server(server_id)
    if not srow: raise HTTPException(status_code=404)
    server=dict(srow)
    if not _verify_binding_play_sig(server,item_id,tg_user_id,sig): raise HTTPException(status_code=404)
    binding=get_tg_binding(server_id,tg_user_id)
    if not binding: raise HTTPException(status_code=403, detail="Telegram 用户尚未绑定 Emby")
    public_base=normalize_url(server.get("notifier_public_url") or "")
    if not public_base: raise HTTPException(status_code=400,detail="未设置通知程序公网地址")
    media_sig=_senplayer_signature(server,item_id)
    media_url=f"{public_base}/senplayer-media/{server_id}/{quote(item_id,safe='')}/{media_sig}"
    params=["url="+quote(media_url,safe="")]
    resume=await _senplayer_resume_seconds(server,binding["emby_user_id"],item_id)
    if resume>0: params.append(f"position={resume}")
    if int(server.get("senplayer_progress_sync") or 0):
        cb=f"{public_base}/senplayer-user-callback/{server_id}/{quote(item_id,safe='')}/{tg_user_id}/{sig}"
        params.append("x-success="+quote(cb,safe=""))
    return RedirectResponse("SenPlayer://x-callback-url/play?"+"&".join(params),status_code=302)

def callback_position(query) -> int:
    for key in ("position", "time", "currentTime", "playbackTime", "progress"):
        raw = query.get(key)
        if raw is not None and raw != "":
            try:
                value = float(raw)
                if math.isfinite(value) and value >= 0 and value <= 922337203685:
                    return int(value)
            except (TypeError, ValueError, OverflowError):
                pass
            break
    raise HTTPException(status_code=400, detail="缺少有效播放位置，已有进度未修改")

@app.get("/senplayer-user-callback/{server_id}/{item_id}/{tg_user_id}/{sig}")
async def senplayer_user_callback(server_id: int, item_id: str, tg_user_id: int, sig: str, request: Request):
    srow=get_server(server_id)
    if not srow: raise HTTPException(status_code=404)
    server=dict(srow)
    if not _verify_binding_play_sig(server,item_id,tg_user_id,sig): raise HTTPException(status_code=404)
    if not int(server.get("senplayer_progress_sync") or 0):
        return HTMLResponse(status_code=204)
    binding=get_tg_binding(server_id,tg_user_id)
    if not binding: return HTMLResponse("<h3>绑定已取消，无法同步进度。</h3>",status_code=403)
    q=request.query_params
    dur=q.get("duration") or "0"; status=(q.get("status") or "").lower()
    pos=callback_position(q)
    try: duration=max(0,int(float(dur)))
    except Exception: duration=0
    finished=status in {"finished","completed","complete","ended"} or (duration>0 and pos/duration>=0.90)
    ok=await _update_emby_resume(server,binding["emby_user_id"],item_id,pos,finished=finished)
    if ok:
        txt="已同步并标记为已播放" if finished else "播放进度已同步"
        return HTMLResponse(f"<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'><body style='font-family:-apple-system;padding:32px;background:#0b1320;color:#fff'><h3>✅ {html.escape(txt)}</h3><p>Emby 用户：{html.escape(binding['emby_username'])}</p><p>位置：{pos} 秒</p><script>setTimeout(()=>history.back(),700)</script></body>")
    return HTMLResponse("<h3>⚠️ SenPlayer 已返回进度，但写入 Emby 失败。</h3>",status_code=502)


@app.get("/senplayer/{server_id}/{item_id}/{sig}")
async def senplayer_open(server_id: int, item_id: str, sig: str):
    server_row = get_server(server_id)
    if not server_row:
        raise HTTPException(status_code=404)
    server = dict(server_row)
    if not _verify_senplayer_signature(server, item_id, sig):
        raise HTTPException(status_code=404)

    public_base = normalize_url(server.get("notifier_public_url") or "")
    if not public_base:
        raise HTTPException(status_code=400, detail="未设置通知程序公网地址")

    media_url = f"{public_base}/senplayer-media/{server_id}/{item_id}/{sig}"
    params = ["url=" + quote(media_url, safe="")]

    # SenPlayer 6.1.1+ supports resume position and returning current time on exit.
    sp_user = await _resolve_senplayer_user(server)
    if sp_user:
        resume = await _senplayer_resume_seconds(server, sp_user["Id"], item_id)
        if resume > 0:
            params.append(f"position={resume}")
        if int(server.get("senplayer_progress_sync") or 0):
            cb = f"{public_base}/senplayer-callback/{server_id}/{item_id}/{sig}"
            params.append("x-success=" + quote(cb, safe=""))

    scheme = "SenPlayer://x-callback-url/play?" + "&".join(params)
    return RedirectResponse(scheme, status_code=302)


@app.get("/senplayer-callback/{server_id}/{item_id}/{sig}")
async def senplayer_callback(server_id: int, item_id: str, sig: str, request: Request):
    server_row = get_server(server_id)
    if not server_row:
        raise HTTPException(status_code=404)
    server = dict(server_row)
    if not _verify_senplayer_signature(server, item_id, sig):
        raise HTTPException(status_code=404)
    if not int(server.get("senplayer_progress_sync") or 0):
        return HTMLResponse(status_code=204)

    sp_user = await _resolve_senplayer_user(server)
    if not sp_user:
        return HTMLResponse("<h3>SenPlayer 已退出，但未配置 Emby 进度同步用户。</h3>")

    q = request.query_params
    raw_duration = q.get("duration") or "0"
    status = (q.get("status") or "").lower()
    position = callback_position(q)
    try:
        duration = max(0, int(float(raw_duration)))
    except Exception:
        duration = 0

    finished = status in {"finished", "completed", "complete", "ended"}
    if not finished and duration > 0 and position / duration >= 0.90:
        finished = True

    ok = await _update_emby_resume(server, sp_user["Id"], item_id, position, finished=finished)
    if ok:
        text = "已同步到 Emby，并标记为已播放" if finished else "播放进度已同步到 Emby"
        body = (
            "<!doctype html><html><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<body style='font-family:-apple-system;padding:32px;background:#0b1320;color:#fff'>"
            f"<h3>✅ {html.escape(text)}</h3>"
            f"<p>用户：{html.escape(sp_user['Name'])}</p>"
            f"<p>位置：{position} 秒</p>"
            "<script>setTimeout(()=>history.back(),800)</script></body></html>"
        )
        return HTMLResponse(body)
    return HTMLResponse("<h3>⚠️ SenPlayer 已返回进度，但写入 Emby 失败。</h3>", status_code=502)


@app.get("/senplayer-media/{server_id}/{item_id}/{sig}")
async def senplayer_media(server_id: int, item_id: str, sig: str):
    server_row = get_server(server_id)
    if not server_row:
        raise HTTPException(status_code=404)
    server = dict(server_row)
    if not _verify_senplayer_signature(server, item_id, sig):
        raise HTTPException(status_code=404)

    emby_base = normalize_url(server.get("senplayer_emby_url") or server.get("emby_url") or "")
    api_key = str(server.get("emby_api_key") or "").strip()
    if not emby_base or not api_key:
        raise HTTPException(status_code=503, detail="SenPlayer Emby 地址或 API Key 未配置")

    target = f"{emby_base}/emby/Videos/{quote(item_id, safe='')}/stream?Static=true&api_key={quote(api_key, safe='')}"
    return RedirectResponse(target, status_code=307)


@app.get("/health")
def health():
    return {"ok": True}


from app.potplayer_sync import PotPlayerSync
pot_sync = PotPlayerSync(app, globals())
