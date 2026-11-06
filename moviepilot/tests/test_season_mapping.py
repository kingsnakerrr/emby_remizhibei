import ast
import pathlib
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

class Base:
    def get_data(self, key): return self.data.get(key)
    def save_data(self, key, value): self.data[key] = value

path = pathlib.Path(__file__).parents[1] / 'plugins/tvseasonrepair/__init__.py'
tree = ast.parse(path.read_text(encoding='utf-8'))
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
scope = dict(globals(), _PluginBase=Base, Body=lambda **kw: None,
             logger=type('Logger', (), {'warning': print, 'error': print})())
exec(compile(tree, str(path), 'exec'), scope)

class MappingTests(unittest.TestCase):
    def setUp(self):
        self.p = scope['TVSeasonRepair']()
        self.p.data = {}
        self.p._official_counts = lambda ident: [35, 43, 38] if ident == 19389 else [8]
        self.row = dict(tmdb_id=291141, name='Vampire III', series_rel='test',
                        seasons=[dict(season=1, min=1, max=38, count=38, contiguous_from_one=True)])
        self.p._post = lambda *args: {'series': [dict(self.row)]}

    def test_mapping_and_stale_plan_invalidation(self):
        self.p.data['scan_results'] = [dict(self.row, safe=True)]
        result = self.p.save_season_override(dict(tmdb_id=291141, target_tmdb_id=19389, target_season=3))
        self.assertTrue(result['success'])
        self.assertEqual(self.p.data['scan_results'], [])
        self.assertTrue(self.p.scan({})['success'])
        self.assertEqual(self.p.data['scan_results'], [])

    def test_mapping_failure_never_uses_snapshot(self):
        self.p.save_season_override(dict(tmdb_id=291141, target_tmdb_id=19389, target_season=3))
        self.p._official_counts = lambda ident: []
        self.assertTrue(self.p.scan({})['success'])
        self.assertFalse(self.p.data['scan_results'][0]['safe'])

    def test_bad_input(self):
        self.assertFalse(self.p.save_season_override({'tmdb_id': 'oops'})['success'])

    def test_legacy_cache_refreshes(self):
        self.p.data['tmdb_season_counts'] = {'291141': [2]}
        self.p.scan({})
        self.assertEqual(self.p.data['tmdb_season_counts']['291141'], [8])

if __name__ == '__main__': unittest.main()
