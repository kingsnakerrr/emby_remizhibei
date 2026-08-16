#!/usr/bin/env python3
"""Authenticated multi-task rclone sync controller.

This service is intentionally conservative. It supports multiple independent
sync tasks and refuses to use /home as a destination, because rclone sync against
/home can delete unrelated local files.
"""

from __future__ import annotations

import argparse
import json
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

from flask import Flask, flash, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.serving import make_server


APP_ROOT = Path("/root/docker-compose/rclone-sync")
SETTINGS_FILE = APP_ROOT / "settings.json"
STATE_FILE = APP_ROOT / "state.json"
LOG_FILE = APP_ROOT / "logs/sync.log"
RCLONE_CONFIG = Path("/root/.config/rclone/rclone.conf")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

ALLOWED_LOCAL_ROOTS = (Path("/home/symedia_gd"), Path("/home/symedia_jav"))
FORBIDDEN_LOCAL_PATHS = (Path("/"), Path("/home"))
METADATA_EXTENSIONS = (
    "strm", "nfo", "jpg", "jpeg", "png", "webp", "gif",
    "srt", "ass", "ssa", "sub", "idx", "xml",
)


def read_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default.copy()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default.copy()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".new")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def make_task(task_id: str, name: str, remote_path: str, local_path: str) -> dict:
    return {
        "id": task_id,
        "name": name,
        "remote": "",
        "remote_path": remote_path,
        "local_path": local_path,
        "interval_minutes": 10,
        "enabled": False,
        "mode": "copy",
        "metadata_only": False,
        "confirm_mirror": False,
        "transfers": 4,
        "checkers": 8,
    }


def default_tasks() -> list[dict]:
    return [
        make_task("symedia_gd", "symedia_gd", "media/symedia_gd", "/home/symedia_gd"),
        make_task("symedia_jav", "symedia_jav", "media/symedia_jav", "/home/symedia_jav"),
    ]


def initial_settings(username: str, password: str) -> dict:
    return {
        "secret_key": secrets.token_hex(32),
        "username": username,
        "password_hash": generate_password_hash(password),
        "must_change_password": password == "admin",
        "tasks": default_tasks(),
    }


def initial_state() -> dict:
    return {"tasks": {}, "last_message": "尚未运行"}


def migrate_settings(value: dict) -> dict:
    """Convert old single-task settings to the new multi-task format."""
    if isinstance(value.get("tasks"), list):
        tasks = []
        seen: set[str] = set()
        for raw in value["tasks"]:
            if not isinstance(raw, dict):
                continue
            task_id = str(raw.get("id") or f"task-{len(tasks) + 1}")
            task_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in task_id).strip("-_")
            task_id = task_id or f"task-{len(tasks) + 1}"
            if task_id in seen:
                task_id = f"{task_id}-{len(tasks) + 1}"
            seen.add(task_id)
            task = make_task(
                task_id,
                str(raw.get("name") or task_id),
                str(raw.get("remote_path") or ""),
                str(raw.get("local_path") or "/home/symedia_gd"),
            )
            task.update(raw)
            task["id"] = task_id
            tasks.append(task)
        value["tasks"] = tasks or default_tasks()
        return value

    migrated = initial_settings(value.get("username") or "admin", "admin")
    migrated["secret_key"] = value.get("secret_key") or migrated["secret_key"]
    migrated["password_hash"] = value.get("password_hash") or migrated["password_hash"]
    migrated["must_change_password"] = bool(value.get("must_change_password", False))
    remote = value.get("remote", "")
    remote_path = value.get("remote_path", "")
    local_path = value.get("local_path", "")
    for task in migrated["tasks"]:
        task["remote"] = remote
    if local_path == "/home/symedia_jav":
        migrated["tasks"][1]["remote_path"] = remote_path
    elif local_path == "/home/symedia_gd":
        migrated["tasks"][0]["remote_path"] = remote_path
    return migrated


def initialize() -> None:
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    (APP_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (APP_ROOT / "data").mkdir(parents=True, exist_ok=True)
    RCLONE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        user = os.environ.get("RCLONE_SYNC_INITIAL_USER", "admin").strip() or "admin"
        password = os.environ.get("RCLONE_SYNC_INITIAL_PASSWORD", "admin") or "admin"
        write_json(SETTINGS_FILE, initial_settings(user, password))
    if not STATE_FILE.exists():
        write_json(STATE_FILE, initial_state())
    LOG_FILE.touch(exist_ok=True)
    os.chmod(LOG_FILE, 0o600)


initialize()
settings_lock = threading.RLock()
state_lock = threading.RLock()
settings = migrate_settings(read_json(SETTINGS_FILE, initial_settings("admin", "admin")))
state = read_json(STATE_FILE, initial_state())
state.setdefault("tasks", {})
write_json(SETTINGS_FILE, settings)
write_json(STATE_FILE, state)

app = Flask(__name__)
app.secret_key = settings["secret_key"]
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

running_processes: dict[str, subprocess.Popen] = {}
stop_event = threading.Event()
log_lock = threading.RLock()


BASE_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }} · Rclone 多任务同步</title>
  <style>
    body{margin:0;background:#f4f7fb;color:#182230;font:15px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
    header{background:#111c2d;color:#fff;padding:16px 24px;display:flex;justify-content:space-between}
    header a{color:#fff;text-decoration:none;margin-left:14px} main{max-width:1180px;margin:24px auto;padding:0 16px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:18px}
    .card{background:#fff;border:1px solid #dbe3ec;border-radius:14px;padding:20px;box-shadow:0 4px 18px #1d35570c}
    .wide{grid-column:1/-1}.task{border-top:1px solid #dbe3ec;padding-top:14px;margin-top:16px}
    h1,h2,h3{margin:0 0 14px} label{display:block;font-weight:650;margin:12px 0 5px}
    input,select{width:100%;padding:10px;border:1px solid #b9c6d5;border-radius:8px;background:#fff}
    input[type=checkbox]{width:auto;margin-right:7px}.row{display:flex;gap:10px}.row>*{flex:1}
    .btn{display:inline-block;width:auto;border:0;border-radius:8px;padding:10px 15px;background:#1769e0;color:#fff;font-weight:700;cursor:pointer}
    .good{background:#16845b}.danger{background:#c0362c}.muted{color:#65758b}.bad{color:#c0362c}.ok{color:#16845b}
    .flash{padding:10px 13px;margin-bottom:14px;border-radius:8px;background:#e7f1ff}
    .status{font-size:24px;font-weight:800}.log{white-space:pre-wrap;height:58vh;overflow:auto;background:#0e1726;color:#d7e3f3;padding:14px;border-radius:9px;font:12px/1.55 Consolas,monospace}
    code{background:#edf2f7;padding:2px 4px;border-radius:4px}
  </style>
</head>
<body>
<header><strong>Rclone 多任务单向同步控制台</strong>
{% if session.get("user") %}<nav><a href="{{ url_for('dashboard') }}">控制台</a><a href="{{ url_for('account') }}">账号</a><a href="{{ url_for('logout') }}">退出</a></nav>{% endif %}
</header>
<main>{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}{{ body|safe }}</main>
</body></html>
"""


def page(title: str, body: str, **context):
    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        body=render_template_string(body, **context),
    )


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
    if request.endpoint in {"login", "healthz", "static"}:
        return None
    if not authenticated():
        return redirect(url_for("login"))
    if settings.get("must_change_password") and request.endpoint not in {"account", "logout"}:
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
        if secrets.compare_digest(username, settings.get("username", "")) and check_password_hash(settings.get("password_hash", ""), password):
            session.clear()
            session["user"] = username
            csrf_token()
            return redirect(url_for("dashboard"))
        flash("账号或密码错误。")
    return page("登录", """
      <div class="card" style="max-width:430px;margin:70px auto">
      <h1>登录同步控制台</h1>
      <form method="post">
        <label>账号</label><input name="username" autocomplete="username" required>
        <label>密码</label><input name="password" type="password" autocomplete="current-password" required>
        <p><button class="btn" type="submit">登录</button></p>
      </form></div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def rclone_remotes() -> list[str]:
    if not RCLONE_CONFIG.is_file():
        return []
    result = subprocess.run(["rclone", "listremotes", "--config", str(RCLONE_CONFIG)], text=True, capture_output=True, timeout=20, check=False)
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
    if any(resolved == forbidden for forbidden in FORBIDDEN_LOCAL_PATHS):
        raise ValueError("禁止把 / 或 /home 作为同步目标，请使用 /home/symedia_gd 或 /home/symedia_jav。")
    allowed = any(resolved == root or root in resolved.parents for root in ALLOWED_LOCAL_ROOTS)
    if not allowed:
        roots = "、".join(str(root) for root in ALLOWED_LOCAL_ROOTS)
        raise ValueError(f"本地目录只允许位于：{roots}")
    resolved.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def task_by_id(task_id: str) -> dict:
    for task in settings.get("tasks", []):
        if task.get("id") == task_id:
            return task
    raise ValueError("任务不存在。")


def task_state(task_id: str) -> dict:
    with state_lock:
        tasks = state.setdefault("tasks", {})
        return tasks.setdefault(task_id, {"running": False, "pid": None, "last_started": None, "last_finished": None, "last_exit_code": None, "last_message": "尚未运行"})


def sync_status() -> dict:
    result = {"config_exists": RCLONE_CONFIG.is_file(), "tasks": {}}
    with settings_lock:
        tasks = [task.copy() for task in settings.get("tasks", [])]
    for task in tasks:
        item = task_state(task["id"]).copy()
        process = running_processes.get(task["id"])
        item["running"] = process is not None and process.poll() is None
        item["local_free"] = None
        try:
            usage = shutil.disk_usage(task.get("local_path", "/"))
            item["local_free"] = f"{usage.free / 1024**3:.2f} GiB"
        except OSError:
            pass
        result["tasks"][task["id"]] = item
    return result


def read_log_tail(max_bytes: int = 512 * 1024, max_lines: int = 800) -> str:
    try:
        with LOG_FILE.open("rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - max_bytes))
            text = log_file.read().decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[-max_lines:])
    except OSError:
        return ""


def append_log_event(message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds").replace("T", " ")
    with log_lock:
        with LOG_FILE.open("a", encoding="utf-8") as log_file:
            log_file.write(f"\n===== [{timestamp}] {message} =====\n")


@app.route("/")
def dashboard():
    return page("控制台", """
      <div class="grid">
        <section class="card">
          <h2>上传 rclone.conf</h2>
          <p class="muted">保存到 <code>/root/.config/rclone/rclone.conf</code>。页面只显示 remote 名称。</p>
          <form method="post" action="{{ url_for('upload_config') }}" enctype="multipart/form-data">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <input type="file" name="config" accept=".conf,text/plain" required>
            <p><button class="btn" type="submit">验证并上传</button></p>
          </form>
          <p>配置状态：<strong class="{{ 'ok' if status.config_exists else 'bad' }}">{{ '已上传' if status.config_exists else '未上传' }}</strong><br>
          已识别：{{ remotes|join('、') if remotes else '无' }}</p>
        </section>
        <section class="card">
          <h2>安全边界</h2>
          <p>只允许同步到：</p>
          <p><code>/home/symedia_gd</code><br><code>/home/symedia_jav</code></p>
          <p class="bad">禁止使用 <code>/home</code> 作为目标目录。</p>
        </section>
        <section class="card wide">
          <h2>同步任务</h2>
          {% for task in tasks %}
          {% set item = status.tasks.get(task.id, {}) %}
          <div class="task">
            <h3>{{ task.name }}</h3>
            <div class="status {{ 'ok' if item.running else '' }}">{{ '同步中' if item.running else '空闲' }}</div>
            <p class="muted">开始：{{ item.last_started or '无' }}　结束：{{ item.last_finished or '无' }}　退出码：{{ item.last_exit_code if item.last_exit_code is not none else '无' }}　PID：{{ item.pid or '无' }}　本地剩余：{{ item.local_free or '未知' }}</p>
            <p>{{ item.last_message or '' }}</p>
            <form method="post" action="{{ url_for('save_task') }}">
              <input type="hidden" name="csrf" value="{{ csrf }}">
              <input type="hidden" name="task_id" value="{{ task.id }}">
              <div class="row">
                <div><label>任务名</label><input name="name" value="{{ task.name }}" required></div>
                <div><label>Remote</label><select name="remote" required><option value="">请选择</option>{% for remote in remotes %}<option value="{{ remote }}" {{ 'selected' if remote == task.remote else '' }}>{{ remote }}</option>{% endfor %}</select></div>
              </div>
              <div class="row">
                <div><label>云端目录</label><input name="remote_path" value="{{ task.remote_path }}" required></div>
                <div><label>本地目录</label><input name="local_path" value="{{ task.local_path }}" required></div>
              </div>
              <div class="row">
                <div><label>间隔分钟</label><input name="interval_minutes" type="number" min="1" max="1440" value="{{ task.interval_minutes }}" required></div>
                <div><label>传输并发</label><input name="transfers" type="number" min="1" max="16" value="{{ task.transfers }}" required></div>
                <div><label>检查并发</label><input name="checkers" type="number" min="1" max="32" value="{{ task.checkers }}" required></div>
              </div>
              <label>同步模式</label>
              <select name="mode"><option value="copy" {{ 'selected' if task.mode == 'copy' else '' }}>增量复制 copy，不删除本地文件</option><option value="sync" {{ 'selected' if task.mode == 'sync' else '' }}>镜像同步 sync，只允许精确子目录</option></select>
              <p><label><input type="checkbox" name="metadata_only" {{ 'checked' if task.metadata_only else '' }}>只传 STRM、NFO、图片和字幕</label></p>
              <p><label><input type="checkbox" name="enabled" {{ 'checked' if task.enabled else '' }}>启用定时同步</label></p>
              <p><label><input type="checkbox" name="confirm_mirror" {{ 'checked' if task.confirm_mirror else '' }}>若选择镜像同步，我确认只会删除本任务目录内多余文件</label></p>
              <p>
                <button class="btn" type="submit">保存任务</button>
                <button class="btn good" formaction="{{ url_for('start_sync') }}" type="submit">立即同步</button>
                <button class="btn danger" formaction="{{ url_for('stop_sync') }}" type="submit">停止</button>
              </p>
            </form>
          </div>
          {% endfor %}
        </section>
        <section class="card wide"><h2>日志</h2><pre id="sync-log" class="log">{{ log_text or '暂无日志' }}</pre></section>
      </div>
      <script>
      const logBox = document.getElementById('sync-log');
      logBox.scrollTop = logBox.scrollHeight;
      setInterval(async () => {
        const response = await fetch('/api/live', {cache: 'no-store'});
        const data = await response.json();
        if (data.log && logBox.textContent !== data.log) {
          const follow = logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight < 90;
          logBox.textContent = data.log;
          if (follow) logBox.scrollTop = logBox.scrollHeight;
        }
      }, 2000);
      </script>
    """, tasks=settings.get("tasks", []), status=sync_status(), remotes=rclone_remotes(), log_text=read_log_tail(), csrf=csrf_token())


@app.route("/api/live")
def live_status():
    return jsonify(status=sync_status(), log=read_log_tail(), server_time=datetime.now().isoformat(timespec="seconds").replace("T", " "))


@app.route("/upload-config", methods=["POST"])
def upload_config():
    try:
        require_csrf()
        upload = request.files.get("config")
        if upload is None or not upload.filename:
            raise ValueError("没有选择配置文件。")
        RCLONE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="rclone.", suffix=".conf", dir=RCLONE_CONFIG.parent, delete=False) as temp:
            upload.save(temp)
            temp_path = Path(temp.name)
        os.chmod(temp_path, 0o600)
        result = subprocess.run(["rclone", "listremotes", "--config", str(temp_path)], text=True, capture_output=True, timeout=20, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            temp_path.unlink(missing_ok=True)
            raise ValueError("配置验证失败，未发现可用 remote。")
        if RCLONE_CONFIG.exists():
            backup = RCLONE_CONFIG.with_name(f"rclone.conf.backup-{datetime.now():%Y%m%d-%H%M%S}")
            shutil.copy2(RCLONE_CONFIG, backup)
            os.chmod(backup, 0o600)
        os.replace(temp_path, RCLONE_CONFIG)
        os.chmod(RCLONE_CONFIG, 0o600)
        flash("rclone.conf 已验证并上传。")
    except (ValueError, subprocess.TimeoutExpired, OSError) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/save-task", methods=["POST"])
def save_task():
    try:
        require_csrf()
        task_id = request.form.get("task_id", "")
        remote = request.form.get("remote", "")
        if remote not in rclone_remotes():
            raise ValueError("请选择有效 remote。")
        mode = request.form.get("mode", "copy")
        if mode not in {"copy", "sync"}:
            raise ValueError("同步模式无效。")
        if mode == "sync" and request.form.get("confirm_mirror") != "on":
            raise ValueError("镜像同步会删除本任务目录内的多余文件，必须勾选确认。")
        with settings_lock:
            task = task_by_id(task_id)
            task.update(
                {
                    "name": request.form.get("name", task_id).strip() or task_id,
                    "remote": remote,
                    "remote_path": clean_remote_path(request.form.get("remote_path", "")),
                    "local_path": validate_local_path(request.form.get("local_path", "")),
                    "interval_minutes": max(1, min(1440, int(request.form.get("interval_minutes", "10")))),
                    "transfers": max(1, min(16, int(request.form.get("transfers", "4")))),
                    "checkers": max(1, min(32, int(request.form.get("checkers", "8")))),
                    "mode": mode,
                    "metadata_only": request.form.get("metadata_only") == "on",
                    "enabled": request.form.get("enabled") == "on",
                    "confirm_mirror": mode == "sync" and request.form.get("confirm_mirror") == "on",
                }
            )
            write_json(SETTINGS_FILE, settings)
        flash("任务已保存。")
    except (ValueError, OSError) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


def build_command(task: dict) -> list[str]:
    remote = task.get("remote", "")
    if remote not in rclone_remotes():
        raise ValueError("rclone.conf 中找不到已选择的 remote。")
    source = f"{remote}:{clean_remote_path(task.get('remote_path', ''))}"
    destination = validate_local_path(task.get("local_path", ""))
    command = [
        "rclone", task.get("mode", "copy"), source, destination,
        "--config", str(RCLONE_CONFIG),
        "--transfers", str(task.get("transfers", 4)),
        "--checkers", str(task.get("checkers", 8)),
        "--create-empty-src-dirs",
        "--stats", "30s",
        "--log-file", str(LOG_FILE),
        "--log-level", "INFO",
        "--retries", "3",
        "--low-level-retries", "10",
    ]
    if task.get("mode") == "sync":
        command.extend(["--delete-after", "--max-delete", "10000"])
    if task.get("metadata_only"):
        for extension in METADATA_EXTENSIONS:
            command.extend(["--include", f"*.{extension}"])
        command.extend(["--exclude", "*"])
    return command


def monitor_process(task_id: str, process: subprocess.Popen) -> None:
    exit_code = process.wait()
    with state_lock:
        item = task_state(task_id)
        item.update({"running": False, "pid": None, "last_finished": datetime.now().isoformat(timespec="seconds"), "last_exit_code": exit_code, "last_message": "同步完成" if exit_code == 0 else "同步失败，请查看日志"})
        write_json(STATE_FILE, state)
    running_processes.pop(task_id, None)
    append_log_event(f"[{task_id}] 同步任务结束，退出码={exit_code}")


def launch_sync(task_id: str) -> None:
    with settings_lock:
        task = task_by_id(task_id).copy()
    process = running_processes.get(task_id)
    if process is not None and process.poll() is None:
        raise ValueError("该任务已经在运行。")
    command = build_command(task)
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    running_processes[task_id] = process
    mode_name = "镜像同步" if task.get("mode") == "sync" else "增量复制"
    with state_lock:
        item = task_state(task_id)
        item.update({"running": True, "pid": process.pid, "last_started": datetime.now().isoformat(timespec="seconds"), "last_exit_code": None, "last_message": f"正在执行{mode_name}"})
        write_json(STATE_FILE, state)
    append_log_event(f"[{task_id}] 同步任务开始，PID={process.pid}，模式={mode_name}，来源={task.get('remote')}:{task.get('remote_path')}，目标={task.get('local_path')}")
    threading.Thread(target=monitor_process, args=(task_id, process), daemon=True).start()


@app.route("/start", methods=["POST"])
def start_sync():
    try:
        require_csrf()
        launch_sync(request.form.get("task_id", ""))
        flash("同步任务已启动。")
    except (ValueError, OSError) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/stop", methods=["POST"])
def stop_sync():
    try:
        require_csrf()
        task_id = request.form.get("task_id", "")
        process = running_processes.get(task_id)
        if process is None or process.poll() is not None:
            raise ValueError("该任务当前没有运行。")
        os.killpg(process.pid, signal.SIGTERM)
        append_log_event(f"[{task_id}] 用户请求停止同步任务，PID={process.pid}")
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
    return page("账号设置", """
      <div class="card" style="max-width:560px;margin:auto">
        <h1>修改控制台账号</h1>
        <form method="post">
          <input type="hidden" name="csrf" value="{{ csrf }}">
          <label>新账号</label><input name="username" value="{{ settings.username }}" required>
          <label>原密码</label><input name="old_password" type="password" required>
          <label>新密码，至少 8 位</label><input name="new_password" type="password" required>
          <p><button class="btn" type="submit">保存并重新登录</button></p>
        </form>
      </div>
    """, settings=settings, csrf=csrf_token())


def scheduler_loop() -> None:
    next_runs: dict[str, float] = {}
    while not stop_event.wait(10):
        with settings_lock:
            tasks = [task.copy() for task in settings.get("tasks", [])]
        now = time.monotonic()
        for task in tasks:
            task_id = task["id"]
            if not task.get("enabled"):
                next_runs[task_id] = now + 30
                continue
            if now < next_runs.get(task_id, now):
                continue
            try:
                launch_sync(task_id)
            except (ValueError, OSError) as error:
                with state_lock:
                    item = task_state(task_id)
                    item["last_message"] = f"定时启动失败：{error}"
                    write_json(STATE_FILE, state)
            next_runs[task_id] = now + max(1, int(task.get("interval_minutes", 10))) * 60


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
        for process in list(running_processes.values()):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)


if __name__ == "__main__":
    main()
