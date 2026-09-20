from html.parser import HTMLParser
from urllib.parse import parse_qs
from unittest.mock import AsyncMock, patch
import unittest
import httpx
import test_regressions as baseline

m = baseline.m


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input' and a.get('form') == 'serverSettings':
            self.fields[a['name']] = a


def context(server):
    return dict(server=server, servers=[server], settings=dict(m.get_settings()),
                libraries=[{'id':'42','name':'电影'}, {'id':'43','name':'电视剧'}, {'id':'44','name':'JAV'}],
                routes=[], local_emby_containers=[{'name':'emby','can_use_container_name':False}],
                webhook_status=None, webhook_url='https://notify.example/webhook/test',
                webhook_local_url='http://emby-tg-notifier:8787/webhook/test',
                detected_public_base='https://notify.example', msg='')


class ConsoleTests(unittest.IsolatedAsyncioTestCase):
    sql = baseline.RegressionTests.sql
    def setUp(self):
        baseline.RegressionTests.setUp(self)
        m._bot_identity_cache.clear()

    async def test_footer_correct_bot_name_server_and_cache(self):
        with patch.object(m,'bot_api',AsyncMock(return_value={'username':'TestBindingBot','first_name':'测试 & 绑定'})) as api:
            footer=await m.notification_binding_footer(self.server)
            self.assertIn('https://t.me/TestBindingBot?start=bind_1',footer)
            self.assertIn('测试 &amp; 绑定',footer)
            self.assertNotIn('test-bot',footer)
            self.assertEqual(footer,await m.notification_binding_footer(self.server))
            api.assert_awaited_once_with('test-bot','getMe')
            other={**self.server,'tg_binding_bot_token':'other-token','id':2}
            self.assertIn('bind_2',await m.notification_binding_footer(other))
            self.assertEqual(api.await_count,2)

    async def test_footer_disabled_invalid_and_failure(self):
        with patch.object(m,'bot_api',AsyncMock(side_effect=RuntimeError('offline'))) as api:
            self.assertEqual('',await m.notification_binding_footer({**self.server,'tg_binding_enabled':0}))
            api.assert_not_awaited()
            self.assertEqual('',await m.notification_binding_footer(self.server))
            self.assertEqual('',await m.notification_binding_footer(self.server))
            self.assertEqual(api.await_count,1)
        m._bot_identity_cache.clear()
        with patch.object(m,'bot_api',AsyncMock(return_value={'username':'invalid/evil'})):
            self.assertEqual('',await m.notification_binding_footer(self.server))

    async def test_all_server_fields_and_save_roundtrip(self):
        markup=m.templates.get_template('console.html').render(**context(self.server))
        p=Inputs();p.feed(markup)
        expected={'name','emby_url','emby_api_key','bot_token_override','send_test_to_telegram',
                  'senplayer_emby_url','notifier_public_url','senplayer_user','tv_batch_minutes',
                  'tg_binding_enabled','tg_binding_bot_id','tg_binding_bot_token',
                  'tg_binding_admin_ids','senplayer_progress_sync'}
        self.assertEqual(set(p.fields),expected)
        self.assertEqual(p.fields['emby_api_key']['type'],'password')
        values={name:a.get('value','') for name,a in p.fields.items() if a.get('type')!='checkbox' or 'checked' in a}
        values['tv_batch_minutes']='17'
        with patch.object(m,'require_login'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app),base_url='http://test') as client:
                response=await client.post('/servers/1/save',data=values,headers={'X-Requested-With':'fetch'})
        self.assertEqual(response.status_code,200)
        saved=dict(m.get_server(1))
        self.assertEqual(saved['tv_batch_minutes'],17)
        for name in ('emby_api_key','tg_binding_bot_token','tg_binding_admin_ids'):
            self.assertEqual(saved[name],self.server[name])

    async def test_binding_footer_is_jav_only(self):
        movie={'Id':'42','Name':'Movie','Type':'Movie'}
        jav={'Id':'43','Name':'ABP-123','Type':'Movie','Path':'/home/symedia_jav/h2606/actor/ABP-123/ABP-123.strm'}
        sent=[]
        def handle(request):
            sent.append(parse_qs(request.content.decode()))
            return httpx.Response(200,json={'ok':True,'result':{'message_id':1}})
        for kind,item in (('movie',movie),('batch',movie),('jav',jav)):
            client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
            with patch.object(m,'bot_api',AsyncMock(return_value={'username':'CorrectBot','first_name':'正确机器人'})), \
                 patch.object(m,'download_poster',AsyncMock(return_value=None)), \
                 patch.object(m,'enrich_item_for_notification',AsyncMock(return_value=item)), \
                 patch.object(m.httpx,'AsyncClient',return_value=client):
                if kind == 'batch':
                    await m.tg_send_tv_batch(self.server,'channel','Series',1,{'1':{}},item)
                else:
                    await m.tg_send(self.server,'channel',item)
        for index,payload in enumerate(sent):
            if index == 2:
                self.assertIn('https://t.me/CorrectBot?start=bind_1',payload['text'][0])
                self.assertTrue(payload['text'][0].endswith('正确机器人</a>'))
            else:
                self.assertNotIn('绑定 Emby',payload['text'][0])
            self.assertEqual(payload['disable_web_page_preview'],['true'])
