import unittest
from unittest.mock import AsyncMock, patch
import httpx
import test_regressions as baseline

m = baseline.m


class RemoveEmbyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        baseline.RegressionTests.setUp(self)

    def test_no_emby_button(self):
        with patch.object(m, 'is_jav_item', return_value=True):
            keyboard = m.senplayer_button(self.server, {'Id':'42','Type':'Movie'})
        self.assertEqual(len(keyboard['inline_keyboard'][0]), 2)
        self.assertNotIn('Emby', str(keyboard))
        self.assertEqual(keyboard['inline_keyboard'][0][0]['text'], '▶️ SenPlayer 播放')

    async def test_old_callback_only_reports_removed(self):
        with patch.object(m,'bot_answer_callback',AsyncMock()) as answer, patch.object(m,'emby_get',AsyncMock()) as get, patch.object(m,'bot_send',AsyncMock()) as send:
            await m.process_bot_callback('test-bot',{'id':9},{'id':'q','from':{'id':100},'data':'ep:1:42:0000000000'})
        answer.assert_awaited_once()
        get.assert_not_awaited()
        send.assert_not_awaited()

    async def test_old_links_never_launch(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app),base_url='http://test') as client:
            for path in ('/ep/old-ticket','/emby-open/1/42/old-signature'):
                response = await client.get(path)
                self.assertEqual(response.status_code,410)
                self.assertNotIn('location',response.headers)


if __name__ == '__main__':
    unittest.main()
