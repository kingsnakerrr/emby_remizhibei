#!/usr/bin/env python3
"""Authenticated control panel for the Emby helper stack."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import shlex
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
RCLONE_CONFIG = Path("/root/.config/rclone/rclone.conf")
RCLONE_SYNC_SETTINGS = Path("/root/docker-compose/rclone-sync/settings.json")
RCLONE_SYNC_STATE = Path("/root/docker-compose/rclone-sync/state.json")
PREWARM_DROPIN = Path("/etc/systemd/system/emby-play-prewarm.service.d/override.conf")
DOMAIN = "https://hdz.180o.222321.xyz"
URLS = {
    "emby": f"{DOMAIN}/",
    "control": f"{DOMAIN}:8443/",
    "sync": f"{DOMAIN}:9443/",
    "cd2": f"{DOMAIN}:10443/",
    "symedia": f"{DOMAIN}:11443/",
}

SYSTEMD_UNITS = {
    "emby-play-prewarm.service": {"label": "Emby 播放预热", "log": "emby-play-prewarm.service", "actions": ("start", "stop", "restart")},
    "emby-fix-strm-images.timer": {"label": "STRM 图片和元素补齐监控", "log": "emby-fix-strm-images.service", "actions": ("start", "stop", "restart"), "run_unit": "emby-fix-strm-images.service"},
    "emby-fix-strm-titles.timer": {"label": "STRM 中文标题、简介等修正监控", "log": "emby-fix-strm-titles.service", "actions": ("start", "stop", "restart"), "run_unit": "emby-fix-strm-titles.service"},
    "rclone-sync-web.service": {"label": "Rclone 同步控制台", "log": "rclone-sync-web.service", "actions": ("start", "stop", "restart")},
    "embystream.service": {"label": "EmbyStream 备用线路", "log": "embystream.service", "actions": ("start", "stop", "restart")},
}
RCLONE_SYNC_DEFAULT_TASKS = [
    {"id": "symedia_gd", "name": "symedia_gd", "remote": "snakegd_kingsnakerrr", "remote_path": "media/symedia_gd", "local_path": "/home/symedia_gd", "interval_minutes": 10, "enabled": False, "mode": "copy", "metadata_only": False, "confirm_mirror": False, "transfers": 16, "checkers": 16},
    {"id": "symedia_jav", "name": "symedia_jav", "remote": "snakegd_kingsnakerrr", "remote_path": "media/symedia_jav", "local_path": "/home/symedia_jav", "interval_minutes": 10, "enabled": False, "mode": "copy", "metadata_only": False, "confirm_mirror": False, "transfers": 16, "checkers": 16},
]
RCLONE_MOUNT_DEFAULTS = {
    "dir-cache-time": "72h",
    "poll-interval": "15s",
    "vfs-cache-mode": "full",
    "vfs-cache-max-size": "600G",
    "vfs-cache-max-age": "72h",
    "vfs-cache-poll-interval": "1m",
    "vfs-read-chunk-size": "64M",
    "vfs-read-chunk-size-limit": "2G",
    "buffer-size": "128M",
    "drive-chunk-size": "256M",
    "transfers": "8",
    "checkers": "16",
}
RCLONE_MOUNT_HELP = {
    "dir-cache-time": "目录列表缓存时间，越长越少请求网盘目录。",
    "poll-interval": "轮询远端变化间隔，短一点目录变化发现更快。",
    "vfs-cache-mode": "full 会缓存读过的数据，适合媒体播放拖动。",
    "vfs-cache-max-size": "单个挂载允许占用的最大本地缓存空间。",
    "vfs-cache-max-age": "缓存文件多久没用后过期清理。",
    "vfs-cache-poll-interval": "检查缓存是否需要清理的间隔。",
    "vfs-read-chunk-size": "开始读取的分块大小，影响起播和顺序读取。",
    "vfs-read-chunk-size-limit": "分块自动增大上限，影响大文件连续播放。",
    "buffer-size": "每个打开文件的内存缓冲。",
    "drive-chunk-size": "Google Drive 传输块大小。",
    "transfers": "并行传输数量，播放挂载一般不用太高。",
    "checkers": "并行检查数量，影响扫描目录速度。",
}
DOCKER_CONTAINERS = {"emby": "Emby", "cd2": "CloudDrive2", "symedia": "Symedia", "autofilm": "AutoFilm"}
PREWARM_DEFAULTS = {
    "EMBY_PREWARM_HEAD_BYTES": 33554432,
    "EMBY_PREWARM_TAIL_BYTES": 4194304,
    "EMBY_PREWARM_RESUME_BYTES": 67108864,
    "EMBY_PREWARM_MAX_WORKERS": 2,
}
FIXER_DEFAULTS = {"image_interval_minutes": 30, "title_interval_minutes": 15, "image_enabled": True, "title_enabled": True, "image_roots": None, "title_roots": None}
CONFIG_EDITORS = {
    "embystream_env": {"label": "EmbyStream 私有变量", "path": Path("/root/docker-compose/embystream/.env.private"), "restart": "unit", "target": "embystream.service"},
    "embystream_toml": {"label": "EmbyStream TOML 配置", "path": Path("/root/docker-compose/embystream/config/config.toml"), "restart": "unit", "target": "embystream.service"},
    "autofilm_yaml": {"label": "AutoFilm 主配置", "path": Path("/root/docker-compose/autofilm/config/config.yaml"), "restart": "container", "target": "autofilm"},
    "autofilm_compose": {"label": "AutoFilm Compose", "path": Path("/root/docker-compose/autofilm/compose.yaml"), "restart": "compose", "target": "/root/docker-compose/autofilm"},
}


def run(command: list[str], timeout: int = 30, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False, cwd=cwd)


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
    CREDS_FILE.write_text(f"URL: {URLS['control']}\nUsername: {user}\nPassword: {password}\n", encoding="utf-8")
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
.split{display:grid;grid-template-columns:minmax(0,2fr) minmax(320px,1fr);gap:14px}.taskbox{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}.taskbox:first-child{border-top:0;margin-top:0;padding-top:0}.inline{display:inline}.field{width:100%}.tiny{width:82px!important}
.subgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}.subcard{background:#0f141b;border:1px solid var(--line);border-radius:8px;padding:14px}.subcard .checks{columns:1}.statusline{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:4px 0 12px}.compact-form{display:flex;align-items:end;gap:14px;flex-wrap:wrap}.compact-form label{min-width:92px}.compact-form p{margin:0}.editor{width:100%;min-height:260px;background:#010409;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px;font:12px/1.45 Consolas,monospace}.help-list{margin:8px 0 14px;padding-left:18px}.help-list li{margin:4px 0}
@media(max-width:760px){.row{grid-template-columns:1fr}.checks{columns:1}table{font-size:12px}th,td{padding:8px 5px}}
@media(max-width:980px){.split{grid-template-columns:1fr}}
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
        username = request.form.get("stack_control_user", "")
        password = request.form.get("stack_control_pass", "")
        if secrets.compare_digest(username, settings.get("username", "")) and check_password_hash(settings.get("password_hash", ""), password):
            session.clear()
            session["user"] = username
            csrf_token()
            return redirect(url_for("dashboard"))
        flash("账号或密码错误。")
    return page("登录", """<div class="card" style="max-width:420px;margin:80px auto"><h1>登录控制台</h1><form method="post" autocomplete="off"><p><input name="stack_control_user" placeholder="账号" autocomplete="section-stack-control username" required style="width:100%"></p><p><input name="stack_control_pass" type="password" placeholder="密码" autocomplete="section-stack-control current-password" required style="width:100%"></p><button type="submit">登录</button></form></div>""")


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


def rclone_mount_units() -> list[tuple[str, dict, dict]]:
    result = run(["systemctl", "list-unit-files", "rclone-*.service", "--no-legend"])
    names: list[str] = []
    for line in result.stdout.splitlines():
        name = line.split()[0] if line.split() else ""
        if name.startswith("rclone-") and name.endswith(".service") and name != "rclone-sync-web.service":
            names.append(name)
    units = []
    for name in sorted(set(names)):
        label = name.removeprefix("rclone-").removesuffix(".service")
        units.append((name, {"label": f"Rclone {label} 挂载", "log": name, "actions": ("start", "stop", "restart")}, unit_status(name)))
    return units


def rclone_mount_config(unit: str) -> dict:
    text = run(["systemctl", "cat", unit]).stdout
    lines = text.splitlines()
    command = ""
    for index, line in enumerate(lines):
        if not line.startswith("ExecStart="):
            continue
        parts = [line.removeprefix("ExecStart=")]
        cursor = index + 1
        while parts[-1].rstrip().endswith("\\") and cursor < len(lines):
            parts[-1] = parts[-1].rstrip()[:-1]
            parts.append(lines[cursor].strip())
            cursor += 1
        command = " ".join(parts)
        break
    remote = ""
    mount_path = ""
    options = RCLONE_MOUNT_DEFAULTS.copy()
    try:
        args = shlex.split(command)
    except ValueError:
        args = []
    if len(args) >= 4 and args[1] == "mount":
        remote = args[2].rstrip(":")
        mount_path = args[3]
    index = 4
    while index < len(args):
        token = args[index]
        if not token.startswith("--"):
            index += 1
            continue
        key_value = token[2:]
        if "=" in key_value:
            key, value = key_value.split("=", 1)
        elif index + 1 < len(args) and not args[index + 1].startswith("--"):
            key, value = key_value, args[index + 1]
            index += 1
        else:
            key, value = key_value, "on"
        if key in options:
            options[key] = value
        index += 1
    return {"remote": remote, "mount_path": mount_path, "options": options}


def write_rclone_mount_service(unit: str, remote: str, mount_path: str, options: dict[str, str]) -> None:
    if not (unit.startswith("rclone-") and unit.endswith(".service") and unit != "rclone-sync-web.service"):
        raise ValueError("不是允许管理的 rclone 挂载服务。")
    if remote not in rclone_remotes():
        raise ValueError("rclone.conf 里没有这个 remote。")
    path = Path(mount_path.strip())
    if not path.is_absolute() or not str(path).startswith("/home/"):
        raise ValueError("挂载目录必须是 /home 下的绝对路径。")
    path.mkdir(parents=True, exist_ok=True)
    name = unit.removeprefix("rclone-").removesuffix(".service")
    merged = RCLONE_MOUNT_DEFAULTS.copy()
    for key, value in options.items():
        if key in merged and str(value).strip():
            merged[key] = str(value).strip()
    rc_port = "5573" if name == "zero" else "5574" if name == "h2" else "5575"
    lines = [
        "[Unit]",
        f"Description=Rclone mount Google Drive {remote} root",
        "Wants=network-online.target",
        "After=network-online.target",
        f"AssertPathIsDirectory={path}",
        "",
        "[Service]",
        "Type=simple",
        "User=root",
        "Group=root",
        f"ExecStart=/usr/bin/rclone mount {shlex.quote(remote + ':')} {shlex.quote(str(path))} \\",
        "  --config=/root/.config/rclone/rclone.conf \\",
        "  --allow-other \\",
        "  --read-only \\",
    ]
    for key in RCLONE_MOUNT_DEFAULTS:
        lines.append(f"  --{key}={merged[key]} \\")
    lines += [
        "  --umask=002 \\",
        f"  --cache-dir=/var/cache/rclone/{name} \\",
        "  --log-level=INFO \\",
        f"  --log-file=/var/log/rclone/{name}.log \\",
        "  --rc \\",
        f"  --rc-addr=127.0.0.1:{rc_port} \\",
        "  --rc-no-auth",
        f"ExecStop=/bin/fusermount3 -uz {path}",
        "Restart=on-failure",
        "RestartSec=10",
        "TimeoutStopSec=30",
        "KillMode=process",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ]
    Path(f"/etc/systemd/system/{unit}").write_text("\n".join(lines), encoding="utf-8")


def rclone_remotes() -> list[str]:
    if not RCLONE_CONFIG.exists():
        return []
    result = run(["rclone", "listremotes", "--config", str(RCLONE_CONFIG)], timeout=20)
    if result.returncode != 0:
        return []
    return [line.rstrip(":") for line in result.stdout.splitlines() if line.strip()]


def sanitize_task_id(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-_")
    return text or secrets.token_hex(4)


def sync_settings() -> dict:
    data = read_json(RCLONE_SYNC_SETTINGS, {})
    data.setdefault("tasks", [])
    if not data["tasks"]:
        data["tasks"] = [task.copy() for task in RCLONE_SYNC_DEFAULT_TASKS]
    return data


def save_sync_settings(data: dict) -> None:
    write_json(RCLONE_SYNC_SETTINGS, data)
    if unit_exists("rclone-sync-web.service"):
        run(["systemctl", "restart", "rclone-sync-web.service"], timeout=120)


def sync_tasks() -> list[dict]:
    data = sync_settings()
    tasks = []
    for raw in data.get("tasks", []):
        if not isinstance(raw, dict):
            continue
        task = RCLONE_SYNC_DEFAULT_TASKS[0].copy()
        task.update(raw)
        task["id"] = sanitize_task_id(str(task.get("id") or task.get("name") or "task"))
        tasks.append(task)
    return tasks


def sync_task_unit(task_id: str) -> str:
    return f"stack-rclone-sync-{sanitize_task_id(task_id)}.service"


def sync_task_states() -> dict:
    data = read_json(RCLONE_SYNC_STATE, {})
    raw_tasks = data.get("tasks", {})
    return raw_tasks if isinstance(raw_tasks, dict) else {}


def sync_task_runtime(task: dict, saved_states: dict | None = None) -> dict:
    unit = sync_task_unit(str(task.get("id", task.get("name", "task"))))
    active = run(["systemctl", "is-active", unit]).stdout.strip() or "inactive"
    state = (saved_states or {}).get(task.get("id"), {})
    running = active in {"active", "activating"}
    status = "同步中" if running else "空闲"
    return {
        "unit": unit,
        "active": active,
        "running": running,
        "status": status,
        "pid": state.get("pid", "无"),
        "started": state.get("last_started", "无"),
        "finished": state.get("last_finished", "无"),
        "exit_code": state.get("last_exit_code", "无"),
        "message": state.get("last_message", "尚未运行"),
    }


def rclone_sync_command(task: dict) -> list[str]:
    mode = task.get("mode", "copy")
    if mode not in {"copy", "sync"}:
        raise ValueError("同步模式无效。")
    if mode == "sync" and not task.get("confirm_mirror"):
        raise ValueError("镜像同步必须勾选确认删除。")
    remote = str(task.get("remote", "")).strip()
    if not remote:
        raise ValueError("Remote 不能为空。")
    source = f"{remote}:{clean_remote_path(str(task.get('remote_path', '')))}"
    target = clean_local_path(str(task.get("local_path", "")))
    command = [
        "rclone",
        mode,
        source,
        target,
        "--config",
        str(RCLONE_CONFIG),
        "--create-empty-src-dirs",
        "--stats",
        "30s",
        "--log-level",
        "INFO",
        "--retries",
        "3",
        "--low-level-retries",
        "10",
        "--transfers",
        str(max(1, min(32, int(task.get("transfers", 16))))),
        "--checkers",
        str(max(1, min(64, int(task.get("checkers", 16))))),
    ]
    if mode == "sync":
        command.extend(["--delete-after", "--max-delete", "10000"])
    if task.get("metadata_only"):
        for pattern in ["*.strm", "*.nfo", "*.jpg", "*.jpeg", "*.png", "*.svg", "*.ass", "*.srt", "*.sup"]:
            command.extend(["--include", pattern])
        command.extend(["--exclude", "*"])
    return command


def start_sync_task_once(task: dict) -> None:
    unit = sync_task_unit(str(task["id"]))
    command = rclone_sync_command(task)
    result = run(
        [
            "systemd-run",
            "--collect",
            "--unit",
            unit.removesuffix(".service"),
            "--description",
            f"Stack Control rclone sync {task.get('name', task['id'])}",
            "--property",
            "WorkingDirectory=/root",
            "--property",
            "StandardOutput=journal",
            "--property",
            "StandardError=journal",
            *command,
        ],
        timeout=120,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "启动同步任务失败。")


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
    data["image_enabled"] = bool(data.get("image_enabled", True))
    data["title_enabled"] = bool(data.get("title_enabled", True))
    image_roots = data.get("image_roots")
    title_roots = data.get("title_roots")
    data["image_roots"] = [p for p in image_roots if p in libs] if isinstance(image_roots, list) else [p for p in libs if "movies" in p]
    data["title_roots"] = [p for p in title_roots if p in libs] if isinstance(title_roots, list) else [p for p in libs if "movies" in p]
    return data


def fixer_runtime(*services: str) -> dict[str, str]:
    states = [unit_status(service).get("active", "unknown") for service in services]
    if any(active in {"active", "activating"} for active in states):
        return {"state": "运行中", "class": "on", "active": ",".join(states)}
    if all(active in {"inactive", "deactivating", "not-found"} for active in states):
        return {"state": "空闲", "class": "unknown", "active": ",".join(states)}
    return {"state": ",".join(states), "class": "off", "active": ",".join(states)}


def web_apps() -> list[dict[str, str]]:
    stack = parse_kv_file(CREDS_FILE)
    rclone_settings = read_json(Path("/root/docker-compose/rclone-sync/settings.json"), {})
    rclone_creds = parse_kv_file(Path("/root/docker-compose/rclone-sync/credentials.txt"))
    return [
        {"name": "Emby", "url": URLS["emby"], "user": "Emby 内账号", "password": "不在控制台保存"},
        {"name": "CloudDrive2", "url": URLS["cd2"], "user": "CD2 内账号", "password": "服务端哈希保存，不能反查"},
        {"name": "Symedia", "url": URLS["symedia"], "user": "Symedia 内账号", "password": "不在控制台保存"},
        {"name": "Rclone 同步控制台", "url": URLS["sync"], "user": rclone_settings.get("username", rclone_creds.get("username", "admin")), "password": rclone_creds.get("password", "已有哈希，未保存明文")},
        {"name": "Stack Control", "url": URLS["control"], "user": stack.get("username", settings.get("username", "admin")), "password": stack.get("password", "见 /root/docker-compose/stack-control/credentials.txt")},
    ]


def editable_config(key: str) -> dict:
    item = CONFIG_EDITORS[key].copy()
    path = item["path"]
    try:
        item["content"] = path.read_text(encoding="utf-8", errors="replace")
        item["exists"] = True
    except OSError:
        item["content"] = ""
        item["exists"] = False
    return item


def restart_after_config_save(item: dict) -> None:
    mode = item["restart"]
    if mode == "unit":
        result = run(["systemctl", "restart", item["target"]], timeout=120)
    elif mode == "container":
        result = run(["docker", "restart", item["target"]], timeout=120)
    elif mode == "compose":
        result = run(["docker", "compose", "up", "-d"], timeout=180, cwd=str(item["target"]))
    else:
        raise ValueError("未知应用方式。")
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "应用配置失败。")


def mb(value: int) -> str:
    return f"{value // 1048576} MB"


@app.route("/")
def dashboard():
    libs = discover_libraries()
    fixers = fixer_settings(libs)
    units = [(name, meta, unit_status(name)) for name, meta in SYSTEMD_UNITS.items()]
    mount_units = rclone_mount_units()
    containers = [(name, label, container_status(name)) for name, label in DOCKER_CONTAINERS.items()]
    tasks = sync_tasks()
    task_states = sync_task_states()
    for task in tasks:
        task["runtime"] = sync_task_runtime(task, task_states)
    remotes = rclone_remotes()
    return page("控制台", """
<div class="grid">
  <section class="card wide"><h2>Web 入口和账号</h2><table><thead><tr><th>软件</th><th>地址</th><th>账号</th><th>密码</th></tr></thead><tbody>
  {% for item in web_apps %}<tr><td><strong>{{ item.name }}</strong></td><td><a class="btn" href="{{ item.url }}" target="_blank">打开网页</a><br><span class="muted">{{ item.url }}</span></td><td class="secret">{{ item.user }}</td><td class="secret">{{ item.password }}</td></tr>{% endfor %}
  </tbody></table></section>
  <section class="card wide"><h2>Rclone 本地挂载</h2>
  {% for name, meta, st in mount_units %}{% set cfg = mount_configs[name] %}
    <details class="taskbox"><summary><strong>{{ cfg.remote or meta.label }}</strong> -> <code>{{ cfg.mount_path or '未识别目录' }}</code> <span class="pill {{ 'on' if st.active in ['active','activating'] else 'off' if st.exists else 'unknown' }}">{{ st.active }}</span> <span class="muted">{{ name }} / {{ st.enabled }}</span></summary>
      <form method="post" action="{{ url_for('save_mount') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="unit" value="{{ name }}">
        <div class="row"><label>Rclone config 名称<br><select class="field" name="remote">{% for remote in remotes %}<option value="{{ remote }}" {% if remote == cfg.remote %}selected{% endif %}>{{ remote }}</option>{% endfor %}{% if cfg.remote and cfg.remote not in remotes %}<option value="{{ cfg.remote }}" selected>{{ cfg.remote }}</option>{% endif %}</select></label><label>挂载到本地目录<br><input class="field" name="mount_path" value="{{ cfg.mount_path }}"></label><span></span></div>
        <p><button type="button" class="warn" onclick="for (const [k,v] of Object.entries({{ mount_defaults_json|safe }})) { const el = this.form.elements['opt_'+k]; if (el) el.value = v; }">填入本地挂载默认值</button></p>
        <div class="subgrid">
        {% for key, value in cfg.options.items() %}
          <label>{{ key }}<br><input class="field" name="opt_{{ key }}" value="{{ value }}"><span class="muted">{{ mount_help[key] }}</span></label>
        {% endfor %}
        </div>
        <p><button type="submit">保存并重启挂载</button><button formaction="{{ url_for('unit_action') }}" name="action" value="start" class="okbtn" type="submit">启动</button><button formaction="{{ url_for('unit_action') }}" name="action" value="stop" class="danger" type="submit">停止</button><button formaction="{{ url_for('unit_action') }}" name="action" value="restart" type="submit">重启</button><button formaction="{{ url_for('unit_action') }}" name="action" value="log" type="submit">日志</button><input type="hidden" name="dynamic_rclone" value="1"></p>
      </form>
    </details>
  {% endfor %}
  {% if not mount_units %}<p class="muted">还没发现 rclone-*.service 挂载。</p>{% endif %}
  </section>
  <section class="card wide"><h2>Rclone 同步任务</h2><p class="muted">默认任务：symedia_gd 和 symedia_jav，copy 模式，10 分钟，16/16 并发。每个任务单独控制，互不影响。</p>
  <form method="post" action="{{ url_for('add_sync_task') }}" class="taskbox"><input type="hidden" name="csrf" value="{{ csrf }}"><div class="row"><label>新增任务名<br><input class="field" name="name" placeholder="例如 symedia_tv" required></label><span></span><p><button class="okbtn" type="submit">添加任务</button></p></div></form>
  {% for task in tasks %}<div class="taskbox"><h3>{{ task.name }} <span class="pill {{ 'on' if task.runtime.running else 'off' }}">{{ task.runtime.status }}</span></h3>
    <p class="muted">服务：{{ task.runtime.unit }} / systemd: {{ task.runtime.active }} / PID: {{ task.runtime.pid }} / 退出码: {{ task.runtime.exit_code }}</p>
    <p class="muted">开始：{{ task.runtime.started }} / 结束：{{ task.runtime.finished }} / {{ task.runtime.message }}</p>
    <form method="post" action="{{ url_for('save_sync_task') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="task_id" value="{{ task.id }}">
    <div class="row"><label>任务名<br><input class="field" name="name" value="{{ task.name }}" required></label><label>Remote<br><select class="field" name="remote">{% for remote in remotes %}<option value="{{ remote }}" {% if remote == task.remote %}selected{% endif %}>{{ remote }}</option>{% endfor %}{% if task.remote and task.remote not in remotes %}<option value="{{ task.remote }}" selected>{{ task.remote }}</option>{% endif %}</select></label><label>间隔分钟<br><input class="tiny" type="number" name="interval_minutes" min="1" max="1440" value="{{ task.interval_minutes }}"></label></div>
    <div class="row"><label>云端目录<br><input class="field" name="remote_path" value="{{ task.remote_path }}" required></label><label>本地目录<br><input class="field" name="local_path" value="{{ task.local_path }}" required></label><span></span></div>
    <div class="row"><label>传输并发<br><input class="tiny" type="number" name="transfers" min="1" max="32" value="{{ task.transfers }}"></label><label>检查并发<br><input class="tiny" type="number" name="checkers" min="1" max="64" value="{{ task.checkers }}"></label><label>模式<br><select class="field" name="mode"><option value="copy" {% if task.mode == 'copy' %}selected{% endif %}>copy 不删本地</option><option value="sync" {% if task.mode == 'sync' %}selected{% endif %}>sync 镜像</option></select></label></div>
    <p><label><input type="checkbox" name="enabled" {% if task.enabled %}checked{% endif %}> 启用定时同步</label> <label><input type="checkbox" name="metadata_only" {% if task.metadata_only %}checked{% endif %}> 只传 STRM/NFO/图片/字幕</label> <label><input type="checkbox" name="confirm_mirror" {% if task.confirm_mirror %}checked{% endif %}> 确认镜像删除</label></p>
    <p><button type="submit">保存</button><button formaction="{{ url_for('sync_task_action') }}" name="action" value="run" class="okbtn" type="submit">立即同步</button><button formaction="{{ url_for('sync_task_action') }}" name="action" value="stop" class="danger" type="submit">停止</button><button formaction="{{ url_for('sync_task_action') }}" name="action" value="log" type="submit">日志</button><button formaction="{{ url_for('delete_sync_task') }}" class="danger" type="submit" onclick="return confirm('删除这个同步任务？')">删除</button></p>
  </form></div>{% endfor %}
  </section>
  <section class="card wide"><h2>自定义服务和定时器</h2><table><thead><tr><th>功能</th><th>状态</th><th>开机</th><th>操作</th></tr></thead><tbody>
  {% for name, meta, st in units %}<tr><td><strong>{{ meta.label }}</strong><br><span class="muted">{{ name }}</span></td><td><span class="pill {{ 'on' if st.active in ['active','activating'] else 'off' if st.exists else 'unknown' }}">{{ st.active }}</span></td><td>{{ st.enabled }}</td><td>{% if st.exists %}<form method="post" action="{{ url_for('unit_action') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="unit" value="{{ name }}"><button name="action" value="start" class="okbtn">启动</button><button name="action" value="stop" class="danger">停止</button><button name="action" value="restart">重启</button>{% if meta.run_unit %}<button name="action" value="run" class="warn">运行一次</button>{% endif %}<button name="action" value="log">日志</button></form>{% endif %}</td></tr>
  {% if name == 'emby-play-prewarm.service' %}<tr><td colspan="4"><div class="subcard"><h3>播放预热参数</h3><p class="muted">当前：头部 {{ mb(prewarm.EMBY_PREWARM_HEAD_BYTES) }}，尾部 {{ mb(prewarm.EMBY_PREWARM_TAIL_BYTES) }}，恢复进度附近 {{ mb(prewarm.EMBY_PREWARM_RESUME_BYTES) }}，并发 {{ prewarm.EMBY_PREWARM_MAX_WORKERS }}</p><form class="compact-form" method="post" action="{{ url_for('save_prewarm') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><label>头部 MB<br><input name="head_mb" type="number" min="1" max="512" value="{{ prewarm.EMBY_PREWARM_HEAD_BYTES // 1048576 }}"></label><label>尾部 MB<br><input name="tail_mb" type="number" min="0" max="128" value="{{ prewarm.EMBY_PREWARM_TAIL_BYTES // 1048576 }}"></label><label>恢复点 MB<br><input name="resume_mb" type="number" min="0" max="512" value="{{ prewarm.EMBY_PREWARM_RESUME_BYTES // 1048576 }}"></label><label>并发<br><input name="workers" type="number" min="1" max="8" value="{{ prewarm.EMBY_PREWARM_MAX_WORKERS }}"></label><p><button type="submit">保存并重启预热服务</button></p></form></div></td></tr>{% endif %}
  {% if name == 'embystream.service' %}<tr><td colspan="4"><details class="subcard"><summary><strong>EmbyStream 使用方法和编辑配置</strong></summary><ul class="help-list muted"><li>客户端连接 EmbyStream 前端入口，走备用 Google Drive API 播放链路；原 Emby 入口仍然保留。</li><li>核心配置是 `.env.private` 的 Emby API Key、Google OAuth、团队盘 ID，以及 `config.toml` 的端口和路径匹配。</li><li>保存配置会自动备份原文件并重启 `embystream.service`。</li></ul><div class="subgrid">{% for key in ['embystream_env','embystream_toml'] %}{% set cfg = configs[key] %}<form method="post" action="{{ url_for('save_config') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="key" value="{{ key }}"><h3>{{ cfg.label }}</h3><p class="muted">{{ cfg.path }}{% if not cfg.exists %} / 当前不存在，保存会新建{% endif %}</p><textarea class="editor" name="content" spellcheck="false">{{ cfg.content }}</textarea><p><button type="submit">保存并重启 EmbyStream</button></p></form>{% endfor %}</div></details></td></tr>{% endif %}
  {% endfor %}
  </tbody></table></section>
  <section class="card wide"><h2>Docker 容器</h2><table><thead><tr><th>容器</th><th>状态</th><th>重启次数</th><th>操作</th></tr></thead><tbody>
  {% for name, label, st in containers %}<tr><td><strong>{{ label }}</strong><br><span class="muted">{{ name }}</span></td><td><span class="pill {{ 'on' if st.running else 'off' if st.exists else 'unknown' }}">{{ st.status }}</span></td><td>{{ st.restarts }}</td><td>{% if st.exists %}<form method="post" action="{{ url_for('container_action') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="name" value="{{ name }}"><button name="action" value="start" class="okbtn">启动</button><button name="action" value="stop" class="danger">停止</button><button name="action" value="restart">重启</button><button name="action" value="log">日志</button></form>{% endif %}</td></tr>
  {% if name == 'autofilm' %}<tr><td colspan="4"><details class="subcard"><summary><strong>AutoFilm 使用方法和编辑配置</strong></summary><ul class="help-list muted"><li>AutoFilm 当前主要靠 `config.yaml` 里的 cron 定时任务运行，不是独立网页面板。</li><li>`config.yaml` 配 Alist/OpenList、媒体服务器、生成 STRM、追番和海报任务；`compose.yaml` 配容器挂载路径。</li><li>保存主配置会重启 AutoFilm；保存 compose 会执行 `docker compose up -d` 重建容器。</li></ul><div class="subgrid">{% for key in ['autofilm_yaml','autofilm_compose'] %}{% set cfg = configs[key] %}<form method="post" action="{{ url_for('save_config') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="key" value="{{ key }}"><h3>{{ cfg.label }}</h3><p class="muted">{{ cfg.path }}</p><textarea class="editor" name="content" spellcheck="false">{{ cfg.content }}</textarea><p><button type="submit">保存并应用 AutoFilm</button></p></form>{% endfor %}</div></details></td></tr>{% endif %}
  {% endfor %}
  </tbody></table></section>
  <section id="strm-monitor" class="card wide"><h2>STRM 监控设置</h2>
    <p class="muted">新增媒体库会从 Emby 数据库自动出现；全部不勾选时，对应监控不会扫描任何库。</p>
    <form method="post" action="{{ url_for('save_fixers', _anchor='strm-monitor') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
      <div class="subgrid">
        <div class="subcard">
          <h3>图片和元素补齐监控</h3>
          <div class="statusline"><span>运行状态</span><span class="pill {{ image_runtime.class }}">{{ image_runtime.state }}</span><span class="muted">定时轮询=按间隔自动检查勾选媒体库，不是实时监听。</span></div>
          <p><label><input type="checkbox" name="image_enabled" {% if fixers.image_enabled %}checked{% endif %}> 启动定时轮询</label></p>
          <p><label>运行间隔 分钟<br><input name="image_interval" type="number" min="1" max="1440" value="{{ fixers.image_interval_minutes }}"></label></p>
          <h3>刷新媒体库</h3>
          <div class="checks">{% for lib in libs %}<label><input type="checkbox" name="image_roots" value="{{ lib }}" {% if lib in fixers.image_roots %}checked{% endif %}> {{ lib }}</label>{% endfor %}</div>
          <p><button formaction="{{ url_for('run_fixer_once', _anchor='strm-monitor') }}" name="kind" value="image" class="warn" type="submit">补齐缺失和未扫描</button><button formaction="{{ url_for('run_fixer_once', _anchor='strm-monitor') }}" name="kind" value="image-full" class="danger" type="submit" onclick="return confirm('只会扫描当前勾选的媒体库；全局扫描补齐会让勾选媒体库全部重新请求 Emby 刮削，确定执行？')">全局扫描补齐</button><button formaction="{{ url_for('run_fixer_once', _anchor='strm-monitor') }}" name="kind" value="image-log" type="submit">日志</button></p>
        </div>
        <div class="subcard">
          <h3>中文标题、简介等修正监控</h3>
          <div class="statusline"><span>运行状态</span><span class="pill {{ title_runtime.class }}">{{ title_runtime.state }}</span><span class="muted">定时轮询=按间隔自动检查勾选媒体库，不是实时监听。</span></div>
          <p><label><input type="checkbox" name="title_enabled" {% if fixers.title_enabled %}checked{% endif %}> 启动定时轮询</label></p>
          <p><label>运行间隔 分钟<br><input name="title_interval" type="number" min="1" max="1440" value="{{ fixers.title_interval_minutes }}"></label></p>
          <h3>刷新媒体库</h3>
          <div class="checks">{% for lib in libs %}<label><input type="checkbox" name="title_roots" value="{{ lib }}" {% if lib in fixers.title_roots %}checked{% endif %}> {{ lib }}</label>{% endfor %}</div>
          <p><button formaction="{{ url_for('run_fixer_once', _anchor='strm-monitor') }}" name="kind" value="title" class="warn" type="submit">补齐缺失和未扫描</button><button formaction="{{ url_for('run_fixer_once', _anchor='strm-monitor') }}" name="kind" value="title-full" class="danger" type="submit" onclick="return confirm('只会扫描当前勾选的媒体库；全局扫描补齐会让勾选媒体库全部重新请求中文元数据，确定执行？')">全局扫描补齐</button><button formaction="{{ url_for('run_fixer_once', _anchor='strm-monitor') }}" name="kind" value="title-log" type="submit">日志</button></p>
        </div>
      </div>
      {% if not libs %}<p class="muted">还没从 Emby 数据库发现 /home 下的 STRM 媒体库。</p>{% endif %}
      <p><button type="submit">保存 STRM 监控设置</button></p>
    </form>
  </section>
</div>
""", units=units, mount_units=mount_units, mount_configs={name: rclone_mount_config(name) for name, _, _ in mount_units}, mount_defaults_json=json.dumps(RCLONE_MOUNT_DEFAULTS), mount_help=RCLONE_MOUNT_HELP, containers=containers, web_apps=web_apps(), tasks=tasks, remotes=remotes, libs=libs, fixers=fixers, image_runtime=fixer_runtime("emby-fix-strm-images.service", "emby-fix-strm-images-full.service"), title_runtime=fixer_runtime("emby-fix-strm-titles.service", "emby-fix-strm-titles-full.service"), prewarm=read_prewarm_env(), configs={key: editable_config(key) for key in CONFIG_EDITORS}, mb=mb, csrf=csrf_token())


@app.route("/unit", methods=["POST"])
def unit_action():
    try:
        require_csrf()
        unit = request.form.get("unit", "")
        action = request.form.get("action", "")
        dynamic_rclone = request.form.get("dynamic_rclone") == "1"
        if unit not in SYSTEMD_UNITS and not (dynamic_rclone and unit.startswith("rclone-") and unit.endswith(".service")):
            raise ValueError("未知服务。")
        meta = SYSTEMD_UNITS.get(unit, {"label": unit, "log": unit, "actions": ("start", "stop", "restart")})
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


@app.route("/mount/save", methods=["POST"])
def save_mount():
    try:
        require_csrf()
        unit = request.form.get("unit", "")
        remote = request.form.get("remote", "").strip()
        mount_path = request.form.get("mount_path", "").strip()
        options = {key: request.form.get(f"opt_{key}", "").strip() for key in RCLONE_MOUNT_DEFAULTS}
        write_rclone_mount_service(unit, remote, mount_path, options)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", unit])
        result = run(["systemctl", "restart", unit], timeout=120)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or "重启挂载失败。")
        flash("Rclone 挂载参数已保存并重启。")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


def clean_remote_path(value: str) -> str:
    parts = [part for part in value.strip().strip("/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("云端目录不能包含 . 或 ..。")
    return "/".join(parts)


def clean_local_path(value: str) -> str:
    path = Path(value.strip())
    if not path.is_absolute():
        raise ValueError("本地目录必须是绝对路径。")
    resolved = path.resolve(strict=False)
    if resolved in {Path("/"), Path("/home")}:
        raise ValueError("不能把 / 或 /home 作为同步目标。")
    if not str(resolved).startswith("/home/"):
        raise ValueError("同步目标只允许放在 /home 下的具体子目录。")
    return str(resolved)


def update_sync_task_from_form(data: dict, task_id: str) -> dict:
    task = None
    for item in data.get("tasks", []):
        if item.get("id") == task_id:
            task = item
            break
    if task is None:
        raise ValueError("同步任务不存在。")
    mode = request.form.get("mode", "copy")
    if mode not in {"copy", "sync"}:
        raise ValueError("同步模式无效。")
    if mode == "sync" and request.form.get("confirm_mirror") != "on":
        raise ValueError("镜像同步必须勾选确认删除。")
    task.update(
        {
            "name": request.form.get("name", task_id).strip() or task_id,
            "remote": request.form.get("remote", "").strip(),
            "remote_path": clean_remote_path(request.form.get("remote_path", "")),
            "local_path": clean_local_path(request.form.get("local_path", "")),
            "interval_minutes": max(1, min(1440, int(request.form.get("interval_minutes", "10")))),
            "transfers": max(1, min(32, int(request.form.get("transfers", "16")))),
            "checkers": max(1, min(64, int(request.form.get("checkers", "16")))),
            "mode": mode,
            "enabled": request.form.get("enabled") == "on",
            "metadata_only": request.form.get("metadata_only") == "on",
            "confirm_mirror": request.form.get("confirm_mirror") == "on",
        }
    )
    return task


@app.route("/sync-task/save", methods=["POST"])
def save_sync_task():
    try:
        require_csrf()
        task_id = request.form.get("task_id", "")
        data = sync_settings()
        update_sync_task_from_form(data, task_id)
        save_sync_settings(data)
        flash("同步任务已保存。")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/sync-task/action", methods=["POST"])
def sync_task_action():
    try:
        require_csrf()
        task_id = request.form.get("task_id", "")
        action = request.form.get("action", "")
        data = sync_settings()
        task = update_sync_task_from_form(data, task_id)
        save_sync_settings(data)
        unit = sync_task_unit(task_id)
        if action == "run":
            start_sync_task_once(task)
            flash(f"{task.get('name', task_id)} 已开始同步。")
        elif action == "stop":
            result = run(["systemctl", "stop", unit], timeout=120)
            if result.returncode != 0 and "not loaded" not in (result.stderr + result.stdout).lower():
                raise ValueError(result.stderr.strip() or result.stdout.strip() or "停止同步任务失败。")
            flash(f"{task.get('name', task_id)} 已停止。")
        elif action == "log":
            return show_log(unit, "journal")
        else:
            raise ValueError("不允许的操作。")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/sync-task/add", methods=["POST"])
def add_sync_task():
    try:
        require_csrf()
        data = sync_settings()
        name = request.form.get("name", "").strip()
        task_id = sanitize_task_id(name)
        used = {str(task.get("id")) for task in data.get("tasks", [])}
        base_id = task_id
        counter = 2
        while task_id in used:
            task_id = f"{base_id}-{counter}"
            counter += 1
        remotes = rclone_remotes()
        task = RCLONE_SYNC_DEFAULT_TASKS[0].copy()
        task.update({"id": task_id, "name": name or task_id, "remote": remotes[0] if remotes else "", "remote_path": f"media/{task_id}", "local_path": f"/home/{task_id}"})
        data.setdefault("tasks", []).append(task)
        save_sync_settings(data)
        flash("同步任务已添加。")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


@app.route("/sync-task/delete", methods=["POST"])
def delete_sync_task():
    try:
        require_csrf()
        task_id = request.form.get("task_id", "")
        data = sync_settings()
        before = len(data.get("tasks", []))
        data["tasks"] = [task for task in data.get("tasks", []) if task.get("id") != task_id]
        if len(data["tasks"]) == before:
            raise ValueError("同步任务不存在。")
        run(["systemctl", "stop", sync_task_unit(task_id)], timeout=30)
        save_sync_settings(data)
        flash("同步任务已删除。")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
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


@app.route("/config/save", methods=["POST"])
def save_config():
    try:
        require_csrf()
        key = request.form.get("key", "")
        if key not in CONFIG_EDITORS:
            raise ValueError("未知配置文件。")
        content = request.form.get("content", "")
        if len(content.encode("utf-8")) > 1024 * 1024:
            raise ValueError("配置文件超过 1MB，控制台不保存这么大的文件。")
        item = CONFIG_EDITORS[key]
        path = item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = path.with_name(f"{path.name}.bak-{stamp}")
            backup.write_bytes(path.read_bytes())
        path.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
        if "env" in key:
            os.chmod(path, 0o600)
        restart_after_config_save(item)
        flash(f"{item['label']} 已保存并应用。")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard"))


def show_log(target: str, mode: str):
    command = ["journalctl", "-u", target, "-n", "500", "--no-pager"] if mode == "journal" else ["docker", "logs", "--tail", "500", target]
    result = run(command, timeout=30)
    text = (result.stdout + result.stderr).strip() or "没有日志。"
    return page("日志", """<div class="card wide"><h2>{{ target }}</h2><p><a class="btn" href="{{ url_for('dashboard') }}">返回</a></p><pre>{{ text }}</pre></div>""", target=target, text=text)


@app.route("/fixers", methods=["POST"])
def save_fixers():
    try:
        require_csrf()
        save_fixer_config_from_form()
        flash("STRM 监控设置已保存。")
    except (ValueError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard", _anchor="strm-monitor"))


def save_fixer_config_from_form() -> dict:
    libs = set(discover_libraries())
    image_roots = [p for p in request.form.getlist("image_roots") if p in libs]
    title_roots = [p for p in request.form.getlist("title_roots") if p in libs]
    image_enabled = request.form.get("image_enabled") == "on"
    title_enabled = request.form.get("title_enabled") == "on"
    image_interval = max(1, min(1440, int(request.form.get("image_interval", "30"))))
    title_interval = max(1, min(1440, int(request.form.get("title_interval", "15"))))
    data = {"image_interval_minutes": image_interval, "title_interval_minutes": title_interval, "image_enabled": image_enabled, "title_enabled": title_enabled, "image_roots": image_roots, "title_roots": title_roots}
    write_json(FIXER_SETTINGS, data)
    write_json(FIXER_ROOTS, {"image_roots": image_roots, "title_roots": title_roots})
    set_timer("emby-fix-strm-images.timer", "emby-fix-strm-images.service", "5min", image_interval)
    set_timer("emby-fix-strm-titles.timer", "emby-fix-strm-titles.service", "10min", title_interval)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "emby-fix-strm-images.timer"])
    run(["systemctl", "enable", "emby-fix-strm-titles.timer"])
    run(["systemctl", "restart", "emby-fix-strm-images.timer"] if image_enabled else ["systemctl", "stop", "emby-fix-strm-images.timer"])
    run(["systemctl", "restart", "emby-fix-strm-titles.timer"] if title_enabled else ["systemctl", "stop", "emby-fix-strm-titles.timer"])
    return data


@app.route("/fixers/run", methods=["POST"])
def run_fixer_once():
    try:
        require_csrf()
        save_fixer_config_from_form()
        kind = request.form.get("kind", "")
        if kind == "image-log":
            return show_log("emby-fix-strm-images.service", "journal")
        if kind == "title-log":
            return show_log("emby-fix-strm-titles.service", "journal")
        commands = {
            "image": ["systemctl", "start", "--no-block", "emby-fix-strm-images.service"],
            "title": ["systemctl", "start", "--no-block", "emby-fix-strm-titles.service"],
            "image-full": ["systemd-run", "--unit", "emby-fix-strm-images-full", "--collect", "--property=Type=oneshot", "--setenv=FIX_REFRESH_MODE=full", "/usr/bin/python3", "/root/docker-compose/emby-tools/fix-strm-images.py"],
            "title-full": ["systemd-run", "--unit", "emby-fix-strm-titles-full", "--collect", "--property=Type=oneshot", "/bin/bash", "-lc", "FIX_REFRESH_MODE=full /root/docker-compose/emby-tools/fix-emby-strm-chinese-titles.sh apply"],
        }
        command = commands.get(kind)
        if not command:
            raise ValueError("未知 STRM 任务。")
        result = run(command, timeout=120)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or "运行失败。")
        flash("已触发后台运行，刷新本区块可看运行状态；完成结果看日志按钮。")
    except (ValueError, subprocess.TimeoutExpired) as error:
        flash(str(error))
    return redirect(url_for("dashboard", _anchor="strm-monitor"))


@app.route("/prewarm", methods=["POST"])
def save_prewarm():
    try:
        require_csrf()
        head = max(1, min(512, int(request.form.get("head_mb", "32")))) * 1048576
        tail = max(0, min(128, int(request.form.get("tail_mb", "4")))) * 1048576
        resume = max(0, min(512, int(request.form.get("resume_mb", "64")))) * 1048576
        workers = max(1, min(8, int(request.form.get("workers", "2"))))
        PREWARM_DROPIN.parent.mkdir(parents=True, exist_ok=True)
        PREWARM_DROPIN.write_text("[Service]\n" f"Environment=EMBY_PREWARM_HEAD_BYTES={head}\n" f"Environment=EMBY_PREWARM_TAIL_BYTES={tail}\n" f"Environment=EMBY_PREWARM_RESUME_BYTES={resume}\n" f"Environment=EMBY_PREWARM_MAX_WORKERS={workers}\n", encoding="utf-8")
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
            CREDS_FILE.write_text(f"URL: {URLS['control']}\nUsername: {username}\nPassword: {new}\n", encoding="utf-8")
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
