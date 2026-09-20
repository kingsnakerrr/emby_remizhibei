import asyncio
import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from starlette.requests import Request


TEMP = tempfile.TemporaryDirectory()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SESSION_SECRET_FILE"] = str(Path(TEMP.name) / "secret")
spec = importlib.util.spec_from_file_location("notifier", Path(__file__).resolve().parents[1] / "app/main.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        m.DB_PATH = str(Path(self.temp.name) / "test.db")
        m.WEBHOOK_LOG_DIR = str(Path(self.temp.name) / "webhooks")
        m.init_db()
        m.pot_sync.init_db()
        conn = m.db()
        conn.execute('DELETE FROM servers')
        conn.execute("""INSERT INTO servers(id,name,webhook_token,emby_url,emby_api_key,
            notifier_public_url,senplayer_user,tg_binding_enabled,tg_binding_bot_token,tg_binding_admin_ids)
            VALUES(1,'Server One','test-secret','https://emby.invalid','test-key',
            'https://notifier.invalid','test-user',1,'test-bot','100')""")
        conn.execute("INSERT INTO tg_bindings(server_id,tg_user_id,emby_user_id,emby_username) VALUES(1,100,'user-1','alice')")
        conn.commit()
        conn.close()
        self.server = dict(m.get_server(1))

    def sql(self, query, args=()):
        conn = m.db()
        rows = conn.execute(query, args).fetchall()
        conn.commit()
        conn.close()
        return rows

    async def open_route(self, route):
        if route == 'ticket':
            ticket = m.create_senplayer_ticket(1, '42', 100)
            return await m.senplayer_ticket_open(ticket)
        if route == 'user':
            sig = m._binding_play_sig(self.server, '42', 100)
            return await m.senplayer_user_open(1, '42', 100, sig)
        return await m.senplayer_open(1, '42', m._senplayer_signature(self.server, '42'))

    async def test_all_routes_resume_without_exit_callback(self):
        with patch.object(m, '_senplayer_resume_seconds', AsyncMock(return_value=75)), patch.object(m, '_resolve_senplayer_user', AsyncMock(return_value={'Id':'user-1'})):
            for route in ('ticket', 'user', 'legacy'):
                with self.subTest(route=route):
                    response = await self.open_route(route)
                    query = parse_qs(urlsplit(response.headers['location']).query)
                    self.assertEqual(query['position'], ['75'])
                    self.assertNotIn('x-success', query)

    async def test_all_routes_opt_in_callback(self):
        self.sql('UPDATE servers SET senplayer_progress_sync=1')
        with patch.object(m, '_senplayer_resume_seconds', AsyncMock(return_value=75)), patch.object(m, '_resolve_senplayer_user', AsyncMock(return_value={'Id':'user-1'})):
            for route in ('ticket', 'user', 'legacy'):
                response = await self.open_route(route)
                self.assertIn('x-success', parse_qs(urlsplit(response.headers['location']).query))

    async def test_play_does_not_wait_for_telegram(self):
        ticket = m.create_senplayer_ticket(1, '42', 100)
        m.attach_senplayer_ticket_message(ticket, 100, 55)
        with patch.object(m, 'bot_api', AsyncMock(side_effect=AssertionError('Playback must not call Telegram'))), patch.object(m, '_senplayer_resume_seconds', AsyncMock(return_value=0)):
            response = await m.senplayer_ticket_open(ticket)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.sql('SELECT * FROM tg_cleanup_jobs')), 1)

    async def test_cleanup_survives_reinitialization(self):
        m.bot_delete_message_later('test-bot', 100, 55, 0)
        m.init_db()
        with patch.object(m, 'bot_delete_message', AsyncMock(return_value=True)) as delete:
            await m.run_cleanup_jobs()
        delete.assert_awaited_once_with('test-bot', '100', 55)
        self.assertEqual(self.sql('SELECT * FROM tg_cleanup_jobs'), [])

    async def test_upgrade_preserves_config_and_binding(self):
        self.sql('DROP TABLE tg_cleanup_jobs')
        m.init_db()
        self.assertEqual(dict(m.get_server(1)), self.server)
        self.assertEqual(m.get_tg_binding(1, 100)['emby_username'], 'alice')
        self.assertEqual(self.sql('SELECT * FROM tg_cleanup_jobs'), [])

    async def test_http_route_and_template(self):
        import httpx
        from jinja2 import Environment, FileSystemLoader
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app), base_url='http://test') as client:
            self.assertEqual((await client.get('/health')).json(), {'ok':True})
            ticket = m.create_senplayer_ticket(1, '42', 100)
            with patch.object(m, '_senplayer_resume_seconds', AsyncMock(return_value=75)):
                response = await client.get('/sp/' + ticket)
            self.assertEqual(response.status_code, 302)
            self.assertNotIn('x-success', response.headers['location'])
        env = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'app/templates')))
        env.get_template('index.html')

    async def test_expired_ticket_rejected(self):
        ticket = m.create_senplayer_ticket(1, '42', 100)
        self.sql('UPDATE senplayer_tickets SET expires_at=0')
        self.assertIsNone(m.consume_senplayer_ticket(ticket))

    async def test_cleanup_retries_then_succeeds(self):
        m.bot_delete_message_later('test-bot', 100, 55, 0)
        with patch.object(m, 'bot_delete_message', AsyncMock(return_value=False)):
            await m.run_cleanup_jobs()
        self.assertEqual(self.sql('SELECT attempts FROM tg_cleanup_jobs')[0]['attempts'], 1)
        self.sql('UPDATE tg_cleanup_jobs SET due_at=0')
        with patch.object(m, 'bot_delete_message', AsyncMock(return_value=True)):
            await m.run_cleanup_jobs()
        self.assertEqual(self.sql('SELECT * FROM tg_cleanup_jobs'), [])

    async def test_cleanup_bounded_retry(self):
        m.bot_delete_message_later('test-bot', 100, 55, 0)
        self.sql('UPDATE tg_cleanup_jobs SET attempts=5')
        with patch.object(m, 'bot_delete_message', AsyncMock(return_value=False)):
            await m.run_cleanup_jobs()
        self.assertEqual(self.sql('SELECT * FROM tg_cleanup_jobs'), [])

    async def test_cleanup_deduplicates_and_expedites(self):
        m.bot_delete_message_later('test-bot', 100, 55, 10)
        m.bot_delete_message_later('test-bot', 100, 55, 0)
        rows = self.sql('SELECT * FROM tg_cleanup_jobs')
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(rows[0]['due_at'], m.time.time())

    async def test_start_command_and_menu_expire(self):
        with patch.object(m, 'bot_api', AsyncMock(return_value={'chat':{'id':100}, 'message_id':56})):
            await m.process_bot_message('test-bot', {'id':9}, {'chat':{'type':'private','id':100}, 'from':{'id':100}, 'text':'/start', 'message_id':55})
        rows = self.sql('SELECT message_id,due_at FROM tg_cleanup_jobs ORDER BY message_id')
        self.assertEqual([r['message_id'] for r in rows], [55, 56])
        for row in rows:
            self.assertAlmostEqual(row['due_at'] - m.time.time(), 10, delta=2)

    async def test_ticket_five_minutes_single_use(self):
        ticket = m.create_senplayer_ticket(1, '42', 100)
        row = m.consume_senplayer_ticket(ticket)
        self.assertAlmostEqual(row['expires_at'] - row['created_at'], 300)
        self.assertIsNone(m.consume_senplayer_ticket(ticket))

    def test_invalid_positions_rejected_and_zero_allowed(self):
        for raw in (None, '', '-1', 'bad', 'nan', 'inf', '1e99'):
            with self.subTest(raw=raw), self.assertRaises(HTTPException):
                m.callback_position({} if raw is None else {'position':raw})
        self.assertEqual(m.callback_position({'position':'0'}), 0)
        self.assertEqual(m.callback_position({'time':'15.8'}), 15)

    async def test_disabled_callbacks_do_not_write(self):
        request = Request({'type':'http', 'query_string':b'position=12'})
        with patch.object(m, '_update_emby_resume', AsyncMock()) as update:
            response = await m.senplayer_user_callback(1, '42', 100, m._binding_play_sig(self.server,'42',100), request)
            self.assertEqual(response.status_code, 204)
            response = await m.senplayer_callback(1, '42', m._senplayer_signature(self.server,'42'), request)
            self.assertEqual(response.status_code, 204)
            update.assert_not_awaited()

    async def test_invalid_callback_does_not_write(self):
        self.sql('UPDATE servers SET senplayer_progress_sync=1')
        request = Request({'type':'http', 'query_string':b'position=nan'})
        with patch.object(m, '_update_emby_resume', AsyncMock()) as update:
            with self.assertRaises(HTTPException):
                await m.senplayer_user_callback(1, '42', 100, m._binding_play_sig(self.server,'42',100), request)
            update.assert_not_awaited()

    async def test_admin_sees_only_own_server(self):
        self.sql("INSERT INTO servers(id,name,webhook_token,tg_binding_enabled,tg_binding_bot_token,tg_binding_admin_ids) VALUES(2,'Secret Server','secret2',1,'test-bot','200')")
        self.sql("INSERT INTO tg_bindings(server_id,tg_user_id,emby_user_id,emby_username) VALUES(2,200,'user-2','hidden-user')")
        with patch.object(m, 'bot_send', AsyncMock()) as send:
            await m.process_bot_message('test-bot', {'id':9}, {'chat':{'type':'private','id':100},'from':{'id':100},'text':'/bindings'})
        output = send.await_args.args[2]
        self.assertIn('alice', output)
        self.assertNotIn('hidden-user', output)


if __name__ == '__main__':
    unittest.main()
