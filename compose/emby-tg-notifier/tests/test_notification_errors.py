import unittest
from unittest.mock import AsyncMock, patch
import httpx
import test_regressions as baseline

m = baseline.m

class NotificationErrorTests(unittest.IsolatedAsyncioTestCase):
    sql = baseline.RegressionTests.sql
    def setUp(self):
        baseline.RegressionTests.setUp(self)

    async def test_failed_delivery_visible_without_token(self):
        self.sql("INSERT INTO routes(server_id,name,library_id,chat_id,enabled) VALUES(1,'TV','tv','-100',1)")
        request=httpx.Request('POST','https://api.telegram.org/botSECRET/sendMessage')
        response=httpx.Response(400,request=request,json={'description':'Bad Request: chat not found'})
        error=httpx.HTTPStatusError('SECRET',request=request,response=response)
        with patch.object(m,'find_library_id',AsyncMock(return_value='tv')),patch.object(m,'tg_send',AsyncMock(side_effect=error)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app),base_url='http://test') as c:
                r=await c.post('/webhook/emby/1/test-secret',json={'Event':'library.new','Item':{'Id':'42','Name':'Fixture'}})
        self.assertEqual(r.status_code,200)
        detail=self.sql('SELECT detail FROM webhook_status')[0]['detail']
        self.assertIn('Telegram 找不到频道',detail)
        self.assertNotIn('SECRET',detail+r.text)
        self.assertIn('成功发送 0',detail)

    def test_generic_error_does_not_expose_url(self):
        self.assertNotIn('SECRET',m.notification_error_summary(RuntimeError('https://host/SECRET')))
