import base64
import io
import time
import unittest
import zipfile
from unittest.mock import AsyncMock, patch
import httpx
import test_regressions as baseline

m = baseline.m


class PotPlayerTests(unittest.IsolatedAsyncioTestCase):
    sql = baseline.RegressionTests.sql

    def setUp(self):
        baseline.RegressionTests.setUp(self)
        live = patch.object(m, 'emby_get', AsyncMock(return_value={'Id':'user-1','Name':'alice','Policy':{}}))
        live.start()
        self.addCleanup(live.stop)

    def callback(self, user=100):
        return {'id':'q', 'from':{'id':user},
                'data':f"pp:1:42:{m._binding_callback_sig(self.server, '42')}"}

    async def test_private_button_and_cleanup(self):
        with patch.object(m, 'bot_send', AsyncMock(return_value={'message_id':55})) as send, patch.object(m, 'bot_answer_callback', AsyncMock()):
            await m.process_bot_callback('test-bot', {'id':9}, self.callback())
        args = send.await_args.args
        self.assertEqual(args[1], 100)
        button = args[3]['inline_keyboard'][0][0]
        self.assertEqual(button['text'], '▶️ 打开 PotPlayer')
        self.assertTrue(button['url'].startswith('https://notifier.invalid/ps/'))
        download = args[3]['inline_keyboard'][1][0]
        self.assertIn('首次加载 PotPlayer 插件', download['text'])
        self.assertEqual(download['url'], 'https://notifier.invalid/downloads/potplayer-browser-launcher.zip')
        self.assertIn('方法1：浏览器跳转，不常驻', args[2])
        self.assertNotIn('test-key', str(args))
        self.assertNotIn('emby.invalid', str(args))
        row = self.sql('SELECT * FROM senplayer_tickets')[0]
        self.assertEqual(row['player'], 'pp')
        self.assertAlmostEqual(row['expires_at'] - time.time(), 300, delta=3)
        self.assertAlmostEqual(self.sql('SELECT * FROM tg_cleanup_jobs')[0]['due_at'] - time.time(), 10, delta=3)

    async def test_unbound_wrong_bot_disabled_and_bad_signature(self):
        for mode in ('unbound', 'wrong_bot', 'bad_signature', 'disabled'):
            q = self.callback(user=101 if mode == 'unbound' else 100)
            if mode == 'bad_signature':
                q['data'] = 'pp:1:42:0000000000'
            if mode == 'disabled':
                self.sql('UPDATE servers SET tg_binding_enabled=0')
            with patch.object(m, 'bot_send', AsyncMock()) as send, patch.object(m, 'bot_answer_callback', AsyncMock()):
                await m.process_bot_callback('wrong' if mode == 'wrong_bot' else 'test-bot', {'id':9}, q)
            send.assert_not_awaited()
        self.assertEqual(self.sql('SELECT * FROM senplayer_tickets'), [])

    async def test_launch_exact_url_no_progress_and_single_use(self):
        self.sql('UPDATE servers SET senplayer_progress_sync=1')
        ticket = m.create_senplayer_ticket(1, '42', 100, player='pp')
        m.attach_senplayer_ticket_message(ticket, 100, 55)
        with patch.object(m, '_senplayer_resume_seconds', AsyncMock()) as resume, patch.object(m, 'bot_api', AsyncMock()) as api:
            response = await m.potplayer_ticket_open(ticket)
        resume.assert_not_awaited()
        api.assert_not_awaited()
        self.assertEqual(response.status_code, 302)
        link = response.headers['location']
        self.assertTrue(link.startswith('hdz-potplayer://play/'))
        payload = link.split('/play/')[1]
        url = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)).decode()
        self.assertEqual(url, 'https://emby.invalid/emby/Videos/42/stream?Static=true&api_key=test-key')
        self.assertNotIn('x-success', url)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertLessEqual(self.sql('SELECT * FROM tg_cleanup_jobs')[0]['due_at'], time.time())
        self.assertEqual((await m.potplayer_ticket_open(ticket)).status_code, 403)

    async def test_ticket_cannot_switch_player(self):
        pp = m.create_senplayer_ticket(1, '42', 100, player='pp')
        self.assertEqual((await m.senplayer_ticket_open(pp)).status_code, 403)
        self.assertEqual((await m.potplayer_ticket_open(pp)).status_code, 302)
        sp = m.create_senplayer_ticket(1, '42', 100)
        self.assertEqual((await m.potplayer_ticket_open(sp)).status_code, 403)
        self.assertIsNotNone(m.consume_senplayer_ticket(sp))

    async def test_expiry_and_revoked_binding(self):
        ticket = m.create_senplayer_ticket(1, '42', 100, ttl=-1, player='pp')
        self.assertEqual((await m.potplayer_ticket_open(ticket)).status_code, 403)
        ticket = m.create_senplayer_ticket(1, '42', 100, player='pp')
        self.sql('DELETE FROM tg_bindings')
        self.assertEqual((await m.potplayer_ticket_open(ticket)).status_code, 403)

    def test_channel_button_is_callback_only(self):
        with patch.object(m, 'is_jav_item', return_value=True):
            keyboard = m.senplayer_button(self.server, {'Id':'42', 'Type':'Movie'})
            button = keyboard['inline_keyboard'][0][1]
            self.assertTrue(button['callback_data'].startswith('pp:1:42:'))
            self.assertNotIn('url', button)
            self.assertLessEqual(len(button['callback_data'].encode()), 64)
            self.assertIsNone(m.senplayer_button(self.server, {'Id':'42', 'Type':'Episode'}))
            self.server['tg_binding_enabled'] = 0
            self.assertNotIn('PotPlayer', str(m.senplayer_button(self.server, {'Id':'42', 'Type':'Movie'})))

    def test_upgrade_old_ticket_default(self):
        # Recreate the pre-v15.6 table, including an outstanding SenPlayer ticket.
        self.sql('DROP TABLE senplayer_tickets')
        self.sql('''CREATE TABLE senplayer_tickets(token TEXT PRIMARY KEY, server_id INTEGER,
            item_id TEXT, tg_user_id INTEGER, expires_at REAL, used_at REAL, created_at REAL,
            tg_chat_id TEXT DEFAULT '', tg_message_id INTEGER DEFAULT 0)''')
        self.sql('INSERT INTO senplayer_tickets(token,server_id,item_id,tg_user_id,expires_at,used_at,created_at) VALUES(?,?,?,?,?,0,?)',
                 ('old', 1, '42', 100, time.time()+300, time.time()))
        m.init_db()
        self.assertEqual(m.consume_senplayer_ticket('old')['player'], 'sp')
        self.assertEqual(m.get_tg_binding(1, 100)['emby_username'], 'alice')

    async def test_http_potplayer_route(self):
        ticket = m.create_senplayer_ticket(1, '42', 100, player='pp')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app), base_url='http://test') as client:
            self.assertEqual((await client.get('/pp/' + ticket)).status_code, 302)
            self.assertEqual((await client.get('/pp/' + ticket)).status_code, 403)

    async def test_download_is_standalone_archive_without_credentials(self):
        ticket = m.create_senplayer_ticket(1, '42', 100, player='pp')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app), base_url='http://test') as client:
            response = await client.get('/downloads/potplayer-browser-launcher.zip')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'application/zip')
            self.assertIn('attachment;', response.headers['content-disposition'])
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                self.assertEqual({name.split('/')[0] for name in archive.namelist()}, {'方法1.浏览器打开不常驻','方法2.安装后台常驻软件'})
                for folder in ('方法1.浏览器打开不常驻','方法2.安装后台常驻软件'):
                    self.assertIn(folder+'/Uninstall.cmd', archive.namelist())
                    self.assertIn('JAV频道点播', archive.read(folder+'/运行Install.cmd安装.txt').decode('utf-8'))
                for name in archive.namelist():
                    content = archive.read(name)
                    self.assertNotIn(b'test-key', content)
                    self.assertNotIn(b'test-bot', content)
            self.assertEqual((await client.get('/downloads/potplayer-browser-launcher.zip')).status_code, 200)
        self.assertIsNotNone(m.consume_senplayer_ticket(ticket, 'pp'))

    async def test_senplayer_does_not_get_installer_button(self):
        q = self.callback()
        q['data'] = q['data'].replace('pp:', 'sp:', 1)
        with patch.object(m, 'bot_send', AsyncMock(return_value={'message_id':55})) as send, patch.object(m, 'bot_answer_callback', AsyncMock()):
            await m.process_bot_callback('test-bot', {'id':9}, q)
        self.assertEqual(len(send.await_args.args[3]['inline_keyboard']), 1)
        self.assertNotIn('Install.cmd', send.await_args.args[2])


if __name__ == '__main__':
    unittest.main()
