# -*- coding: utf-8 -*-
"""地域分类口径单元测试（region_group 互斥 + territory 受控解析）。"""
import unittest
from etl.geo_taxonomy import resolve_region, resolve_territory


class TestResolveRegion(unittest.TestCase):
    def test_canonical_region(self):
        self.assertEqual(resolve_region("全球 Global"), ("Global", "Global"))
        self.assertEqual(resolve_region("美国+加拿大 US & Canada"), ("US & Canada", "North America"))
        self.assertEqual(resolve_region("日本 Japan"), ("Japan", "APAC"))
        self.assertEqual(resolve_region("韩国 Korea"), ("South Korea", "APAC"))
        self.assertEqual(resolve_region("中国境内权益 China Mainland Rights"), ("China Mainland", "Greater China"))

    def test_unknown_region_falls_to_other(self):
        self.assertEqual(resolve_region("不存在的区域 XYZ"), ("Other", "Other"))


class TestResolveTerritory(unittest.TestCase):
    def test_composite_region_priority_no_double_count(self):
        # 组合区域应优先于单国，且只返回单一桶
        self.assertEqual(resolve_territory("United States and Canada (Coherus Territory)")[0], "US & Canada")
        self.assertEqual(resolve_territory("Global excluding Greater China")[0], "Global ex-Greater China")

    def test_single_country(self):
        self.assertEqual(resolve_territory("美国 United States")[0], "United States")
        self.assertEqual(resolve_territory("日本 Japan")[0], "Japan")
        self.assertEqual(resolve_territory("巴西 Brazil")[0], "Brazil")

    def test_unresolved_goes_review(self):
        geo, group, status = resolve_territory("一些完全无法识别的区域文本")
        self.assertEqual(geo, "Other")
        self.assertEqual(group, "Other")
        self.assertEqual(status, "review")

    def test_empty_territory_goes_review(self):
        geo, group, status = resolve_territory("")
        self.assertEqual(geo, "Other")
        self.assertEqual(group, "Other")
        self.assertEqual(status, "review")


if __name__ == "__main__":
    unittest.main()
