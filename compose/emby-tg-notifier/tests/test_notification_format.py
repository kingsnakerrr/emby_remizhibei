import unittest
from unittest.mock import AsyncMock, patch
import test_regressions as baseline

m = baseline.m


class NotificationFormatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        baseline.RegressionTests.setUp(self)
        self.server = dict(m.get_server(1))

    def test_cinemascope_1920_by_960_is_1080p(self):
        quality=m.detect_source_quality({}, {},
            {'Width':1920,'Height':960,'Codec':'h264','VideoRange':'SDR'},
            {'Codec':'eac3','Channels':6})
        self.assertEqual(quality,'1080p H264 SDR E-AC-3 5.1')

    def test_movie_caption_layout_genres_overview_and_category(self):
        item={'Name':'怒之杀','ProductionYear':2026,'Type':'Movie',
              'Genres':['动作','惊悚'],'Overview':'\u3000 在目睹亿万富豪蒂布遇害。 ',
              'MediaSources':[{'Size':6806575847,'MediaStreams':[
                  {'Type':'Video','Width':1920,'Height':960,'Codec':'h264','VideoRange':'SDR'},
                  {'Type':'Audio','Codec':'eac3','Channels':6}]}]}
        text=m.format_caption(item)
        expected=['🎬 <b>怒之杀</b> (2026)','🎭 类型：动作、惊悚','📝 简介：在目睹亿万富豪蒂布遇害。',
                  '📥 <b>Emby 新媒体入库</b>','🏷 类别：Movie','🌟 质量：1080p H264 SDR E-AC-3 5.1','💾 大小：6.3G']
        positions=[text.index(line) for line in expected]
        self.assertEqual(positions,sorted(positions))
        self.assertNotIn('🏷 类型：',text)

    def test_tv_batch_uses_type_overview_and_category(self):
        item={'Type':'Episode','SeriesName':'剧集','SeriesProductionYear':2024,
              'NotificationGenres':['剧情','动作'],'NotificationOverview':'季度简介'}
        text=m.format_tv_batch_caption('剧集',2,{'1':{},'2':{}},item)
        for value in ('🎭 类型：剧情、动作','📝 简介：季度简介','🏷 类别：TVshow'):
            self.assertIn(value,text)
        self.assertNotIn('绑定 Emby',text)

    async def test_episode_description_prefers_season_then_series(self):
        full={'Id':'42','Type':'Episode','Name':'第一集','ParentId':'season-2','SeriesId':'series-1',
              'Overview':'单集简介','Genres':['单集类型'],
              'MediaSources':[{'Size':1,'MediaStreams':[{'Type':'Video','Width':1920,'Height':1080}]}]}
        async def get(_server,path):
            if '/season-2?' in path:return {'Overview':'季度简介','Genres':['季度类型']}
            if '/series-1?' in path:return {'Overview':'总简介','Genres':['总类型']}
            raise AssertionError(path)
        with patch.object(m,'_get_user_item_details',AsyncMock(return_value=('user-1',full))),patch.object(m,'emby_get',side_effect=get):
            item=await m.enrich_item_for_notification(self.server,{'Id':'42','Type':'Episode'})
        self.assertEqual(item['NotificationOverview'],'季度简介')
        self.assertEqual(item['NotificationGenres'],['季度类型'])

        async def fallback(_server,path):
            if '/season-2?' in path:return {'Overview':'','Genres':[]}
            if '/series-1?' in path:return {'Overview':'总简介','Genres':['总类型']}
            raise AssertionError(path)
        with patch.object(m,'_get_user_item_details',AsyncMock(return_value=('user-1',full))),patch.object(m,'emby_get',side_effect=fallback):
            item=await m.enrich_item_for_notification(self.server,{'Id':'42','Type':'Episode'})
        self.assertEqual(item['NotificationOverview'],'总简介')
        self.assertEqual(item['NotificationGenres'],['总类型'])


if __name__ == '__main__':
    unittest.main()
