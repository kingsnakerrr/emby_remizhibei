#!/usr/bin/env python3
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LISTEN_HOST = os.getenv("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8097"))
EMBY_BASE_URL = os.getenv("EMBY_BASE_URL", "http://127.0.0.1:8096").rstrip("/")
LIBRARY_DB = os.getenv("LIBRARY_DB", "/emby-data/library.db")
ALLOWED_MEDIA_PREFIX = os.getenv(
    "ALLOWED_MEDIA_PREFIX", "/CloudNAS/CloudDrive/GoogleDrive/zero/"
)
READ_BUFFER = int(os.getenv("READ_BUFFER", str(1024 * 1024)))
AUTH_CACHE_SECONDS = int(os.getenv("AUTH_CACHE_SECONDS", "60"))

VIDEO_RE = re.compile(r"^/emby/videos/(\d+)/original(?:\.[^/]+)?$", re.IGNORECASE)
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
AUTH_CACHE = {}
AUTH_LOCK = threading.Lock()


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def extract_token(handler, query):
    token = (query.get("api_key") or [""])[0]
    if not token:
        token = handler.headers.get("X-Emby-Token", "")
    if not token:
        auth = handler.headers.get("X-Emby-Authorization", "")
        match = re.search(r'(?:Token|token)="?([^", ]+)', auth)
        if match:
            token = match.group(1)
    return token


def token_is_valid(handler, query):
    token = extract_token(handler, query)
    if not token:
        return False

    cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with AUTH_LOCK:
        expires = AUTH_CACHE.get(cache_key, 0)
        if expires > now:
            return True

    params = urllib.parse.urlencode({"api_key": token})
    request = urllib.request.Request(f"{EMBY_BASE_URL}/emby/System/Info?{params}")
    for name in ("Authorization", "X-Emby-Authorization", "X-Emby-Token"):
        value = handler.headers.get(name)
        if value:
            request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            valid = response.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        valid = False

    if valid:
        with AUTH_LOCK:
            AUTH_CACHE[cache_key] = now + AUTH_CACHE_SECONDS
    return valid


def lookup_media_path(item_id):
    uri = f"file:{LIBRARY_DB}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as database:
        row = database.execute(
            "SELECT Path FROM MediaItems WHERE Id = ?", (int(item_id),)
        ).fetchone()
    if not row or not row[0]:
        raise FileNotFoundError(f"Emby item {item_id} was not found")

    item_path = Path(row[0])
    if item_path.suffix.lower() == ".strm":
        target = item_path.read_text(encoding="utf-8-sig").splitlines()[0].strip()
    else:
        target = str(item_path)

    if not target.startswith(ALLOWED_MEDIA_PREFIX):
        raise ValueError("media path is not handled by the CD2 gateway")
    return Path(target)


def parse_range(value, size):
    if not value:
        return 0, size - 1, False
    if "," in value:
        raise ValueError("multiple ranges are not supported")
    match = RANGE_RE.match(value.strip())
    if not match:
        raise ValueError("invalid range")
    start_text, end_text = match.groups()
    if not start_text:
        suffix = int(end_text or "0")
        if suffix <= 0:
            raise ValueError("invalid suffix range")
        start = max(size - suffix, 0)
        end = size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    if start >= size or start < 0 or end < start:
        raise IndexError("range outside file")
    return start, min(end, size - 1), True


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "EmbyCD2Gateway/1.0"

    def send_json(self, status, data):
        body = json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.handle_request(send_body=False)

    def do_GET(self):
        self.handle_request(send_body=True)

    def handle_request(self, send_body):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/healthz":
            self.send_json(200, {"status": "ok", "source": "cd2"})
            return

        match = VIDEO_RE.match(parsed.path)
        if not match:
            self.send_json(404, {"error": "unsupported endpoint"})
            return

        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if not token_is_valid(self, query):
            self.send_json(401, {"error": "invalid Emby credentials"})
            return

        try:
            media_path = lookup_media_path(match.group(1))
        except FileNotFoundError as error:
            self.send_json(404, {"error": str(error)})
            return
        except (ValueError, UnicodeError, OSError) as error:
            self.send_json(409, {"error": str(error)})
            return

        try:
            stat = media_path.stat()
            if not media_path.is_file():
                raise FileNotFoundError(str(media_path))
            start, end, partial = parse_range(self.headers.get("Range"), stat.st_size)
        except IndexError:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{stat.st_size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        except (FileNotFoundError, OSError, ValueError) as error:
            self.send_json(503, {"error": f"CD2 media unavailable: {error}"})
            return

        length = end - start + 1
        content_type = mimetypes.guess_type(str(media_path))[0] or "application/octet-stream"
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        self.send_header("ETag", f'"cd2-{stat.st_size:x}-{int(stat.st_mtime):x}"')
        self.send_header("Cache-Control", "private, no-transform")
        self.send_header("X-Playback-Source", "cd2")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{stat.st_size}")
        self.end_headers()

        if not send_body:
            return

        try:
            remaining = length
            with media_path.open("rb", buffering=0) as source:
                source.seek(start)
                while remaining:
                    chunk = source.read(min(READ_BUFFER, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError as error:
            self.log_error("CD2 read failed for %s: %s", media_path, error)

    def log_message(self, fmt, *args):
        print(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"client={self.client_address[0]} {fmt % args}",
            flush=True,
        )


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), GatewayHandler)
    print(
        f"CD2 playback gateway listening on {LISTEN_HOST}:{LISTEN_PORT}; "
        f"Emby={EMBY_BASE_URL}; prefix={ALLOWED_MEDIA_PREFIX}",
        flush=True,
    )
    server.serve_forever()
