#!/usr/bin/env python3
"""Authenticated control panel for the Emby helper stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import subprocess
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


APP_ROOT = Path("/root/docker-compose/stack-control")
SETTINGS_FILE = APP_ROOT / "settings.json"
CREDS_FILE = APP_ROOT / "credentials.txt"
FIXER_SETTINGS = APP_ROOT / "fixer-settings.json"
FIXER_ROOTS = Path("/root/docker-compose/emby-tools/strm-fixer-roots.json")
EMBY_DB = Path("/root/docker-compose/emby/config/data/library.db")
PREWARM_DROPIN = Path("/etc/systemd/system/emby-play-prewarm.service.d/override.conf")
DOMAIN = "https://hdz.180o.222321.xyz"

SYSTEMD_UNITS = {
    "emby-play-prewarm.service": {"label": "Emby 播放预热", "log": "emby-play-prewarm.service", "actions": ("start", "stop", "restart")},
    "emby-fix-strm-images.timer": {"label": "STRM 图片补齐监控", "log": "emby-fix-strm-images.service", "actions": ("start", "stop", "restart"), "run_unit": "emby-fix-strm-images.service"},
    "emby-fix-strm-titles.timer": {"label": "STRM 中文标题监控", "log": "emby-fix-strm-titles.service", "actions": ("start", "stop", "restart"), "run_unit": "emby-fix-strm-titles.service"},
    "rclone-sync-web.service": {"label": "Rclone 同步控制台", "log": "rclone-sync-web.service", "actions": ("start", "stop", "restart")},
    "embystream.service": {"label": "EmbyStream 备用线路", "log": "embystream.service", "actions": ("start", "stop", "restart")},
}
DOCKER_CONTAINERS = {"emby": "Emby", "cd2": "CloudDrive2", "symedia": "Symedia", "autofilm": "AutoFilm"}
PREWARM_DEFAULTS = {"EMBY_PREWARM_HEAD_BYTES": 33554432, "EMBY_PREWARM_TAIL_BYTES": 4194304, "EMBY_PREWARM_MAX_WORKERS": 2}
FIXER_DEFAULTS = {"image_interval_minutes": 30, "title_interval_minutes": 15, "image_roots": [], "title_roots": []}


def run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def read_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default.copy()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default.copy()


def write_json(path: Path, value: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".new")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def parse_kv_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()
    except OSError:
        pass
    return data


def initial_settings() -> dict:
    user = os.environ.get("STACK_CONTROL_INITIAL_USER", "admin").strip() or "admin"
    password = os.environ.get("STACK_CONTROL_INITIAL_PASSWORD", "") or secrets.token_urlsafe(18)
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(f"URL: {DOMAIN}/control/\nUsername: {user}\nPassword: {password}\n", encoding="utf-8")
    os.chmod(CREDS_FILE, 0o600)
    return {"secret_key": secrets.token_hex(32), "username": user, "password_hash": generate_password_hash(password)}


def initialize() -> None:
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        write_json(SETTINGS_FILE, initial_settings())


initialize()
settings = read_json(SETTINGS_FILE, {"secret_key": secrets.token_hex(32), "username": "admin", "password_hash": ""})

app = Flask(__name__)
app.secret_key = settings["secret_key"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

BASE = """
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · Emby Stack Control</title>
<style>
:root{color-scheme:dark;--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--blue:#2f81f7;--green:#2ea043;--red:#da3633;--yellow:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{height:56px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:#010409}
header a{color:var(--text);text-decoration:none;margin-left:14px}.wrap{max-width:1380px;margin:22px auto;padding:0 18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}.wide{grid-column:1/-1}h1,h2,h3{margin:0 0 12px}h1{font-size:20px}h2{font-size:17px}h3{font-size:15px}
table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
.pill{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;font-size:12px}.on{background:#143d2a;color:#7ee787}.off{background:#3d1f1c;color:#ff938a}.unknown{background:#3b3219;color:#e3b341}
button,.btn{border:0;border-radius:6px;padding:7px 10px;margin:2px;background:var(--blue);color:white;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}.danger{background:var(--red)}.okbtn{background:var(--green)}.warn{background:var(--yellow);color:#111}
input{padding:8px;background:#0d1117;color:var(--text);border:1px solid var(--line);border-radius:6px}input[type=number]{width:92px}.row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.muted{color:var(--muted)}.flash{background:#1f2a44;border:1px solid #315a9d;border-radius:8px;padding:10px;margin-bottom:12px}
pre{white-space:pre-wrap;background:#010409;border:1px solid var(--line);border-radius:8px;padding:12px;max-height:52vh;overflow:auto;font:12px/1.55 Consolas,monospace}.secret{font-family:Consolas,monospace;word-break:break-all}.checks{columns:2;column-gap:24px}.checks label{display:block;margin:6px 0;break-inside:avoid}
@media(max-width:760px){.row{grid-template-columns:1fr}.checks{columns:1}table{font-size:12px}th,td{padding:8px 5px}}
</style></head><body>
<header><strong>Emby Stack Control</strong>{% if session.get("user") %}<nav><a href="{{ url_for('dashboard') }}">控制台</a><a href="{{ url_for('account') }}">账号</a><a href="{{ url_for('logout') }}">退出</a></nav>{% endif %}</header>
<main class="wrap">{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}{{ body|safe }}</main>
</body></html>
"""


def page(title: str, body: str, **context):
    return render_template_string(BASE, title=title, body=render_template_string(body, **context))


def csrf_token() -> str:
    session.setdefault("csrf", secrets.token_urlsafe(24))
    return session["csrf"]


def require_csrf() -> None:
    if not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "")):
        raise ValueError("页面令牌失效，请刷新后重试。")


@app.before_request
def auth_gate():
    if request.endpoint in {"login", "healthz"}:
        return None
    if session.get("user") != settings.get("username"):
        return redirect(url_for("login"))
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
    return page("登录", """<div class="card" style="max-width:420px;margin:80px auto"><h1>登录控制台</h1><form method="post"><p><input name="username" placeholder="账号" autocomplete="username" required style="width:100%"></p><p><input name="password" type="password" placeholder="密码" autocomplete="current-password" required style="width:100%"></p><button type="submit">登录</button></form></div>""")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def unit_exists(unit: str) -> bool:
    result = run(["systemctl", "list-unit-files", unit, "--no-legend"])
    return result.returncode == 0 and unit in result.stdout


def unit_status(unit: str) -> dict:
    if not unit_exists(unit):
        return {"exists": False, "active": "missing", "enabled": "missing"}
    return {"exists": True, "active": run(["systemctl", "is-active", unit]).stdout.strip() or "unknown", "enabled": run(["systemctl", "is-enabled", unit]).stdout.strip() or "unknown"}


def container_status(name: str) -> dict:
    result = run(["docker", "inspect", "-f", "{{.State.Status}}|{{.State.Running}}|{{.RestartCount}}", name])
    if result.returncode != 0:
        return {"exists": False, "status": "missing", "running": False, "restarts": "-"}
    status, running, restarts = (result.stdout.strip().split("|") + ["", "", ""])[:3]
    return {"exists": True, "status": status, "running": running == "true", "restarts": restarts}


def timer_interval(unit: str, default_minutes: int) -> int:
    text = run(["systemctl", "cat", unit]).stdout
    match = re.search(r"OnUnitActiveSec=(\d+)\s*min", text)
    if match:
        return int(match.group(1))
    match = re.search(r"OnUnitActiveSec=(\d+)", text)
    return max(1, int(match.group(1)) // 60) if match else default_minutes


def set_timer(unit: str, service: str, boot: str, minutes: int) -> None:
    Path(f"/etc/systemd/system/{unit}").write_text(
        "[Unit]\nDescription=Managed by Emby Stack Control\n\n"
        "[Timer]\n"
        f"OnBootSec={boot}\nOnUnitActiveSec={minutes}min\nPersistent=true\nUnit={service}\n\n"
        "[Install]\nWantedBy=timers.target\n",
        encoding="utf-8",
    )


def read_prewarm_env() -> dict[str, int]:
    values = PREWARM_DEFAULTS.copy()
    text = run(["systemctl", "show", "emby-play-prewarm.service", "-p", "Environment", "--value"]).stdout
    if PREWARM_DROPIN.exists():
        text += "\n" + PREWARM_DROPIN.read_text(encoding="utf-8", errors="ignore")
    for key in values:
        match = re.search(rf"{key}=([0-9]+)", text)
        if match:
            values[key] = int(match.group(1))
    return values


def discover_libraries() -> list[str]:
    roots: set[str] = set()
    if EMBY_DB.exists():
        con = sqlite3.connect(f"file:{EMBY_DB}?mode=ro", uri=True)
        try:
            for (path,) in con.execute("select Path from MediaItems where Path like '/home/%' limit 200000"):
                if not path:
                    continue
                parts = Path(path).parts
                if len(parts) >= 4 and parts[1] == "home":
                    roots.add(str(Path(*parts[:4])))
        finally:
            con.close()
    saved = read_json(FIXER_ROOTS, {})
    roots.update(p for p in saved.get("image_roots", []) if isinstance(p, str))
    roots.update(p for p in saved.get("title_roots", []) if isinstance(p, str))
    return sorted(p for p in roots if p.startswith("/home/"))


def fixer_settings(libs: list[str]) -> dict:
    data = read_json(FIXER_SETTINGS, FIXER_DEFAULTS)
    data["image_interval_minutes"] = timer_interval("emby-fix-strm-images.timer", int(data.get("image_interval_minutes") or 30))
    data["title_interval_minutes"] = timer_interval("emby-fix-strm-titles.timer", int(data.get("title_interval_minutes") or 15))
    data["image_roots"] = [p for p in data.get("image_roots", []) if p in libs] or [p for p in libs if "movies" in p]
    data["title_roots"] = [p for p in data.get("title_roots", []) if p in libs] or [p for p in libs if "movies" in p]
    return data


def web_apps() -> list[dict[str, str]]:
    stack = parse_kv_file(CREDS_FILE)
    rclone_settings = read_json(Path("/root/docker-compose/rclone-sync/settings.json"), {})
    rclone_creds = parse_kv_file(Path("/root/docker-compose/rclone-sync/credentials.txt"))
    return [
        {"name": "Emby", "url": f"{DOMAIN}/", "user": "Emby 内账号", "password": "不在控制台保存"},
        {"name": "CloudDrive2", "url": f"{DOMAIN}/cd2/", "user": "CD2 内账号", "password": "服务端哈希保存，不能反查"},
        {"name": "Symedia", "url": f"{DOMAIN}/symedia/", "user": "Symedia 内账号", "password": "不在控制台保存"},
        {"name": "Rclone 同步控制台", "url": f"{DOMAIN}/sync/", "user": rclone_settings.get("username", rclone_creds.get("username", "admin")), "password": rclone_creds.get("password", "已有哈希，未保存明文")},
        {"name": "Stack Control", "url": f"{DOMAIN}/control/", "user": stack.get("username", settings.get("username", "admin")), "password": stack.get("password", "见 /root/docker-compose/stack-control/credentials.txt")},
    ]


def mb(value: int) -> str:
    return f"{value // 1048576} MB"


@app.route("/")
def dashboard():
    libs = discover_libraries()
    fixers = fixer_settings(libs)
    units = [(name, meta, unit_status(name)) for name, meta in SYSTEMD_UNITS.items()]
    containers = [(name, label, container_status(name)) for name, label in DOCKER_CONTAINERS.items()]
    return page("控制台", """
<div class="grid">
  <section class="card wide"><h2>Web 入口和账号</h2><table><thead><tr><th>软件</th><th>地址</th><th>账号</th><th>密码</th></tr></thead><tbody>
  {% for item in web_apps %}<tr><td><strong>{{ item.name }}</strong></td><td><a class="btn" href="{{ item.url }}" target="_blank">打开网页</a><br><span class="muted">{{ item.url }}</span></td><td class="secret">{{ item.user }}</td><td class="secret">{{ item.password }}</td></tr>{% endfor %}
  </tbody></table></section>
  <section class="card wide"><h2>自定义服务和定时器</h2><table><thead><tr><th>功能</th><th>状态</th><th>开机</th><th>操作</th></tr></thead><tbody>
  {% for name, meta, st in units %}<tr><td><strong>{{ meta.label }}</strong><br><span class="muted">{{ name }}</span></td><td><span class="pill {{ 'on' if st.active in ['active','activating'] else 'off' if st.exists else 'unknown' }}">{{ st.active }}</span></td><td>{{ st.enabled }}</td><td>{% if st.exists %}<form method="post" action="{{ url_for('unit_action') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="unit" value="{{ name }}"><button name="action" value="start" class="okbtn">启动</button><button name="action" value="stop" class="danger">停止</button><button name="action" value="restart">重启</button>{% if meta.run_unit %}<button name="action" value="run" class="warn">运行一次</button>{% endif %}<button name="action" value="log">日志</button></form>{% endif %}</td></tr>{% endfor %}
  </tbody></table></section>
  <section class="card wide"><h2>Docker 容器</h2><table><thead><tr><th>容器</th><th>状态</th><th>重启次数</th><th>操作</th></tr></thead><tbody>
  {% for name, label, st in containers %}<tr><td><strong>{{ label }}</strong><br><span class="muted">{{ name }}</span></td><td><span class="pill {{ 'on' if st.running else 'off' if st.exists else 'unknown' }}">{{ st.status }}</span></td><td>{{ st.restarts }}</td><td>{% if st.exists %}<form method="post" action="{{ url_for('container_action') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="name" value="{{ name }}"><button name="action" value="start" class="okbtn">启动</button><button name="action" value="stop" class="danger">停止</button><button name="action" value="restart">重启</button><button name="action" value="log">日志</button></form>{% endif %}</td></tr>{% endfor %}
  </tbody></table></section>
  <section class="card wide"><h2>STRM 监控设置</h2><form method="post" action="{{ url_for('save_fixers') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
    <p class="muted">默认：图片补齐 30 分钟一次，中文标题 15 分钟一次。保存后会立刻改 systemd timer。</p>
    <div class="row"><label>图片补齐间隔 分钟<br><input name="image_interval" type="number" min="1" max="1440" value="{{ fixers.image_interval_minutes }}"></label><label>中文标题间隔 分钟<br><input name="title_interval" type="number" min="1" max="1440" value="{{ fixers.title_interval_minutes }}"></label><span></span></div>
    <h3>图片补齐要刷新哪些媒体库</h3><div class="checks">{% for lib in libs %}<label><input type="checkbox" name="image_roots" value="{{ lib }}" {% if lib in fixers.image_roots %}checked{% endif %}> {{ lib }}</label>{% endfor %}</div>
    <h3>中文标题要刷新哪些媒体库</h3><div class="checks">{% for lib in libs %}<label><input type="checkbox" name="title_roots" value="{{ lib }}" {% if lib in fixers.title_roots %}checked{% endif %}> {{ lib }}</label>{% endfor %}</div>
    {% if not libs %}<p class="muted">还没从 Emby 数据库发现 /home 下的 STRM 媒体库。</p>{% endif %}<p><button type="submit">保存 STRM 监控设置</button></p>
  </form></section>
  <section class="card"><h2>播放预热参数</h2><p class="muted">当前：头部 {{ mb(prewarm.EMBY_PREWARM_HEAD_BYTES) }}，尾部 {{ mb(prewarm.EMBY_PREWARM_TAIL_BYTES) }}，并发 {{ prewarm.EMBY_PREWARM_MAX_WORKERS }}</p><form method="post" action="{{ url_for('save_prewarm') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><div class="row"><label>头部 MB<br><input name="head_mb" type="number" min="1" max="512" value="{{ prewarm.EMBY_PREWARM_HEAD_BYTES // 1048576 }}"></label><label>尾部 MB<br><input name="tail_mb" type="number" min="0" max="128" value="{{ prewarm.EMBY_PREWARM_TAIL_BYTES // 1048576 }}"></label><label>并发<br><input name="workers" type="number" min="1" max="8" value="{{ prewarm.EMBY_PREWARM_MAX_WORKERS }}"></label></div><p><button type="submit">保存并重启预热服务</button></p></form></section>
</div>
""", units=units, containers=containers, web_apps=web_apps(), libs=libs, fixers=fixers, prewarm=read_prewarm_env(), mb=mb, csrf=csrf_token())


@app.route("/unit", methods=["POST"])
def unit_action():
    try:
        require_csrf()
        unit = request.form.get("unit", "")
        action = request.form.get("action", "")
        if unit not in SYSTEMD_UNITS:
            raise ValueError("未知服务。")
        meta = SYSTEMD_UNITS[unit]
        if action == "log":
            return show_log(meta["log"], "journal")
        target = meta.get("run_unit") if action == "run" else unit
        if action == "run":
            result = run(["systemctl", "start", target], timeout=120)
        elif action in meta["actions"]:
            result = run(["systemctl", action, target], timeout=120)
        else:
            raise ValueError("不允许的操作。")
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or "操作失败。")
        flash(f"{meta['label']} 已执行：{action}")
    except (ValueError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/container", methods=["POST"])
def container_action():
    try:
        require_csrf()
        name = request.form.get("name", "")
        action = request.form.get("action", "")
        if name not in DOCKER_CONTAINERS:
            raise ValueError("未知容器。")
        if action == "log":
            return show_log(name, "docker")
        if action not in {"start", "stop", "restart"}:
            raise ValueError("不允许的操作。")
        result = run(["docker", action, name], timeout=120)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or "操作失败。")
        flash(f"{DOCKER_CONTAINERS[name]} 已执行：{action}")
    except (ValueError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


def show_log(target: str, mode: str):
    command = ["journalctl", "-u", target, "-n", "180", "--no-pager"] if mode == "journal" else ["docker", "logs", "--tail", "180", target]
    result = run(command, timeout=30)
    text = (result.stdout + result.stderr).strip() or "没有日志。"
    return page("日志", """<div class="card wide"><h2>{{ target }}</h2><p><a class="btn" href="{{ url_for('dashboard') }}">返回</a></p><pre>{{ text }}</pre></div>""", target=target, text=text)


@app.route("/fixers", methods=["POST"])
def save_fixers():
    try:
        require_csrf()
        libs = set(discover_libraries())
        image_roots = [p for p in request.form.getlist("image_roots") if p in libs]
        title_roots = [p for p in request.form.getlist("title_roots") if p in libs]
        image_interval = max(1, min(1440, int(request.form.get("image_interval", "30"))))
        title_interval = max(1, min(1440, int(request.form.get("title_interval", "15"))))
        data = {"image_interval_minutes": image_interval, "title_interval_minutes": title_interval, "image_roots": image_roots, "title_roots": title_roots}
        write_json(FIXER_SETTINGS, data)
        write_json(FIXER_ROOTS, {"image_roots": image_roots, "title_roots": title_roots})
        set_timer("emby-fix-strm-images.timer", "emby-fix-strm-images.service", "5min", image_interval)
        set_timer("emby-fix-strm-titles.timer", "emby-fix-strm-titles.service", "10min", title_interval)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", "--now", "emby-fix-strm-images.timer"])
        run(["systemctl", "enable", "--now", "emby-fix-strm-titles.timer"])
        run(["systemctl", "restart", "emby-fix-strm-images.timer"])
        run(["systemctl", "restart", "emby-fix-strm-titles.timer"])
        flash("STRM 监控设置已保存。")
    except (ValueError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/prewarm", methods=["POST"])
def save_prewarm():
    try:
        require_csrf()
        head = max(1, min(512, int(request.form.get("head_mb", "32")))) * 1048576
        tail = max(0, min(128, int(request.form.get("tail_mb", "4")))) * 1048576
        workers = max(1, min(8, int(request.form.get("workers", "2"))))
        PREWARM_DROPIN.parent.mkdir(parents=True, exist_ok=True)
        PREWARM_DROPIN.write_text("[Service]\n" f"Environment=EMBY_PREWARM_HEAD_BYTES={head}\n" f"Environment=EMBY_PREWARM_TAIL_BYTES={tail}\n" f"Environment=EMBY_PREWARM_MAX_WORKERS={workers}\n", encoding="utf-8")
        run(["systemctl", "daemon-reload"])
        result = run(["systemctl", "restart", "emby-play-prewarm.service"], timeout=120)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "重启预热服务失败。")
        flash("播放预热参数已保存。")
    except (ValueError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        try:
            require_csrf()
            old = request.form.get("old_password", "")
            username = request.form.get("username", "").strip()
            new = request.form.get("new_password", "")
            if not check_password_hash(settings["password_hash"], old):
                raise ValueError("原密码错误。")
            if len(username) < 3 or len(new) < 8:
                raise ValueError("账号至少 3 位，新密码至少 8 位。")
            settings["username"] = username
            settings["password_hash"] = generate_password_hash(new)
            write_json(SETTINGS_FILE, settings)
            CREDS_FILE.write_text(f"URL: {DOMAIN}/control/\nUsername: {username}\nPassword: {new}\n", encoding="utf-8")
            os.chmod(CREDS_FILE, 0o600)
            session.clear()
            flash("账号密码已修改，请重新登录。")
            return redirect(url_for("login"))
        except ValueError as error:
            flash(str(error))
    return page("账号", """<div class="card" style="max-width:520px;margin:auto"><h1>修改账号密码</h1><form method="post"><input type="hidden" name="csrf" value="{{ csrf }}"><p><input name="username" value="{{ username }}" required style="width:100%"></p><p><input name="old_password" type="password" placeholder="原密码" required style="width:100%"></p><p><input name="new_password" type="password" placeholder="新密码，至少 8 位" required style="width:100%"></p><button type="submit">保存</button></form></div>""", username=settings["username"], csrf=csrf_token())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=6011, type=int)
    args = parser.parse_args()
    if not args.init:
        app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
