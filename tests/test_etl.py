# -*- coding: utf-8 -*-
"""ETL 规范化逻辑的单元测试（无需数据库）。"""
import csv
import importlib
import json
import os
import tempfile
import unittest
from unittest import mock

from etl import build_dataset
from etl.build_dataset import norm, fnum, MODALITY, INDICATION, STAGE, DEAL_TYPE, REGION

class TestNorm(unittest.TestCase):
    def test_modality_mapping(self):
        self.assertEqual(norm('modality', MODALITY, 'ADC', set()), 'ADC')
        self.assertEqual(norm('modality', MODALITY, '单抗（非ADC）Monoclonal antibody', set()), 'mAb')
        self.assertEqual(norm('modality', MODALITY, '双抗 Bispecific antibody', set()), 'Bispecific')
        self.assertEqual(norm('modality', MODALITY, 'RNA疗法 (siRNA/mRNA/ASO)', set()), 'RNA therapy')

    def test_stage_empty_and_multi(self):
        self.assertEqual(norm('stage', STAGE, '', set()), 'Unknown')
        self.assertEqual(norm('stage', STAGE, 'I期 Phase I、注册阶段 Registration', set()), 'Multiple Stages')
        self.assertEqual(norm('stage', STAGE, '临床前 Preclinical', set()), 'Preclinical')

    def test_indication_multi_primary(self):
        self.assertEqual(norm('indication', INDICATION, '肿瘤 Oncology、罕见病 Rare disease', set()), 'Oncology')

    def test_deal_type(self):
        self.assertEqual(norm('deal_type', DEAL_TYPE, '并购 Acquisition', set()), 'M&A')
        self.assertEqual(norm('deal_type', DEAL_TYPE, '分销 / 商业化 Distribution / commercialization', set()), 'Distribution')

    def test_region(self):
        self.assertEqual(norm('region', REGION, '韩国 Korea', set()), 'South Korea')
        self.assertEqual(norm('region', REGION, '大中华 Greater China', set()), 'Greater China')

    def test_unmapped_collected(self):
        seen = {'modality': set()}
        norm('modality', MODALITY, '不存在的值 XYZ', seen)
        self.assertIn('不存在的值 XYZ', seen['modality'])

class TestBuildDatasetPaths(unittest.TestCase):
    def test_base_defaults_to_repo_normalized_data(self):
        self.assertTrue(build_dataset.BASE.endswith("normalized_data"))
        self.assertTrue(os.path.isdir(build_dataset.BASE))
        for y in build_dataset.YEARS:
            self.assertTrue(os.path.isfile(os.path.join(build_dataset.BASE, f"cleaned_data_{y}.csv")))

    def test_base_env_override(self):
        tmp = tempfile.mkdtemp(prefix="etl-data-")
        with mock.patch.dict(os.environ, {"ETL_DATA_DIR": tmp}, clear=False):
            importlib.reload(build_dataset)
            self.assertEqual(build_dataset.BASE, tmp)
        importlib.reload(build_dataset)  # 恢复默认路径


class TestBuildDatasetReproducibility(unittest.TestCase):
    def test_source_fingerprint_stable(self):
        f1 = build_dataset._source_fingerprint()
        f2 = build_dataset._source_fingerprint()
        self.assertEqual(f1, f2)
        self.assertEqual(len(f1), 12)

    def test_snapshot_matches_source_fingerprint(self):
        with open(os.path.join(build_dataset.OUT_DIR, "deals.json"), encoding="utf-8") as f:
            meta = json.load(f)["meta"]
        self.assertEqual(meta["data_fingerprint"], build_dataset._source_fingerprint())


class TestUpdates(unittest.TestCase):
    HEADER = ["deal_id","announce_date","licensor","licensee","drug_name","target","modality","indication","deal_type","stage","upfront","total_value","value_disclosure","milestones","territory","source_name","source_title","publish_date","analyst_note","confidence","region","currency","source_url","fx_rate","upfront_musd","total_value_musd"]

    def _write(self, path, rows):
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(self.HEADER)
            w.writerows(rows)

    def test_upsert_add_and_update(self):
        tmp = tempfile.mkdtemp(prefix="etl-upd-")
        base = os.path.join(tmp, "base"); os.makedirs(base)
        upd = os.path.join(tmp, "upd"); os.makedirs(upd)
        self._write(os.path.join(base, "cleaned_data_2020.csv"), [
            ["2020-A","2020-01-10","LicA","Lic1","AssetA","T1","ADC","Oncology","License-out","Phase II","100","400","","","US","","","","","high","Global","USD","","1.0","100","400"],
            ["2020-B","2020-02-10","LicB","Lic2","AssetB","T2","mAb","Autoimmune","License-out","Phase I","","","","","EU","","","","","high","Europe","USD","","1.0","",""],
        ])
        self._write(os.path.join(upd, "2020_additions.csv"), [
            ["2020-B","2020-02-10","LicB","Lic2","AssetB","T2","mAb","Autoimmune","License-out","Phase I","30","90","","","EU","","","","","high","Europe","USD","","1.0","30","90"],
            ["2020-C","2020-03-10","LicC","Lic3","AssetC","T3","ADC","Oncology","License-out","Phase III","50","150","","","US","","","","","high","US & Canada","USD","","1.0","50","150"],
        ])
        deals, unmapped, terr_review, issues, yearly, update_stats, unique = build_dataset.collect(base, upd, years=[2020])
        by = {d["id"]: d for d in deals}
        self.assertEqual(unique, 3)
        self.assertEqual(by["2020-B"]["upfront_musd"], 30.0)
        self.assertEqual(by["2020-B"]["total_value_musd"], 90.0)
        self.assertIn("2020-C", by)
        self.assertEqual(len(update_stats), 1)
        self.assertEqual(update_stats[0]["added"], 1)
        self.assertEqual(update_stats[0]["updated"], 1)
        self.assertEqual(update_stats[0]["skipped"], 0)


class TestFnum(unittest.TestCase):
    def test_parse(self):
        self.assertIsNone(fnum(''))
        self.assertIsNone(fnum('  '))
        self.assertEqual(fnum('650.0'), 650.0)
        self.assertEqual(fnum('1,234.5'), 1234.5)

if __name__ == '__main__':
    unittest.main()


class TestDataFacts(unittest.TestCase):
    """锁定关键数据口径，防止后续 ETL 重跑时无意漂移。"""
    def test_alphamab_2026_licensor_name(self):
        with open(os.path.join(build_dataset.OUT_DIR, "deals.json"), encoding="utf-8") as f:
            deals = json.load(f)["deals"]
        row = next(d for d in deals if d["id"] == "2026-Alpham-Pathos-c895ed3a")
        self.assertEqual(row["licensor"], "康宁杰瑞 Alphamab Oncology")
        self.assertNotIn("生物制药", row["licensor"])
