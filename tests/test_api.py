# -*- coding: utf-8 -*-
"""聚合接口的单元测试（依赖已落库的本地数据）。"""
import unittest
from api.server import ensure_db, ep_overview_kpis, ep_landscape, ep_economics_trends, \
    ep_economics_distribution, ep_pipeline_aggregates, ep_therapy_opportunity, ep_geo, ep_meta, ep_deals

ensure_db()

class TestAggregates(unittest.TestCase):
    def test_overview_kpis(self):
        k = ep_overview_kpis({})
        self.assertGreater(k['total_deals'], 0)
        self.assertIn('total_value', k)
        self.assertIn('licensors', k)

    def test_landscape_consistent_total(self):
        d = ep_landscape({}, 'stage')
        self.assertEqual(d['total'], ep_overview_kpis({})['total_deals'])
        self.assertGreater(len(d['counts']), 0)
        self.assertGreaterEqual(d['coverage'], 0)

    def test_economics_trends_yoy(self):
        d = ep_economics_trends({'granularity': ['year']})
        self.assertEqual(d['granularity'], 'year')
        self.assertIsNone(d['rows'][0]['count_yoy'])  # 首年无上年同期 → N/A

    def test_distribution_has_n_and_five_number(self):
        d = ep_economics_distribution({})
        for b in d['boxplot']:
            self.assertIn('n', b)
            self.assertEqual(len(b['q']), 5)

    def test_pipeline_aggregates(self):
        d = ep_pipeline_aggregates({})
        self.assertGreater(len(d['md_list']), 0)
        self.assertGreater(len(d['trend']), 0)
        self.assertGreater(len(d['stagebox']), 0)

    def test_therapy_opportunity(self):
        d = ep_therapy_opportunity({})
        self.assertGreater(len(d['rows']), 0)

    def test_geo_top8(self):
        d = ep_geo({})
        self.assertLessEqual(len(d), 8)

    def test_deals_returns_id_and_total(self):
        d = ep_deals({"limit": ["1"]})
        self.assertTrue(d["deals"][0]["id"])
        self.assertIn("total", d)

    def test_meta_enums(self):
        d = ep_meta()
        self.assertIn('modality', d['enums'])
        self.assertIn('region', d['enums'])

if __name__ == '__main__':
    unittest.main()
