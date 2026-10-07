import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch
import httpx
import test_regressions as baseline

m = baseline.m


class SyncTests(unittest.IsolatedAsyncioTestCase):
    sql = baseline.RegressionTests.sql

    def setUp(self):
        baseline.RegressionTests.setUp(self)
        self.sync = m.pot_sync
        self.get = AsyncMock(side_effect=self.emby_get)
        self.p = patch.object(m, 'emby_get', self.get)
        self.p.start()
        self.addCleanup(self.p.stop)
        self.write = AsyncMock()
        self.pw = patch.object(self.sync, 'write_progress', self.write)
        self.pw.start()
        self.addCleanup(self.pw.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def emby_get(self, server, path):
        if '/Items/' in path:
            return {'Id':'42','RunTimeTicks':1000*10000000,'UserData':{'PlaybackPositionTicks':100*10000000,'PlayCount':3}}
        return {'Id':path.split('/')[-1], 'Name':'alice', 'Policy':{'IsDisabled':False}}

    async def grant(self, ticket=None, headers=None):
        ticket = ticket or m.create_senplayer_ticket(1,'42',100,player='pp')
        r = await self.client.post('/potplayer/claim/'+ticket, headers=headers or {})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    async def report(self, token, seq=1, pos=101, event='progress', duration=1000):
        return await self.client.post('/potplayer/report',headers={'Authorization':'Bearer '+token},
                                      json={'seq':seq,'position':pos,'duration':duration,'event':event})

    async def pair(self):
        send = AsyncMock(return_value={'message_id':55})
        with patch.object(m,'bot_send',send):
            await self.sync.bot_command('test-bot',{'from':{'id':100},'message_id':2,'text':'/pc'},'/pc')
        link = send.await_args.args[2].split('<code>')[1].split('</code>')[0]
        r = await self.client.post(link.replace('https://notifier.invalid',''))
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['token'], link

    async def test_browser_dispatch_route_is_not_registered(self):
        ticket=m.create_senplayer_ticket(1,'42',100,player='pp')
        self.assertEqual((await self.client.get('/ps/'+ticket)).status_code,404)
        g=await self.grant(ticket)
        self.assertEqual(g['resume'],100)
        self.write.assert_not_awaited()

    async def test_progress_stop_idempotence_and_finish(self):
        g=await self.grant()
        self.assertEqual((await self.report(g['token'])).status_code,200)
        self.assertEqual((await self.report(g['token'])).status_code,200)
        self.assertEqual(self.write.await_count,1)
        r=await self.report(g['token'],2,990,'stop')
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['finished'])
        self.assertTrue(self.write.await_args.args[3])
        self.assertEqual((await self.report(g['token'],3,995)).status_code,409)
        self.assertEqual(self.write.await_count,2)

    async def test_rewind_is_real_position_not_elapsed_time(self):
        g=await self.grant()
        await self.report(g['token'],1,400)
        await self.report(g['token'],2,20)
        self.assertEqual(self.write.await_args.args[2],20)

    async def test_failed_open_does_not_write_or_increment(self):
        g=await self.grant()
        self.assertEqual((await self.report(g['token'],pos=0)).status_code,400)
        self.write.assert_not_awaited()
        self.assertEqual(self.sync.query('SELECT started FROM pp_sessions')[0]['started'],0)

    async def test_errors_keep_sequence_retryable(self):
        g=await self.grant()
        self.write.side_effect=RuntimeError('network failure')
        self.assertEqual((await self.report(g['token'])).status_code,502)
        self.assertEqual(self.sync.query('SELECT seq FROM pp_sessions')[0]['seq'],0)
        self.write.side_effect=None
        self.assertEqual((await self.report(g['token'])).status_code,200)

    async def test_report_bounds_and_auth(self):
        g=await self.grant()
        for pos,duration in ((-1,1000),(2000,1000),(1,0),(True,1000),(1,1300000)):
            self.assertEqual((await self.report(g['token'],pos=pos,duration=duration)).status_code,400)
        self.assertEqual((await self.report('wrong')).status_code,401)
        self.sync.query('UPDATE pp_sessions SET expires_at=0')
        self.assertEqual((await self.report(g['token'])).status_code,401)
        self.write.assert_not_awaited()

    async def test_live_user_disabled_or_deleted(self):
        g=await self.grant()
        self.get.side_effect=None
        for response in ({'Id':'user-1','Policy':{'IsDisabled':True}},None,{'Id':'user-1','Policy':{'EnableMediaPlayback':False}}):
            self.get.return_value=response
            self.assertEqual((await self.report(g['token'])).status_code,403)
        self.write.assert_not_awaited()

    async def test_binding_change_blocks_old_grant(self):
        g=await self.grant()
        self.sql("UPDATE tg_bindings SET emby_user_id='user-2'")
        self.assertEqual((await self.report(g['token'])).status_code,403)
        self.write.assert_not_awaited()

    async def test_renamed_user_refreshes_name_not_identity(self):
        self.get.side_effect=None
        self.get.return_value={'Id':'user-1','Name':'renamed','Policy':{}}
        _,b=await self.sync.live_scope(1,100)
        self.assertEqual(b['emby_username'],'renamed')
        self.assertEqual(m.get_tg_binding(1,100)['emby_user_id'],'user-1')

    async def test_newer_playback_supersedes_old_progress(self):
        a=await self.grant()
        await self.report(a['token'])
        b=await self.grant()
        await self.report(b['token'])
        self.assertEqual((await self.report(a['token'],2,150)).status_code,409)

    async def test_pair_single_use_and_private_desktop_delivery(self):
        token,link=await self.pair()
        h={'Authorization':'Bearer '+token}
        self.assertEqual((await self.client.post(link.replace('https://notifier.invalid',''))).status_code,403)
        self.assertEqual((await self.client.post('/potplayer/poll',headers=h)).status_code,200)
        self.assertEqual(self.sync.dispatch(self.server,100,'42'),'sent')
        self.assertEqual(self.sync.dispatch(self.server,100,'42'),'busy')
        ticket=(await self.client.post('/potplayer/poll',headers=h)).json()['ticket']
        self.assertTrue(ticket)
        self.assertIsNone((await self.client.post('/potplayer/poll',headers=h)).json()['ticket'])
        self.assertEqual((await self.client.post('/potplayer/claim/'+ticket)).status_code,403)
        g=await self.grant(ticket,h)
        await self.report(g['token'])
        await self.report(g['token'],2,300,'stop')
        self.assertEqual(self.sync.query('SELECT busy_until FROM pp_devices')[0]['busy_until'],0)

    async def test_offline_does_not_queue_and_expired_job_does_not_play(self):
        token,_=await self.pair()
        self.assertEqual(self.sync.dispatch(self.server,100,'42'),'offline')
        self.assertEqual(self.sync.query('SELECT * FROM pp_jobs'),[])
        h={'Authorization':'Bearer '+token}
        await self.client.post('/potplayer/poll',headers=h)
        self.sync.dispatch(self.server,100,'42')
        self.sync.query('UPDATE pp_jobs SET expires_at=0')
        self.assertIsNone((await self.client.post('/potplayer/poll',headers=h)).json()['ticket'])

    async def test_repair_and_uninstall_revoke_old_credentials(self):
        token,_=await self.pair()
        new,_=await self.pair()
        self.assertEqual((await self.client.post('/potplayer/poll',headers={'Authorization':'Bearer '+token})).status_code,401)
        h={'Authorization':'Bearer '+new}
        self.assertEqual((await self.client.post('/potplayer/revoke',headers=h)).status_code,200)
        self.assertEqual((await self.client.post('/potplayer/poll',headers=h)).status_code,401)

    async def test_cannot_pair_another_tg_account(self):
        send=AsyncMock()
        with patch.object(m,'bot_send',send):
            await self.sync.bot_command('test-bot',{'from':{'id':101},'message_id':2,'text':'/pc'},'/pc')
        self.assertEqual(self.sync.query('SELECT * FROM pp_pairs'),[])
        self.assertNotIn('/potplayer/pair/',send.await_args.args[2])

    async def test_channel_callback_with_online_device_never_opens_browser(self):
        token,_=await self.pair()
        await self.client.post('/potplayer/poll',headers={'Authorization':'Bearer '+token})
        q={'id':'q','from':{'id':100},'data':'pp:1:42:'+m._binding_callback_sig(self.server,'42')}
        with patch.object(m,'bot_send',AsyncMock()) as send, patch.object(m,'bot_answer_callback',AsyncMock()) as answer:
            await m.process_bot_callback('test-bot',{'id':9},q)
        send.assert_not_awaited()
        self.assertIn('已发送到配对电脑',answer.await_args.args[2])

    async def test_real_userdata_payload_targets_bound_user(self):
        # Exercise the actual HTTP writer while intercepting the network boundary.
        self.pw.stop()
        g=await self.grant()
        response=httpx.Response(200,request=httpx.Request('POST','https://emby.invalid'))
        mock_client=AsyncMock()
        mock_client.__aenter__.return_value=mock_client
        mock_client.post.return_value=response
        post=mock_client.post
        with patch('app.potplayer_sync.httpx.AsyncClient',return_value=mock_client):
            await self.report(g['token'],pos=123)
            self.assertIn('/Users/user-1/Items/42/UserData',post.await_args.args[0])
            self.assertEqual(post.await_args.kwargs['json']['PlayCount'],4)
            self.assertEqual(post.await_args.kwargs['json']['PlaybackPositionTicks'],1230000000)
            await self.report(g['token'],2,980,'stop')
            self.assertEqual(post.await_args.kwargs['json']['PlayCount'],4)
            self.assertTrue(post.await_args.kwargs['json']['Played'])
            self.assertEqual(post.await_args.kwargs['json']['PlaybackPositionTicks'],0)


if __name__=='__main__':
    unittest.main()
