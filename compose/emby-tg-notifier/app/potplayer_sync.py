"""Scoped PotPlayer grants, paired desktop delivery, and Emby user-data sync."""
import asyncio
import base64
import hashlib
import html
import json
import math
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse


class PotPlayerSync:
    def __init__(self, app, host):
        self.h = host
        self.locks = [asyncio.Lock() for _ in range(64)]
        app.add_api_route('/ps/{ticket}', self.browser, methods=['GET'])
        app.add_api_route('/potplayer/claim/{ticket}', self.claim, methods=['POST'])
        app.add_api_route('/potplayer/report', self.report, methods=['POST'])
        app.add_api_route('/potplayer/pair/{code}', self.pair, methods=['POST'])
        app.add_api_route('/potplayer/poll', self.poll, methods=['POST'])
        app.add_api_route('/potplayer/revoke', self.revoke, methods=['POST'])

    def init_db(self):
        with self.h['db']() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS pp_pairs(code_hash TEXT PRIMARY KEY, server_id INTEGER,
                tg_user_id INTEGER, emby_user_id TEXT, expires_at REAL);
            CREATE TABLE IF NOT EXISTS pp_devices(token_hash TEXT PRIMARY KEY, server_id INTEGER,
                tg_user_id INTEGER, emby_user_id TEXT, last_seen REAL, busy_until REAL DEFAULT 0,
                UNIQUE(server_id,tg_user_id));
            CREATE TABLE IF NOT EXISTS pp_jobs(id INTEGER PRIMARY KEY, device_hash TEXT,
                ticket TEXT, expires_at REAL, delivered INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS pp_sessions(token TEXT PRIMARY KEY, server_id INTEGER,
                tg_user_id INTEGER, emby_user_id TEXT, item_id TEXT, device_hash TEXT,
                created_at REAL, expires_at REAL, position REAL DEFAULT 0, duration REAL DEFAULT 0,
                play_count INTEGER DEFAULT 0, started INTEGER DEFAULT 0, stopped INTEGER DEFAULT 0,
                seq INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS pp_session_scope ON pp_sessions(server_id,tg_user_id,item_id);
            ''')
        c.close()

    def query(self, sql, args=()):
        c = self.h['db']()
        try:
            rows = c.execute(sql, args).fetchall()
            c.commit()
            return [dict(r) for r in rows]
        finally:
            c.close()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def scope(self, sid, uid, expected=None):
        s = self.h['get_server'](sid)
        b = self.h['get_tg_binding'](sid, uid)
        if not s or not s['tg_binding_enabled'] or not b or (expected and b['emby_user_id'] != expected):
            raise HTTPException(403, 'Binding revoked or changed')
        return dict(s), dict(b)

    async def live_scope(self, sid, uid, expected=None):
        server, binding = self.scope(sid, uid, expected)
        try:
            user = await self.h['emby_get'](server, '/Users/'+quote(binding['emby_user_id'],safe=''))
        except Exception:
            raise HTTPException(503, 'Emby user verification unavailable')
        policy = (user or {}).get('Policy') or {}
        if not user or str(user.get('Id')) != binding['emby_user_id'] or policy.get('IsDisabled') or policy.get('EnableMediaPlayback') is False:
            raise HTTPException(403, 'Emby user unavailable or playback disabled')
        name = str(user.get('Name') or binding['emby_username'])
        if name != binding['emby_username']:
            self.query('UPDATE tg_bindings SET emby_username=? WHERE server_id=? AND tg_user_id=? AND emby_user_id=?',
                       (name,sid,uid,binding['emby_user_id']))
            binding['emby_username'] = name
        return server, binding

    def bearer(self, request):
        value = request.headers.get('authorization', '')
        if not value.startswith('Bearer ') or len(value) > 200:
            raise HTTPException(401, 'Missing credential')
        return value[7:]

    async def body(self, request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise HTTPException(413, 'Request too large')
        try:
            data = json.loads(raw)
        except Exception:
            raise HTTPException(400, 'Invalid JSON')
        if not isinstance(data, dict):
            raise HTTPException(400, 'Invalid JSON')
        return data

    def device(self, request):
        key = self.digest(self.bearer(request))
        rows = self.query('SELECT * FROM pp_devices WHERE token_hash=?', (key,))
        if not rows:
            raise HTTPException(401, 'Device revoked')
        d = rows[0]
        self.scope(d['server_id'], d['tg_user_id'], d['emby_user_id'])
        return d

    async def bot_command(self, token, msg, command):
        if command not in {'/pc', '/pc_off'}:
            return False
        uid = int(msg['from']['id'])
        servers = [s for s in self.h['servers_for_binding_bot'](token)
                   if self.h['get_tg_binding'](s['id'], uid)]
        args = str(msg.get('text') or '').split()
        if len(args) > 1:
            servers = [s for s in servers if str(s['id']) == args[1]]
        self.h['bot_delete_message_later'](token, uid, msg.get('message_id'), 10)
        if len(servers) != 1:
            await self.h['bot_send'](token, uid, '请先绑定服务器；有多个绑定时发送 /pc 服务器编号。\n' +
                                     '\n'.join(f"{s['id']}: {html.escape(s['name'])}" for s in servers))
            return True
        server, binding = self.scope(servers[0]['id'], uid)
        sid = server['id']
        if command == '/pc_off':
            self.query('DELETE FROM pp_devices WHERE server_id=? AND tg_user_id=?', (sid, uid))
            self.query('DELETE FROM pp_pairs WHERE server_id=? AND tg_user_id=?', (sid, uid))
            await self.h['bot_send'](token, uid, '已撤销电脑配对，PotPlayer 恢复浏览器入口。')
            return True
        try:
            server, binding = await self.live_scope(server['id'], uid)
        except HTTPException:
            await self.h['bot_send'](token, uid, '当前绑定的 Emby 用户无法通过实时核验，请检查用户和服务器。')
            return True
        base = self.h['normalize_url'](server.get('notifier_public_url') or '')
        if not base:
            await self.h['bot_send'](token, uid, '管理员尚未配置通知程序公网地址。')
            return True
        self.query('DELETE FROM pp_pairs WHERE expires_at<? OR (server_id=? AND tg_user_id=?)', (time.time(), sid, uid))
        code = secrets.token_urlsafe(24)
        self.query('INSERT INTO pp_pairs VALUES(?,?,?,?,?)',
                   (self.digest(code), sid, uid, binding['emby_user_id'], time.time()+300))
        link = base + '/potplayer/pair/' + code
        sent = await self.h['bot_send'](token, uid,
            '方法 2 电脑配对：复制下方地址，粘贴到安装窗口。有效期 5 分钟，只能使用一次。'
            '\n此地址相当于配对口令，请勿转发。配对后点击频道 PotPlayer 会在该电脑播放。'
            '\n关闭直达：/pc_off\n<code>' + html.escape(link) + '</code>')
        if isinstance(sent, dict):
            self.h['bot_delete_message_later'](token, uid, sent.get('message_id'), 300)
        return True

    async def pair(self, code: str):
        if len(code) > 100:
            raise HTTPException(403)
        pending = self.query('SELECT * FROM pp_pairs WHERE code_hash=? AND expires_at>?', (self.digest(code),time.time()))
        if not pending:
            raise HTTPException(403, 'Pairing code expired or used')
        await self.live_scope(pending[0]['server_id'],pending[0]['tg_user_id'],pending[0]['emby_user_id'])
        c = self.h['db']()
        try:
            c.execute('BEGIN IMMEDIATE')
            r = c.execute('SELECT * FROM pp_pairs WHERE code_hash=? AND expires_at>?',
                          (self.digest(code), time.time())).fetchone()
            if not r:
                raise HTTPException(403, 'Pairing code expired or used')
            s, b = self.scope(r['server_id'], r['tg_user_id'], r['emby_user_id'])
            token = secrets.token_urlsafe(32)
            c.execute('DELETE FROM pp_devices WHERE server_id=? AND tg_user_id=?', (r['server_id'], r['tg_user_id']))
            c.execute('INSERT INTO pp_devices VALUES(?,?,?,?,?,0)',
                      (self.digest(token), r['server_id'], r['tg_user_id'], b['emby_user_id'], 0))
            c.execute('DELETE FROM pp_pairs WHERE code_hash=?', (self.digest(code),))
            c.commit()
        finally:
            c.close()
        return JSONResponse({'token':token, 'server':s['name']}, headers={'Cache-Control':'no-store'})

    def dispatch(self, server, uid, item_id):
        # No offline queue: only an actively polling, idle, paired desktop is eligible.
        s, b = self.scope(server['id'], uid)
        rows = self.query('SELECT * FROM pp_devices WHERE server_id=? AND tg_user_id=? AND emby_user_id=?',
                          (s['id'], uid, b['emby_user_id']))
        if not rows:
            return 'offline'
        d = rows[0]
        if d['busy_until'] > time.time():
            return 'busy'
        if d['last_seen'] < time.time()-15:
            return 'offline'
        ticket = self.h['create_senplayer_ticket'](s['id'], item_id, uid, 60, player='pp')
        c = self.h['db']()
        try:
            cur = c.execute('UPDATE pp_devices SET busy_until=? WHERE token_hash=? AND busy_until<?',
                            (time.time()+60, d['token_hash'], time.time()))
            if cur.rowcount != 1:
                return 'busy'
            c.execute('DELETE FROM pp_jobs WHERE expires_at<? OR delivered=1', (time.time(),))
            c.execute('INSERT INTO pp_jobs(device_hash,ticket,expires_at) VALUES(?,?,?)',
                      (d['token_hash'], ticket, time.time()+60))
            c.commit()
        finally:
            c.close()
        return 'sent'

    async def poll(self, request: Request):
        d = self.device(request)
        c = self.h['db']()
        try:
            c.execute('BEGIN IMMEDIATE')
            c.execute('UPDATE pp_devices SET last_seen=? WHERE token_hash=?', (time.time(), d['token_hash']))
            r = c.execute('SELECT * FROM pp_jobs WHERE device_hash=? AND delivered=0 AND expires_at>? ORDER BY id LIMIT 1',
                          (d['token_hash'], time.time())).fetchone()
            if r:
                c.execute('UPDATE pp_jobs SET delivered=1 WHERE id=?', (r['id'],))
            c.commit()
            return JSONResponse({'ticket': r['ticket'] if r else None}, headers={'Cache-Control':'no-store'})
        finally:
            c.close()

    async def revoke(self, request: Request):
        # A device can revoke itself even after its Emby user/binding is removed.
        key = self.digest(self.bearer(request))
        self.query('DELETE FROM pp_devices WHERE token_hash=?', (key,))
        return {'ok':True}

    async def browser(self, ticket: str):
        if not self.query("SELECT token FROM senplayer_tickets WHERE token=? AND player='pp' AND used_at=0 AND expires_at>?", (ticket, time.time())):
            raise HTTPException(403, 'Playback link expired')
        row = self.query('SELECT server_id FROM senplayer_tickets WHERE token=?', (ticket,))[0]
        server = dict(self.h['get_server'](row['server_id']))
        base = self.h['normalize_url'](server.get('notifier_public_url') or '')
        payload = base64.urlsafe_b64encode((base+'/potplayer/claim/'+ticket).encode()).decode().rstrip('=')
        return RedirectResponse('hdz-potplayer-sync://play/'+payload, status_code=302,
                                headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

    async def claim(self, ticket: str, request: Request):
        device_hash = ''
        if request.headers.get('authorization'):
            d = self.device(request)
            device_hash = d['token_hash']
            rows = self.query('SELECT * FROM pp_jobs WHERE device_hash=? AND ticket=? AND expires_at>?',
                              (device_hash, ticket, time.time()))
            if not rows:
                raise HTTPException(403, 'Wrong desktop')
        elif self.query('SELECT id FROM pp_jobs WHERE ticket=?', (ticket,)):
            raise HTTPException(403, 'Desktop credential required')
        grant = self.h['consume_senplayer_ticket'](ticket, 'pp')
        if not grant:
            raise HTTPException(403, 'Playback link expired or used')
        s, b = await self.live_scope(grant['server_id'], grant['tg_user_id'])
        sid, uid, item = s['id'], grant['tg_user_id'], str(grant['item_id'])
        # Read the bound user's accessible item before issuing a playback grant.
        data = await self.h['emby_get'](s, f"/Users/{quote(b['emby_user_id'],safe='')}/Items/{quote(item,safe='')}?Fields=UserData")
        if not data or str(data.get('Id')) != item or data.get('IsFolder'):
            raise HTTPException(403, 'Media unavailable')
        ud = data.get('UserData') or {}
        base = self.h['normalize_url'](s.get('senplayer_emby_url') or s.get('emby_url') or '')
        if urlsplit(base).scheme not in {'http','https'} or not s.get('emby_api_key'):
            raise HTTPException(503, 'Playback not configured')
        token = secrets.token_urlsafe(32)
        duration = max(0, int(data.get('RunTimeTicks') or 0)/10000000)
        resume = 0 if ud.get('Played') else max(0, int(ud.get('PlaybackPositionTicks') or 0)/10000000)
        self.query('DELETE FROM pp_sessions WHERE expires_at<?', (time.time(),))
        self.query('''INSERT INTO pp_sessions(token,server_id,tg_user_id,emby_user_id,item_id,device_hash,
                   created_at,expires_at,position,duration,play_count) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                   (token,sid,uid,b['emby_user_id'],item,device_hash,time.time(),time.time()+86400,resume,duration,int(ud.get('PlayCount') or 0)))
        if grant.get('tg_message_id'):
            self.h['bot_delete_message_later'](self.h['binding_bot_token_for_server'](s),grant['tg_chat_id'],grant['tg_message_id'],0)
        return JSONResponse({'token':token, 'resume':resume, 'duration':duration,
                             'title':'HDZ-'+token[:10],
                             'url':base+'/emby/Videos/'+quote(item,safe='')+'/stream?Static=true&api_key='+quote(s['emby_api_key'],safe='')},
                            headers={'Cache-Control':'no-store'})

    async def write_progress(self, server, row, position, finished):
        current = await self.h['emby_get'](server, '/Users/'+quote(row['emby_user_id'],safe='')+
                                          '/Items/'+quote(row['item_id'],safe='')+'?Fields=UserData')
        if not current or str(current.get('Id')) != row['item_id']:
            raise HTTPException(403, 'Media no longer accessible')
        # Preserve favorites/likes and prior watched state; do not reset other UserData fields.
        payload = dict(current.get('UserData') or {})
        payload.update({'PlaybackPositionTicks':0 if finished else int(position*10000000),
                        'LastPlayedDate':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                        'PlayCount':max(int(payload.get('PlayCount') or 0),row['play_count']+1),
                        'Played':bool(payload.get('Played') or finished)})
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(self.h['normalize_url'](server['emby_url'])+'/emby/Users/'+
                                  quote(row['emby_user_id'],safe='')+'/Items/'+quote(row['item_id'],safe='')+'/UserData',
                                  headers={'X-Emby-Token':server['emby_api_key']}, json=payload)
            r.raise_for_status()

    async def report(self, request: Request):
        token = self.bearer(request)
        body = await self.body(request)
        event = body.get('event')
        seq, pos, duration = body.get('seq'), body.get('position'), body.get('duration')
        if event not in {'progress','stop'} or type(seq) is not int or not 1 <= seq <= 1000000:
            raise HTTPException(400, 'Invalid event')
        if any(type(v) not in {int,float} or not math.isfinite(v) for v in (pos,duration)) or not 0 <= pos <= duration+2 or not 0 < duration <= 1209600:
            raise HTTPException(400, 'Invalid playback position')
        rows = self.query('SELECT * FROM pp_sessions WHERE token=? AND expires_at>?', (token,time.time()))
        if not rows:
            raise HTTPException(401, 'Playback grant expired')
        scope = rows[0]
        lock = self.locks[(scope['server_id']+scope['tg_user_id']) % len(self.locks)]
        async with lock:
            row = self.query('SELECT * FROM pp_sessions WHERE token=?', (token,))[0]
            s, b = await self.live_scope(row['server_id'],row['tg_user_id'],row['emby_user_id'])
            if row['device_hash'] and not self.query('SELECT token_hash FROM pp_devices WHERE token_hash=?',(row['device_hash'],)):
                raise HTTPException(403, 'Desktop revoked')
            if seq <= row['seq']:
                return {'ok':True,'duplicate':True}
            if row['stopped']:
                raise HTTPException(409, 'Playback already ended')
            if self.query('''SELECT token FROM pp_sessions WHERE server_id=? AND tg_user_id=? AND item_id=?
                             AND created_at>? AND started=1 LIMIT 1''',
                          (row['server_id'],row['tg_user_id'],row['item_id'],row['created_at'])):
                raise HTTPException(409, 'Newer playback superseded this session')
            # A failed open must not turn an existing resume point into zero or add a play.
            if not row['started'] and pos <= 0:
                raise HTTPException(400, 'No confirmed playback yet')
            finished = event == 'stop' and pos >= duration*0.95
            try:
                await self.write_progress(s,row,min(pos,duration),finished)
            except Exception:
                raise HTTPException(502, 'Emby progress write failed; retry this sequence')
            self.query('UPDATE pp_sessions SET seq=?,position=?,duration=?,started=1,stopped=? WHERE token=?',
                       (seq,pos,duration,int(event=='stop'),token))
            if row['device_hash']:
                self.query('UPDATE pp_devices SET last_seen=?,busy_until=? WHERE token_hash=?',
                           (time.time(),0 if event=='stop' else time.time()+60,row['device_hash']))
            return {'ok':True,'finished':finished}
