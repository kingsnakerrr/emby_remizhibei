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

    async def test_offline_never_falls_back_to_browser(self):
        with patch.object(m.pot_sync, 'dispatch', return_value='offline'), patch.object(m, 'bot_send', AsyncMock()) as send, patch.object(m, 'bot_answer_callback', AsyncMock()) as answer:
            await m.process_bot_callback('test-bot', {'id':9}, self.callback())
        send.assert_not_awaited()
        self.assertIn('不再使用 Chrome', answer.await_args.args[2])
        self.assertEqual(self.sql('SELECT * FROM senplayer_tickets'), [])

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

    async def test_retired_browser_route_is_gone_and_does_not_consume_ticket(self):
        ticket = m.create_senplayer_ticket(1, '42', 100, player='pp')
        with self.assertRaises(m.HTTPException) as error:
            await m.potplayer_ticket_open(ticket)
        self.assertEqual(error.exception.status_code, 410)
        self.assertIsNotNone(m.consume_senplayer_ticket(ticket, 'pp'))

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
            self.assertEqual((await client.get('/pp/' + ticket)).status_code, 410)
            self.assertIsNotNone(m.consume_senplayer_ticket(ticket, 'pp'))

    async def test_download_is_standalone_archive_without_credentials(self):
        ticket = m.create_senplayer_ticket(1, '42', 100, player='pp')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app), base_url='http://test') as client:
            response = await client.get('/downloads/potplayer-browser-launcher.zip')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'application/zip')
            self.assertIn('attachment;', response.headers['content-disposition'])
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                self.assertIn('Install.cmd', archive.namelist())
                self.assertIn('Supervisor.ps1', archive.namelist())
                self.assertIn('Launcher.vbs', archive.namelist())
                self.assertNotIn('Bridge.ps1', archive.namelist())
                self.assertIn('JAV频道点播', archive.read('运行Install.cmd安装.txt').decode('utf-8'))
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
