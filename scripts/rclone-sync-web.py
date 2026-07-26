#!/usr/bin/env python3
"""Small authenticated rclone one-way sync controller."""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from collections import OrderedDict

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.serving import make_server


APP_ROOT = Path("/root/docker-compose/rclone-sync")
SETTINGS_FILE = APP_ROOT / "settings.json"
STATE_FILE = APP_ROOT / "state.json"
LOG_FILE = APP_ROOT / "logs" / "sync.log"
RCLONE_CONFIG = Path("/root/.config/rclone/rclone.conf")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
BROWSE_CACHE_TTL_SECONDS = 300
BROWSE_CACHE_MAX_ENTRIES = 8
BROWSE_CACHE_MAX_ITEMS = 200_000
ALLOWED_LOCAL_ROOTS = (
    Path("/home"),
    Path("/media"),
    Path("/mnt"),
    Path("/srv"),
    Path("/root/docker-compose/symedia"),
    APP_ROOT / "data",
)
METADATA_EXTENSIONS = (
    "strm",
    "nfo",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
    "srt",
    "ass",
    "ssa",
    "sub",
    "idx",
    "xml",
)


def read_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default.copy()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def initial_settings(username: str, password: str) -> dict:
    return {
        "secret_key": secrets.token_hex(32),
        "username": username,
        "password_hash": generate_password_hash(password),
        "must_change_password": password == "admin",
        "remote": "",
        "remote_path": "",
        "local_path": "/home/symedia_gd",
        "interval_minutes": 10,
        "enabled": False,
        "mode": "copy",
        "metadata_only": False,
        "confirm_mirror": False,
        "transfers": 4,
        "checkers": 8,
    }


def initialize() -> None:
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    (APP_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (APP_ROOT / "data").mkdir(parents=True, exist_ok=True)
    RCLONE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        username = os.environ.get("RCLONE_SYNC_INITIAL_USER", "admin").strip()
        password = os.environ.get("RCLONE_SYNC_INITIAL_PASSWORD", "admin")
        if not username:
            username = "admin"
        if not password:
            password = "admin"
        write_json(SETTINGS_FILE, initial_settings(username, password))
    if not STATE_FILE.exists():
        write_json(
            STATE_FILE,
            {
                "running": False,
                "pid": None,
                "last_started": None,
                "last_finished": None,
                "last_exit_code": None,
                "last_message": "尚未运行",
            },
        )
    LOG_FILE.touch(exist_ok=True)
    os.chmod(LOG_FILE, 0o600)


initialize()
settings_lock = threading.RLock()
state_lock = threading.RLock()
settings = read_json(SETTINGS_FILE, initial_settings("admin", "admin"))
if "confirm_mirror" not in settings:
    # A previously saved sync mode already passed the mandatory confirmation.
    settings["confirm_mirror"] = settings.get("mode") == "sync"
    write_json(SETTINGS_FILE, settings)
state = read_json(STATE_FILE, {})
if state.get("running"):
    state.update(
        {
            "running": False,
            "pid": None,
            "last_message": "控制台重启，上一同步进程已结束",
        }
    )
    write_json(STATE_FILE, state)
sync_process: subprocess.Popen | None = None
stop_event = threading.Event()
browse_cache_lock = threading.RLock()
browse_cache: OrderedDict[tuple[str, str], tuple[float, list[dict]]] = OrderedDict()
log_event_lock = threading.RLock()

app = Flask(__name__)
app.secret_key = settings["secret_key"]
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


BASE_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }} · Rclone 同步</title>
  <style>
    :root{color-scheme:light;--bg:#f4f7fb;--card:#fff;--ink:#182230;--muted:#65758b;
      --line:#dbe3ec;--blue:#1769e0;--green:#16845b;--red:#c0362c;--amber:#a15c00}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
      font:15px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
    header{background:#111c2d;color:#fff;padding:16px 24px;display:flex;
      justify-content:space-between;align-items:center} header a{color:#fff;text-decoration:none}
    main{max-width:1100px;margin:24px auto;padding:0 16px}.grid{display:grid;
      grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:18px}
    .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
      padding:20px;box-shadow:0 4px 18px #1d35570c}.wide{grid-column:1/-1}
    h1,h2{margin:0 0 14px} h1{font-size:22px} h2{font-size:18px}
    label{display:block;font-weight:650;margin:12px 0 5px}input,select{
      width:100%;padding:10px 11px;border:1px solid #b9c6d5;border-radius:8px;background:#fff}
    input[type=checkbox]{width:auto;margin-right:7px}.row{display:flex;gap:10px;align-items:end}
    .row>*{flex:1}.btn{display:inline-block;width:auto;border:0;border-radius:8px;
      padding:10px 15px;background:var(--blue);color:#fff;font-weight:700;cursor:pointer}
    .btn.secondary{background:#53657c}.btn.danger{background:var(--red)}
    .btn.good{background:var(--green)}.muted{color:var(--muted)}.warn{color:var(--amber)}
    .bad{color:var(--red)}.ok{color:var(--green)}
    .log-window{white-space:pre-wrap;min-height:560px;height:62vh;max-height:1200px;
      resize:vertical;overflow:auto;background:#0e1726;color:#d7e3f3;padding:14px;
      border-radius:9px;font:12px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace}
    .log-toolbar{display:flex;justify-content:space-between;gap:12px;align-items:center;
      margin-bottom:8px;flex-wrap:wrap}
    .flash{padding:10px 13px;margin:0 0 14px;border-radius:8px;background:#e7f1ff}
    .dir{display:block;width:100%;text-align:left;background:#f5f8fc;color:#234;
      border:1px solid var(--line);padding:8px;margin:5px 0;border-radius:7px;cursor:pointer}
    .dir-tools{display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap}
    .dir-tools select{width:auto;min-width:82px;padding:7px}.dir-tools .btn{padding:7px 11px}
    .dir-tools .btn:disabled{opacity:.45;cursor:not-allowed}
    nav a{margin-left:15px}.status{font-size:28px;font-weight:800}.small{font-size:13px}
  </style>
</head>
<body>
<header><strong>Rclone 单向同步控制台</strong>
{% if session.get("user") %}<nav><a href="{{ url_for('dashboard') }}">控制台</a>
<a href="{{ url_for('account') }}">账号</a><a href="{{ url_for('logout') }}">退出</a></nav>{% endif %}
</header>
<main>
{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}
{{ body|safe }}
</main>
</body></html>
"""


def page(title: str, body: str, **context):
    rendered_body = render_template_string(body, **context)
    return render_template_string(BASE_TEMPLATE, title=title, body=rendered_body)


def save_settings() -> None:
    with settings_lock:
        write_json(SETTINGS_FILE, settings)


def save_state() -> None:
    with state_lock:
        write_json(STATE_FILE, state)


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def require_csrf() -> None:
    token = request.form.get("csrf", "")
    if not token or not secrets.compare_digest(token, session.get("csrf", "")):
        raise ValueError("页面令牌已失效，请刷新后重试。")


def authenticated() -> bool:
    return session.get("user") == settings.get("username")


@app.before_request
def enforce_login():
    allowed = {"login", "healthz", "static"}
    if request.endpoint in allowed:
        return None
    if not authenticated():
        return redirect(url_for("login"))
    if settings.get("must_change_password") and request.endpoint not in {
        "account",
        "logout",
    }:
        flash("当前仍是默认 admin/admin，请先修改密码。")
        return redirect(url_for("account"))
    return None


@app.route("/healthz")
def healthz():
    return jsonify(ok=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if (
            secrets.compare_digest(username, settings.get("username", ""))
            and check_password_hash(settings.get("password_hash", ""), password)
        ):
            session.clear()
            session["user"] = username
            csrf_token()
            return redirect(url_for("dashboard"))
        flash("账号或密码错误。")
    return page(
        "登录",
        """
        <div class="card" style="max-width:430px;margin:70px auto">
        <h1>登录同步控制台</h1>
        <form method="post">
          <label>账号</label><input name="username" autocomplete="username" required>
          <label>密码</label><input name="password" type="password"
            autocomplete="current-password" required>
          <p><button class="btn" type="submit">登录</button></p>
        </form></div>
        """,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def rclone_remotes() -> list[str]:
    if not RCLONE_CONFIG.is_file():
        return []
    result = subprocess.run(
        ["rclone", "listremotes", "--config", str(RCLONE_CONFIG)],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.rstrip(":") for line in result.stdout.splitlines() if line]


def clean_remote_path(value: str) -> str:
    value = value.strip().strip("/")
    parts = [part for part in value.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("远程目录不能包含 . 或 ..。")
    return "/".join(parts)


def validate_local_path(value: str) -> str:
    candidate = Path(value.strip())
    if not candidate.is_absolute():
        raise ValueError("本地目录必须使用绝对路径。")
    resolved = candidate.resolve(strict=False)
    allowed = any(
        resolved == root or root in resolved.parents for root in ALLOWED_LOCAL_ROOTS
    )
    if not allowed:
        roots = "、".join(str(root) for root in ALLOWED_LOCAL_ROOTS)
        raise ValueError(f"本地目录只允许位于：{roots}")
    resolved.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def sync_status() -> dict:
    with state_lock:
        snapshot = state.copy()
    snapshot["config_exists"] = RCLONE_CONFIG.is_file()
    snapshot["local_free"] = None
    local_path = settings.get("local_path", "")
    try:
        usage = shutil.disk_usage(local_path)
        snapshot["local_free"] = f"{usage.free / 1024**3:.2f} GiB"
    except OSError:
        pass
    return snapshot


def read_log_tail(max_bytes: int = 512 * 1024, max_lines: int = 800) -> str:
    try:
        with LOG_FILE.open("rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            file_size = log_file.tell()
            start = max(0, file_size - max_bytes)
            log_file.seek(start)
            raw = log_file.read()
        text = raw.decode("utf-8", errors="replace")
        if start > 0 and "\n" in text:
            text = text.split("\n", 1)[1]
        return "\n".join(text.splitlines()[-max_lines:])
    except OSError:
        return ""


def append_log_event(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds").replace("T", " ")
    with log_event_lock:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as log_file:
                log_file.write(f"\n===== [{timestamp}] {message} =====\n")
        except OSError:
            app.logger.warning("无法写入同步事件日志：%s", message)


@app.route("/")
def dashboard():
    remotes = rclone_remotes()
    status = sync_status()
    log_text = read_log_tail()
    return page(
        "控制台",
        """
        <div class="grid">
          <section class="card">
            <h2>运行状态</h2>
            <div id="sync-state" class="status {{ 'ok' if status.running else '' }}">
              {{ '同步中' if status.running else '空闲' }}
            </div>
            <p>开始时间：<span id="last-started">{{ status.last_started or '无' }}</span><br>
            结束时间：<span id="last-finished">{{ status.last_finished or '无' }}</span><br>
            退出码：<span id="last-exit-code">{{ status.last_exit_code if status.last_exit_code is not none else '无' }}</span><br>
            进程 PID：<span id="sync-pid">{{ status.pid or '无' }}</span><br>
            本地剩余：<span id="local-free">{{ status.local_free or '未知' }}</span></p>
            <p id="sync-message" class="muted">{{ status.last_message }}</p>
            <p id="live-updated" class="small muted">实时状态连接中……</p>
            <form method="post" action="{{ url_for('start_sync') }}" style="display:inline">
              <input type="hidden" name="csrf" value="{{ csrf }}">
              <button class="btn good" type="submit">立即同步</button>
            </form>
            <form method="post" action="{{ url_for('stop_sync') }}" style="display:inline">
              <input type="hidden" name="csrf" value="{{ csrf }}">
              <button class="btn danger" type="submit">停止</button>
            </form>
          </section>

          <section class="card">
            <h2>上传 rclone.conf</h2>
            <p class="muted">保存到 /root/.config/rclone/rclone.conf。
            页面只显示远程名称，不显示 Token 和密钥。</p>
            <form method="post" action="{{ url_for('upload_config') }}"
              enctype="multipart/form-data">
              <input type="hidden" name="csrf" value="{{ csrf }}">
              <input type="file" name="config" accept=".conf,text/plain" required>
              <p><button class="btn" type="submit">验证并上传</button></p>
            </form>
            <p>配置状态：
              <strong class="{{ 'ok' if status.config_exists else 'bad' }}">
              {{ '已上传' if status.config_exists else '未上传' }}</strong><br>
              已识别：{{ remotes|join('、') if remotes else '无' }}
            </p>
          </section>

          <section class="card wide">
            <h2>同步设置</h2>
            <form method="post" action="{{ url_for('save_sync') }}">
              <input type="hidden" name="csrf" value="{{ csrf }}">
              <div class="row">
                <div><label>团队盘账号（rclone remote）</label>
                  <select id="remote" name="remote" required>
                    <option value="">请选择</option>
                    {% for remote in remotes %}<option value="{{ remote }}"
                      {{ 'selected' if remote == settings.remote else '' }}>{{ remote }}</option>
                    {% endfor %}
                  </select></div>
                <div><label>团队盘备份目录</label>
                  <input id="remote_path" name="remote_path"
                    value="{{ settings.remote_path }}" placeholder="例如 Symedia备份"></div>
                <div style="flex:0 0 auto"><button id="browse" class="btn secondary"
                  type="button">读取目录</button></div>
              </div>
              <div id="directories" class="small"></div>
              <label>同步到本地目录</label>
              <input name="local_path" value="{{ settings.local_path }}" required>
              <div class="row">
                <div><label>轮询间隔（分钟）</label>
                  <input name="interval_minutes" type="number" min="1" max="1440"
                    value="{{ settings.interval_minutes }}" required></div>
                <div><label>传输并发</label>
                  <input name="transfers" type="number" min="1" max="16"
                    value="{{ settings.transfers }}" required></div>
                <div><label>检查并发</label>
                  <input name="checkers" type="number" min="1" max="32"
                    value="{{ settings.checkers }}" required></div>
              </div>
              <label>同步模式</label>
              <select name="mode">
                <option value="copy" {{ 'selected' if settings.mode == 'copy' else '' }}>
                  增量复制（推荐：不删除本地文件）</option>
                <option value="sync" {{ 'selected' if settings.mode == 'sync' else '' }}>
                  镜像同步（危险：删除本地多余文件）</option>
              </select>
              <p><label><input type="checkbox" name="metadata_only"
                {{ 'checked' if settings.metadata_only else '' }}>
                只传 STRM、NFO、图片和字幕，排除影片本体</label></p>
              <p><label><input type="checkbox" name="enabled"
                {{ 'checked' if settings.enabled else '' }}>启用定时同步</label></p>
              <p><label><input type="checkbox" name="confirm_mirror"
                {{ 'checked' if settings.confirm_mirror else '' }}>
                若选择镜像同步，我确认本地多余文件会被删除</label></p>
              <button class="btn" type="submit">保存设置</button>
            </form>
          </section>

          <section class="card wide">
            <div class="log-toolbar">
              <h2 style="margin:0">实时同步日志</h2>
              <span class="small muted">每 2 秒自动更新；向上滚动时不会强制回到底部</span>
            </div>
            <pre id="sync-log" class="log-window">{{ log_text or '暂无日志' }}</pre>
          </section>
        </div>
        <script>
        const browse = document.getElementById('browse');
        let directoryPage = 1;
        let directoryPageSize = '20';
        async function loadDirs(page=1, refresh=false) {
          directoryPage = page;
          const remote = document.getElementById('remote').value;
          const path = document.getElementById('remote_path').value;
          const box = document.getElementById('directories');
          if (!remote) { box.textContent = '请先选择团队盘账号。'; return; }
          box.textContent = '正在读取……';
          const response = await fetch('/api/browse?remote=' +
            encodeURIComponent(remote) + '&path=' + encodeURIComponent(path) +
            '&page=' + encodeURIComponent(page) +
            '&page_size=' + encodeURIComponent(directoryPageSize) +
            (refresh ? '&refresh=1' : ''));
          const data = await response.json();
          if (!response.ok) { box.textContent = data.error || '读取失败'; return; }
          box.innerHTML = '';
          directoryPage = data.page;
          const tools = document.createElement('div'); tools.className='dir-tools';
          const summary = document.createElement('span');
          summary.textContent = '共 ' + data.total + ' 个目录，第 ' +
            data.page + '/' + data.pages + ' 页';
          const sizeLabel = document.createElement('span'); sizeLabel.textContent='每页';
          const size = document.createElement('select');
          for (const value of ['20','50','100','all']) {
            const option=document.createElement('option'); option.value=value;
            option.textContent=value === 'all' ? '全部' : value;
            option.selected=String(data.page_size) === value;
            size.appendChild(option);
          }
          size.onchange=()=>{directoryPageSize=size.value;loadDirs(1)};
          const previous=document.createElement('button'); previous.type='button';
          previous.className='btn secondary'; previous.textContent='上一页';
          previous.disabled=data.page <= 1;
          previous.onclick=()=>loadDirs(data.page-1);
          const next=document.createElement('button'); next.type='button';
          next.className='btn secondary'; next.textContent='下一页';
          next.disabled=data.page >= data.pages;
          next.onclick=()=>loadDirs(data.page+1);
          const reload=document.createElement('button'); reload.type='button';
          reload.className='btn secondary'; reload.textContent='刷新目录';
          reload.onclick=()=>loadDirs(data.page, true);
          tools.append(summary,sizeLabel,size,previous,next,reload);
          box.appendChild(tools);
          if (data.parent !== null) {
            const up = document.createElement('button'); up.type='button';
            up.className='dir'; up.textContent='⬆ 返回上级';
            up.onclick=()=>{document.getElementById('remote_path').value=data.parent;loadDirs(1)};
            box.appendChild(up);
          }
          data.dirs.forEach((dir, index) => {
            const button=document.createElement('button'); button.type='button';
            button.className='dir';
            button.textContent=(data.start_index + index + 1) + '. 📁 ' + dir.name;
            button.onclick=()=>{document.getElementById('remote_path').value=dir.path;loadDirs(1)};
            box.appendChild(button);
          });
          if (!data.dirs.length) box.append('当前目录没有子目录。');
        }
        browse.addEventListener('click', ()=>loadDirs(1));

        const logBox = document.getElementById('sync-log');
        let liveRequestRunning = false;
        async function refreshLiveStatus() {
          if (liveRequestRunning) return;
          liveRequestRunning = true;
          const updated = document.getElementById('live-updated');
          try {
            const response = await fetch('/api/live', {cache: 'no-store'});
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '读取失败');
            const status = data.status;
            const stateBox = document.getElementById('sync-state');
            stateBox.textContent = status.running ? '同步中' : '空闲';
            stateBox.className = 'status' + (status.running ? ' ok' : '');
            document.getElementById('last-started').textContent =
              status.last_started || '无';
            document.getElementById('last-finished').textContent =
              status.last_finished || '无';
            document.getElementById('last-exit-code').textContent =
              status.last_exit_code === null || status.last_exit_code === undefined
                ? '无' : status.last_exit_code;
            document.getElementById('sync-pid').textContent = status.pid || '无';
            document.getElementById('local-free').textContent =
              status.local_free || '未知';
            document.getElementById('sync-message').textContent =
              status.last_message || '';
            updated.textContent = '最后刷新：' +
              new Date().toLocaleTimeString() + '（服务器：' + data.server_time + '）';
            const followBottom = logBox.scrollHeight - logBox.scrollTop -
              logBox.clientHeight < 90;
            const nextLog = data.log || '暂无日志';
            if (logBox.textContent !== nextLog) {
              logBox.textContent = nextLog;
              if (followBottom) logBox.scrollTop = logBox.scrollHeight;
            }
          } catch (error) {
            updated.textContent = '实时连接暂时中断，正在自动重试：' + error.message;
          } finally {
            liveRequestRunning = false;
          }
        }
        logBox.scrollTop = logBox.scrollHeight;
        refreshLiveStatus();
        setInterval(refreshLiveStatus, 2000);
        </script>
        """,
        settings=settings,
        status=status,
        remotes=remotes,
        log_text=log_text,
        csrf=csrf_token(),
    )


@app.route("/api/live")
def live_status():
    return jsonify(
        status=sync_status(),
        log=read_log_tail(),
        server_time=datetime.now().isoformat(timespec="seconds").replace("T", " "),
    )


@app.route("/api/browse")
def browse_remote():
    remote = request.args.get("remote", "")
    if remote not in rclone_remotes():
        return jsonify(error="无效的团队盘账号。"), 400
    try:
        path = clean_remote_path(request.args.get("path", ""))
        page_size = request.args.get("page_size", "20").lower()
        if page_size not in {"20", "50", "100", "all"}:
            raise ValueError("每页数量只能是 20、50、100 或全部。")
        page = max(1, int(request.args.get("page", "1")))
        cache_key = (remote, path)
        refresh = request.args.get("refresh") == "1"
        now = time.monotonic()
        with browse_cache_lock:
            cached = browse_cache.get(cache_key)
            if cached and now - cached[0] <= BROWSE_CACHE_TTL_SECONDS and not refresh:
                dirs = cached[1]
                browse_cache.move_to_end(cache_key)
            else:
                dirs = None
        if dirs is None:
            target = f"{remote}:{path}"
            result = subprocess.run(
                [
                    "rclone",
                    "lsf",
                    target,
                    "--config",
                    str(RCLONE_CONFIG),
                    "--dirs-only",
                    "--max-depth",
                    "1",
                ],
                text=True,
                capture_output=True,
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                return jsonify(
                    error=result.stderr.strip()[-500:] or "rclone 读取失败"
                ), 400
            dirs = []
            for item in result.stdout.splitlines():
                name = item.rstrip("/")
                if not name:
                    continue
                child = "/".join(value for value in (path, name) if value)
                dirs.append({"name": name, "path": child})
            dirs.sort(key=lambda item: item["name"].casefold())
            with browse_cache_lock:
                browse_cache[cache_key] = (now, dirs)
                browse_cache.move_to_end(cache_key)
                while len(browse_cache) > 1 and (
                    len(browse_cache) > BROWSE_CACHE_MAX_ENTRIES
                    or sum(len(value[1]) for value in browse_cache.values())
                    > BROWSE_CACHE_MAX_ITEMS
                ):
                    browse_cache.popitem(last=False)
        total = len(dirs)
        if page_size == "all":
            pages = 1
            page = 1
            start_index = 0
            visible_dirs = dirs
        else:
            size = int(page_size)
            pages = max(1, math.ceil(total / size))
            page = min(page, pages)
            start_index = (page - 1) * size
            visible_dirs = dirs[start_index:start_index + size]
        parent = None if not path else "/".join(path.split("/")[:-1])
        return jsonify(
            current=path,
            parent=parent,
            dirs=visible_dirs,
            total=total,
            page=page,
            pages=pages,
            page_size=page_size,
            start_index=start_index,
        )
    except (ValueError, subprocess.TimeoutExpired) as error:
        return jsonify(error=str(error)), 400


@app.route("/upload-config", methods=["POST"])
def upload_config():
    try:
        require_csrf()
        upload = request.files.get("config")
        if upload is None or not upload.filename:
            raise ValueError("没有选择配置文件。")
        RCLONE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="rclone.", suffix=".conf", dir=RCLONE_CONFIG.parent, delete=False
        ) as temporary:
            upload.save(temporary)
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        result = subprocess.run(
            ["rclone", "listremotes", "--config", str(temporary_path)],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            temporary_path.unlink(missing_ok=True)
            raise ValueError("配置验证失败，未发现可用 remote。")
        if RCLONE_CONFIG.exists():
            backup = RCLONE_CONFIG.with_name(
                f"rclone.conf.backup-{datetime.now():%Y%m%d-%H%M%S}"
            )
            shutil.copy2(RCLONE_CONFIG, backup)
            os.chmod(backup, 0o600)
        os.replace(temporary_path, RCLONE_CONFIG)
        os.chmod(RCLONE_CONFIG, 0o600)
        with browse_cache_lock:
            browse_cache.clear()
        flash("rclone.conf 已验证并上传。")
    except (ValueError, subprocess.TimeoutExpired, OSError) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/save-sync", methods=["POST"])
def save_sync():
    try:
        require_csrf()
        remote = request.form.get("remote", "")
        if remote not in rclone_remotes():
            raise ValueError("请选择有效的团队盘账号。")
        mode = request.form.get("mode", "copy")
        if mode not in {"copy", "sync"}:
            raise ValueError("同步模式无效。")
        if mode == "sync" and request.form.get("confirm_mirror") != "on":
            raise ValueError("镜像同步会删除本地文件，必须勾选确认。")
        interval = max(1, min(1440, int(request.form.get("interval_minutes", "10"))))
        transfers = max(1, min(16, int(request.form.get("transfers", "4"))))
        checkers = max(1, min(32, int(request.form.get("checkers", "8"))))
        with settings_lock:
            settings.update(
                {
                    "remote": remote,
                    "remote_path": clean_remote_path(
                        request.form.get("remote_path", "")
                    ),
                    "local_path": validate_local_path(
                        request.form.get("local_path", "")
                    ),
                    "interval_minutes": interval,
                    "transfers": transfers,
                    "checkers": checkers,
                    "mode": mode,
                    "metadata_only": request.form.get("metadata_only") == "on",
                    "enabled": request.form.get("enabled") == "on",
                    "confirm_mirror": (
                        mode == "sync"
                        and request.form.get("confirm_mirror") == "on"
                    ),
                }
            )
            write_json(SETTINGS_FILE, settings)
        flash("同步设置已保存。")
    except (ValueError, OSError) as error:
        app.logger.warning("同步设置保存失败：%s", error)
        flash(str(error))
    return redirect(url_for("dashboard"))


def build_command() -> list[str]:
    with settings_lock:
        current = settings.copy()
    remote = current.get("remote", "")
    if remote not in rclone_remotes():
        raise ValueError("rclone.conf 中找不到已选择的 remote。")
    source = f"{remote}:{clean_remote_path(current.get('remote_path', ''))}"
    destination = validate_local_path(current.get("local_path", ""))
    command = [
        "rclone",
        current.get("mode", "copy"),
        source,
        destination,
        "--config",
        str(RCLONE_CONFIG),
        "--transfers",
        str(current.get("transfers", 4)),
        "--checkers",
        str(current.get("checkers", 8)),
        "--create-empty-src-dirs",
        "--stats",
        "30s",
        "--log-file",
        str(LOG_FILE),
        "--log-level",
        "INFO",
        "--retries",
        "3",
        "--low-level-retries",
        "10",
    ]
    if current.get("mode") == "sync":
        command.extend(["--delete-after", "--max-delete", "10000"])
    if current.get("metadata_only"):
        for extension in METADATA_EXTENSIONS:
            command.extend(["--include", f"*.{extension}"])
        command.extend(["--exclude", "*"])
    return command


def monitor_process(process: subprocess.Popen) -> None:
    global sync_process
    exit_code = process.wait()
    with state_lock:
        state.update(
            {
                "running": False,
                "pid": None,
                "last_finished": datetime.now().isoformat(timespec="seconds"),
                "last_exit_code": exit_code,
                "last_message": "同步完成" if exit_code == 0 else "同步失败，请查看日志",
            }
        )
        write_json(STATE_FILE, state)
    append_log_event(f"同步任务结束，退出码={exit_code}")
    sync_process = None


def launch_sync() -> None:
    global sync_process
    with state_lock:
        if sync_process is not None and sync_process.poll() is None:
            raise ValueError("同步任务已经在运行。")
    command = build_command()
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    sync_process = process
    with settings_lock:
        current_mode = settings.get("mode", "copy")
        current_remote = settings.get("remote", "")
        current_remote_path = settings.get("remote_path", "")
        current_local_path = settings.get("local_path", "")
    mode_name = "镜像同步" if current_mode == "sync" else "增量复制"
    with state_lock:
        state.update(
            {
                "running": True,
                "pid": process.pid,
                "last_started": datetime.now().isoformat(timespec="seconds"),
                "last_exit_code": None,
                "last_message": f"正在扫描并执行{mode_name}",
            }
        )
        write_json(STATE_FILE, state)
    append_log_event(
        f"同步任务开始，PID={process.pid}，模式={mode_name}，"
        f"来源={current_remote}:{current_remote_path}，目标={current_local_path}"
    )
    threading.Thread(
        target=monitor_process, args=(process,), daemon=True
    ).start()


@app.route("/start", methods=["POST"])
def start_sync():
    try:
        require_csrf()
        launch_sync()
        flash("同步任务已启动。")
    except (ValueError, OSError) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/stop", methods=["POST"])
def stop_sync():
    try:
        require_csrf()
        process = sync_process
        if process is None or process.poll() is not None:
            raise ValueError("当前没有运行中的同步任务。")
        os.killpg(process.pid, signal.SIGTERM)
        append_log_event(f"用户请求停止同步任务，PID={process.pid}")
        flash("已发送停止信号。")
    except (ValueError, ProcessLookupError) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        try:
            require_csrf()
            old_password = request.form.get("old_password", "")
            new_username = request.form.get("username", "").strip()
            new_password = request.form.get("new_password", "")
            if not check_password_hash(settings["password_hash"], old_password):
                raise ValueError("原密码错误。")
            if len(new_username) < 3:
                raise ValueError("账号至少需要 3 个字符。")
            if len(new_password) < 8:
                raise ValueError("新密码至少需要 8 个字符。")
            with settings_lock:
                settings["username"] = new_username
                settings["password_hash"] = generate_password_hash(new_password)
                settings["must_change_password"] = False
                write_json(SETTINGS_FILE, settings)
            session.clear()
            flash("账号密码已修改，请重新登录。")
            return redirect(url_for("login"))
        except ValueError as error:
            flash(str(error))
    return page(
        "账号设置",
        """
        <div class="card" style="max-width:560px;margin:auto">
          <h1>修改控制台账号</h1>
          {% if settings.must_change_password %}<p class="bad">
          当前使用默认 admin/admin，必须先修改才能进入控制台。</p>{% endif %}
          <form method="post">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <label>新账号</label><input name="username" value="{{ settings.username }}" required>
            <label>原密码</label><input name="old_password" type="password" required>
            <label>新密码（至少 8 位）</label>
            <input name="new_password" type="password" required>
            <p><button class="btn" type="submit">保存并重新登录</button></p>
          </form>
        </div>
        """,
        settings=settings,
        csrf=csrf_token(),
    )


def scheduler_loop() -> None:
    next_run = time.monotonic() + 30
    while not stop_event.wait(10):
        with settings_lock:
            enabled = bool(settings.get("enabled"))
            interval = max(1, int(settings.get("interval_minutes", 10))) * 60
        if not enabled:
            next_run = time.monotonic() + 30
            continue
        if time.monotonic() < next_run:
            continue
        try:
            launch_sync()
        except (ValueError, OSError) as error:
            with state_lock:
                state["last_message"] = f"定时启动失败：{error}"
                write_json(STATE_FILE, state)
        next_run = time.monotonic() + interval


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=6096, type=int)
    args = parser.parse_args()
    if args.init:
        return
    threading.Thread(target=scheduler_loop, daemon=True).start()
    server = make_server(args.host, args.port, app, threaded=True)
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        if sync_process is not None and sync_process.poll() is None:
            os.killpg(sync_process.pid, signal.SIGTERM)


if __name__ == "__main__":
    main()
