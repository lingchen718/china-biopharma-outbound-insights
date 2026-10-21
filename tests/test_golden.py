# -*- coding: utf-8 -*-
"""口径回归 golden fixtures：用固定小数据集锁定聚合口径，防止口径漂移。"""
import os
import tempfile
import unittest

import api.server as server


SCHEMA = """
CREATE TABLE deals (
  deal_id TEXT PRIMARY KEY,
  date TEXT, year INTEGER,
  licensor TEXT, licensee TEXT, asset TEXT, target TEXT,
  modality TEXT, indication TEXT, stage TEXT, deal_type TEXT,
  region TEXT, territory TEXT, region_group TEXT, geo_territory TEXT, geo_region_group TEXT, geo_status TEXT,
  confidence TEXT, currency TEXT, fx_rate REAL,
  upfront REAL, total_value REAL,
  upfront_musd REAL, total_value_musd REAL, milestone_musd REAL,
  milestone_derivable INTEGER, has_upfront INTEGER, has_total INTEGER,
  value_disclosure TEXT, source_name TEXT, source_title TEXT,
  source_url TEXT, publish_date TEXT, analyst_note TEXT
)
"""

ROWS = [
    ("D1", "2022-01-15", 2022, "LicA", "Lic1", "AssetA", "T1", "ADC", "Oncology", "Phase II", "License-out", "Global", "United States",
     "Global", "Global", "Global", "resolved", 100.0, 400.0, 300.0, 1, 1, 1),
    ("D2", "2022-06-20", 2022, "LicB", "Lic2", "AssetB", "T1", "ADC", "Oncology", "Phase I", "License-out", "North America", "United States",
     "North America", "United States", "North America", "resolved", 50.0, 200.0, 150.0, 1, 1, 1),
    ("D3", "2023-03-01", 2023, "LicC", "Lic3", "AssetC", "T2", "mAb", "Autoimmune", "Phase I", "License-out", "Europe", "Germany",
     "Europe", "Europe", "Europe", "resolved", None, None, None, 0, 0, 0),
    ("D4", "2023-09-10", 2023, "LicA", "Lic4", "AssetD", "T2", "mAb", "Autoimmune", "Phase II", "License-out", "Europe", "United Kingdom",
     "Europe", "Europe", "Europe", "resolved", 30.0, 90.0, 60.0, 1, 1, 1),
]

INSERT = (
    "INSERT INTO deals (deal_id,date,year,licensor,licensee,asset,target,modality,indication,stage,deal_type,region,territory,"
    "region_group,geo_territory,geo_region_group,geo_status,"
    "upfront_musd,total_value_musd,milestone_musd,milestone_derivable,has_upfront,has_total) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)


class GoldenCaliber(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig = server.DB_PATH
        cls.tmp = tempfile.mkdtemp(prefix="golden-")
        server.DB_PATH = os.path.join(cls.tmp, "golden")
        server._CACHE.clear()
        conn = server.connect()
        conn.executescript(SCHEMA)
        conn.executemany(INSERT, ROWS)
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_PATH = cls._orig
        server._CACHE.clear()

    def test_overview_kpis(self):
        k = server.ep_overview_kpis({})
        self.assertEqual(k["total_deals"], 4)
        self.assertEqual(k["total_value"], 690.0)
        self.assertEqual(k["highest_deal"], 400.0)
        self.assertEqual(k["total_upfront"], 180.0)
        self.assertEqual(k["licensors"], 3)
        self.assertEqual(k["licensees"], 4)

    def test_economics_snapshot(self):
        s = server.ep_economics_snapshot({})
        self.assertEqual(s["upfront_deals"], 3)
        self.assertEqual(s["total_deals_count"], 3)
        self.assertEqual(s["total_rows"], 4)
        self.assertEqual(s["total_upfront"], 180.0)
        self.assertEqual(s["median_upfront"], 50.0)
        self.assertEqual(s["total_value"], 690.0)

    def test_economics_trends_yoy(self):
        d = server.ep_economics_trends({"granularity": ["year"]})
        rows = {r["period"]: r for r in d["rows"]}
        self.assertEqual(rows["2022"]["deals"], 2)
        self.assertEqual(rows["2022"]["upfront"], 150.0)
        self.assertEqual(rows["2022"]["total_value"], 600.0)
        self.assertIsNone(rows["2022"]["count_yoy"])
        self.assertEqual(rows["2023"]["count_yoy"], 0.0)
        self.assertEqual(rows["2023"]["upfront_yoy"], -80.0)
        self.assertEqual(rows["2023"]["total_yoy"], -85.0)

    def test_economics_distribution(self):
        d = server.ep_economics_distribution({})
        by = {b["modality"]: b for b in d["boxplot"]}
        self.assertEqual(by["ADC"]["n"], 2)
        self.assertEqual(by["ADC"]["q"], [200.0, 250.0, 300.0, 350.0, 400.0])
        self.assertEqual(by["mAb"]["n"], 1)
        self.assertEqual(by["mAb"]["q"], [90.0, 90.0, 90.0, 90.0, 90.0])

    def test_economics_milestones(self):
        m = server.ep_economics_milestones({})
        self.assertEqual([x["id"] for x in m["milestones"]], ["D1", "D2", "D4"])
        self.assertEqual(m["milestones"][0]["milestone_musd"], 300.0)
        self.assertEqual(m["not_derivable"], 0)

    def test_landscape_coverage(self):
        d = server.ep_landscape({}, "modality")
        self.assertEqual(d["total"], 4)
        self.assertEqual(d["coverage"], 75)
        counts = {c["key"]: c["value"] for c in d["counts"]}
        self.assertEqual(counts["ADC"], 2)
        self.assertEqual(counts["mAb"], 2)

    def test_deals_amount_filters(self):
        self.assertEqual(server.ep_deals({"upfront_min": ["60"]})["total"], 1)
        self.assertEqual(server.ep_deals({"total_max": ["250"]})["total"], 2)
        self.assertEqual(server.ep_deals({"upfront_min": ["60"], "total_max": ["250"]})["total"], 0)

    def test_deals_date_filters(self):
        self.assertEqual(server.ep_deals({"date_from": ["2023-01-01"]})["total"], 2)
        self.assertEqual(server.ep_deals({"date_to": ["2022-12-31"]})["total"], 2)

    def test_deals_milestone_filter(self):
        self.assertEqual(server.ep_deals({"milestone": ["derivable"]})["total"], 3)
        self.assertEqual(server.ep_deals({"milestone": ["not_derivable"]})["total"], 1)

    def test_deals_export_csv(self):
        csv_text = server.ep_deals_csv({})
        self.assertTrue(csv_text.startswith("\ufeff交易ID"))
        self.assertEqual(len(csv_text.strip().splitlines()), 5)  # 表头 + 4 行
        filtered = server.ep_deals_csv({"milestone": ["not_derivable"]})
        self.assertEqual(len(filtered.strip().splitlines()), 2)  # 表头 + D3


if __name__ == "__main__":
    unittest.main()
