#!/usr/bin/env python3
"""Authenticated control panel for the Emby stack helper services."""
from __future__ import annotations

import argparse, json, os, re, secrets, subprocess
from pathlib import Path
from flask import Flask, flash, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

APP_ROOT = Path('/root/docker-compose/stack-control')
SETTINGS_FILE = APP_ROOT / 'settings.json'
CREDS_FILE = APP_ROOT / 'credentials.txt'
PREWARM_DROPIN = Path('/etc/systemd/system/emby-play-prewarm.service.d/override.conf')
SYSTEMD_UNITS = {
    'emby-play-prewarm.service': {'label':'Emby 播放预热','log':'emby-play-prewarm.service','actions':('start','stop','restart')},
    'emby-fix-strm-images.timer': {'label':'STRM 图片补齐监控','log':'emby-fix-strm-images.service','actions':('start','stop','restart'),'run_unit':'emby-fix-strm-images.service'},
    'emby-fix-strm-titles.timer': {'label':'STRM 中文标题监控','log':'emby-fix-strm-titles.service','actions':('start','stop','restart'),'run_unit':'emby-fix-strm-titles.service'},
    'rclone-zero.service': {'label':'Rclone zero 挂载','log':'rclone-zero.service','actions':('start','stop','restart')},
    'rclone-h2.service': {'label':'Rclone h2 挂载','log':'rclone-h2.service','actions':('start','stop','restart')},
    'rclone-sync-web.service': {'label':'Rclone 同步控制台','log':'rclone-sync-web.service','actions':('start','stop','restart')},
    'embystream.service': {'label':'EmbyStream 备用线路','log':'embystream.service','actions':('start','stop','restart')},
}
DOCKER_CONTAINERS = {'emby':'Emby','cd2':'CloudDrive2','symedia':'Symedia','autofilm':'AutoFilm'}
PREWARM_DEFAULTS = {'EMBY_PREWARM_HEAD_BYTES':33554432,'EMBY_PREWARM_TAIL_BYTES':4194304,'EMBY_PREWARM_MAX_WORKERS':2}

def run(cmd:list[str], timeout:int=30):
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)

def read_json(path:Path, default:dict):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else default.copy()
    except Exception:
        return default.copy()

def write_json(path:Path, value:dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.new')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chmod(tmp,0o600); os.replace(tmp,path)

def initial_settings():
    user=os.environ.get('STACK_CONTROL_INITIAL_USER','admin').strip() or 'admin'
    password=os.environ.get('STACK_CONTROL_INITIAL_PASSWORD','')
    generated=False
    if not password:
        password=secrets.token_urlsafe(18); generated=True
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(f'URL: /control/\nUsername: {user}\nPassword: {password}\n',encoding='utf-8')
    os.chmod(CREDS_FILE,0o600)
    return {'secret_key':secrets.token_hex(32),'username':user,'password_hash':generate_password_hash(password),'generated_password':generated}

def initialize():
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists(): write_json(SETTINGS_FILE, initial_settings())
initialize()
settings=read_json(SETTINGS_FILE, {'secret_key':secrets.token_hex(32),'username':'admin','password_hash':''})
app=Flask(__name__); app.secret_key=settings['secret_key']; app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
BASE='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }} · Emby Stack Control</title><style>:root{color-scheme:dark;--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--blue:#2f81f7;--green:#2ea043;--red:#da3633;--yellow:#d29922}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}header{height:56px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:#010409}header a{color:var(--text);text-decoration:none;margin-left:14px}.wrap{max-width:1320px;margin:22px auto;padding:0 18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}.wide{grid-column:1/-1}h1,h2,h3{margin:0 0 12px}h1{font-size:20px}h2{font-size:17px}h3{font-size:15px}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}th{color:var(--muted);font-weight:600}.pill{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;font-size:12px}.on{background:#143d2a;color:#7ee787}.off{background:#3d1f1c;color:#ff938a}.unknown{background:#3b3219;color:#e3b341}button,.btn{border:0;border-radius:6px;padding:7px 10px;margin:2px;background:var(--blue);color:white;font-weight:700;cursor:pointer}.danger{background:var(--red)}.okbtn{background:var(--green)}.warn{background:var(--yellow);color:#111}input{width:100%;padding:9px;background:#0d1117;color:var(--text);border:1px solid var(--line);border-radius:6px}.row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.muted{color:var(--muted)}.flash{background:#1f2a44;border:1px solid #315a9d;border-radius:8px;padding:10px;margin-bottom:12px}pre{white-space:pre-wrap;background:#010409;border:1px solid var(--line);border-radius:8px;padding:12px;max-height:52vh;overflow:auto;font:12px/1.55 Consolas,monospace}@media(max-width:760px){.row{grid-template-columns:1fr}table{font-size:12px}th,td{padding:8px 5px}}</style></head><body><header><strong>Emby Stack Control</strong>{% if session.get("user") %}<nav><a href="{{ url_for('dashboard') }}">控制台</a><a href="{{ url_for('account') }}">账号</a><a href="{{ url_for('logout') }}">退出</a></nav>{% endif %}</header><main class="wrap">{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}{{ body|safe }}</main></body></html>'''

def page(title, body, **ctx): return render_template_string(BASE,title=title,body=render_template_string(body,**ctx))
def csrf_token():
    session.setdefault('csrf', secrets.token_urlsafe(24)); return session['csrf']
def require_csrf():
    if not secrets.compare_digest(request.form.get('csrf',''), session.get('csrf','')): raise ValueError('页面令牌失效，请刷新后重试。')
def logged(): return session.get('user')==settings.get('username')
@app.before_request
def gate():
    if request.endpoint in {'login','healthz'}: return None
    if not logged(): return redirect(url_for('login'))
@app.route('/healthz')
def healthz(): return jsonify(ok=True)
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form.get('username',''); p=request.form.get('password','')
        if secrets.compare_digest(u,settings.get('username','')) and check_password_hash(settings.get('password_hash',''),p):
            session.clear(); session['user']=u; csrf_token(); return redirect(url_for('dashboard'))
        flash('账号或密码错误。')
    return page('登录','''<div class="card" style="max-width:420px;margin:80px auto"><h1>登录控制台</h1><form method="post"><p><input name="username" placeholder="账号" autocomplete="username" required></p><p><input name="password" type="password" placeholder="密码" autocomplete="current-password" required></p><button type="submit">登录</button></form></div>''')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
def unit_exists(unit):
    r=run(['systemctl','list-unit-files',unit,'--no-legend']); return r.returncode==0 and unit in r.stdout
def unit_status(unit):
    if not unit_exists(unit): return {'exists':False,'active':'missing','enabled':'missing'}
    return {'exists':True,'active':run(['systemctl','is-active',unit]).stdout.strip() or 'unknown','enabled':run(['systemctl','is-enabled',unit]).stdout.strip() or 'unknown'}
def container_status(name):
    r=run(['docker','inspect','-f','{{.State.Status}}|{{.State.Running}}|{{.RestartCount}}',name])
    if r.returncode: return {'exists':False,'status':'missing','running':False,'restarts':'-'}
    status,running,restarts=(r.stdout.strip().split('|')+['','',''])[:3]
    return {'exists':True,'status':status,'running':running=='true','restarts':restarts}
def read_prewarm_env():
    values=PREWARM_DEFAULTS.copy(); r=run(['systemctl','show','emby-play-prewarm.service','-p','Environment','--value'])
    text=r.stdout+'\n'+(PREWARM_DROPIN.read_text(encoding='utf-8',errors='ignore') if PREWARM_DROPIN.exists() else '')
    for k in values:
        m=re.search(rf'{k}=([0-9]+)',text)
        if m: values[k]=int(m.group(1))
    return values
def fmt(v): return f'{v//1024//1024} MB'
@app.route('/')
def dashboard():
    units=[(n,m,unit_status(n)) for n,m in SYSTEMD_UNITS.items()]
    containers=[(n,l,container_status(n)) for n,l in DOCKER_CONTAINERS.items()]
    return page('控制台','''<div class="grid"><section class="card wide"><h2>自定义服务和定时器</h2><table><thead><tr><th>功能</th><th>状态</th><th>开机</th><th>操作</th></tr></thead><tbody>{% for name, meta, st in units %}<tr><td><strong>{{ meta.label }}</strong><br><span class="muted">{{ name }}</span></td><td><span class="pill {{ 'on' if st.active in ['active','activating'] else 'off' if st.exists else 'unknown' }}">{{ st.active }}</span></td><td>{{ st.enabled }}</td><td>{% if st.exists %}<form method="post" action="{{ url_for('unit_action') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="unit" value="{{ name }}"><button name="action" value="start" class="okbtn">启动</button><button name="action" value="stop" class="danger">停止</button><button name="action" value="restart">重启</button>{% if meta.run_unit %}<button name="action" value="run" class="warn">运行一次</button>{% endif %}<button name="action" value="log">日志</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table></section><section class="card wide"><h2>Docker 容器</h2><table><thead><tr><th>容器</th><th>状态</th><th>重启次数</th><th>操作</th></tr></thead><tbody>{% for name, label, st in containers %}<tr><td><strong>{{ label }}</strong><br><span class="muted">{{ name }}</span></td><td><span class="pill {{ 'on' if st.running else 'off' if st.exists else 'unknown' }}">{{ st.status }}</span></td><td>{{ st.restarts }}</td><td>{% if st.exists %}<form method="post" action="{{ url_for('container_action') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="name" value="{{ name }}"><button name="action" value="start" class="okbtn">启动</button><button name="action" value="stop" class="danger">停止</button><button name="action" value="restart">重启</button><button name="action" value="log">日志</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table></section><section class="card"><h2>播放预热参数</h2><p class="muted">当前：头部 {{ fmt(prewarm.EMBY_PREWARM_HEAD_BYTES) }}，尾部 {{ fmt(prewarm.EMBY_PREWARM_TAIL_BYTES) }}，并发 {{ prewarm.EMBY_PREWARM_MAX_WORKERS }}</p><form method="post" action="{{ url_for('save_prewarm') }}"><input type="hidden" name="csrf" value="{{ csrf }}"><div class="row"><label>头部 MB<input name="head_mb" type="number" min="1" max="512" value="{{ prewarm.EMBY_PREWARM_HEAD_BYTES // 1024 // 1024 }}"></label><label>尾部 MB<input name="tail_mb" type="number" min="0" max="128" value="{{ prewarm.EMBY_PREWARM_TAIL_BYTES // 1024 // 1024 }}"></label><label>并发<input name="workers" type="number" min="1" max="8" value="{{ prewarm.EMBY_PREWARM_MAX_WORKERS }}"></label></div><p><button type="submit">保存并重启预热服务</button></p></form></section><section class="card"><h2>常用入口</h2><p><a class="btn" href="/emby/" target="_blank">Emby</a> <a class="btn" href="/symedia/" target="_blank">Symedia</a> <a class="btn" href="/cd2/" target="_blank">CD2</a></p><p class="muted">这里只放入口，不保存这些服务的登录密码。</p></section></div>''',units=units,containers=containers,prewarm=read_prewarm_env(),fmt=fmt,csrf=csrf_token())
@app.route('/unit', methods=['POST'])
def unit_action():
    try:
        require_csrf(); unit=request.form.get('unit',''); action=request.form.get('action','')
        if unit not in SYSTEMD_UNITS: raise ValueError('未知服务。')
        meta=SYSTEMD_UNITS[unit]
        if action=='log': return show_log(meta['log'],'journal')
        target=meta.get('run_unit') if action=='run' else unit
        if action=='run': r=run(['systemctl','start',target],120)
        elif action in meta['actions']: r=run(['systemctl',action,target],120)
        else: raise ValueError('不允许的操作。')
        if r.returncode: raise ValueError(r.stderr.strip() or r.stdout.strip() or '操作失败。')
        flash(f"{meta['label']} 已执行：{action}")
    except Exception as e: flash(str(e))
    return redirect(url_for('dashboard'))
@app.route('/container', methods=['POST'])
def container_action():
    try:
        require_csrf(); name=request.form.get('name',''); action=request.form.get('action','')
        if name not in DOCKER_CONTAINERS: raise ValueError('未知容器。')
        if action=='log': return show_log(name,'docker')
        if action not in {'start','stop','restart'}: raise ValueError('不允许的操作。')
        r=run(['docker',action,name],120)
        if r.returncode: raise ValueError(r.stderr.strip() or r.stdout.strip() or '操作失败。')
        flash(f'{DOCKER_CONTAINERS[name]} 已执行：{action}')
    except Exception as e: flash(str(e))
    return redirect(url_for('dashboard'))
def show_log(target, mode):
    r=run(['journalctl','-u',target,'-n','160','--no-pager'] if mode=='journal' else ['docker','logs','--tail','160',target],30)
    text=(r.stdout+r.stderr).strip() or '没有日志。'
    return page('日志','''<div class="card wide"><h2>{{ target }}</h2><p><a class="btn" href="{{ url_for('dashboard') }}">返回</a></p><pre>{{ text }}</pre></div>''',target=target,text=text)
@app.route('/prewarm', methods=['POST'])
def save_prewarm():
    try:
        require_csrf(); head=max(1,min(512,int(request.form.get('head_mb','32'))))*1024*1024; tail=max(0,min(128,int(request.form.get('tail_mb','4'))))*1024*1024; workers=max(1,min(8,int(request.form.get('workers','2'))))
        PREWARM_DROPIN.parent.mkdir(parents=True, exist_ok=True)
        PREWARM_DROPIN.write_text('[Service]\n'+f'Environment=EMBY_PREWARM_HEAD_BYTES={head}\n'+f'Environment=EMBY_PREWARM_TAIL_BYTES={tail}\n'+f'Environment=EMBY_PREWARM_MAX_WORKERS={workers}\n',encoding='utf-8')
        run(['systemctl','daemon-reload']); r=run(['systemctl','restart','emby-play-prewarm.service'],120)
        if r.returncode: raise ValueError(r.stderr.strip() or '重启预热服务失败。')
        flash('播放预热参数已保存。')
    except Exception as e: flash(str(e))
    return redirect(url_for('dashboard'))
@app.route('/account', methods=['GET','POST'])
def account():
    if request.method=='POST':
        try:
            require_csrf(); old=request.form.get('old_password',''); username=request.form.get('username','').strip(); new=request.form.get('new_password','')
            if not check_password_hash(settings['password_hash'],old): raise ValueError('原密码错误。')
            if len(username)<3: raise ValueError('账号至少 3 位。')
            if len(new)<8: raise ValueError('新密码至少 8 位。')
            settings.update(username=username,password_hash=generate_password_hash(new),generated_password=False); write_json(SETTINGS_FILE,settings); session.clear(); flash('账号密码已修改，请重新登录。'); return redirect(url_for('login'))
        except Exception as e: flash(str(e))
    return page('账号','''<div class="card" style="max-width:520px;margin:auto"><h1>修改账号密码</h1><form method="post"><input type="hidden" name="csrf" value="{{ csrf }}"><p><input name="username" value="{{ username }}" required></p><p><input name="old_password" type="password" placeholder="原密码" required></p><p><input name="new_password" type="password" placeholder="新密码，至少 8 位" required></p><button type="submit">保存</button></form></div>''',username=settings['username'],csrf=csrf_token())
def main():
    p=argparse.ArgumentParser(); p.add_argument('--init',action='store_true'); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',default=6011,type=int); args=p.parse_args()
    if args.init: return
    app.run(host=args.host, port=args.port)
if __name__=='__main__': main()
