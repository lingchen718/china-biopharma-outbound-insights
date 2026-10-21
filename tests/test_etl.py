# -*- coding: utf-8 -*-
"""ETL 规范化逻辑的单元测试（无需数据库）。"""
import unittest
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

class TestFnum(unittest.TestCase):
    def test_parse(self):
        self.assertIsNone(fnum(''))
        self.assertIsNone(fnum('  '))
        self.assertEqual(fnum('650.0'), 650.0)
        self.assertEqual(fnum('1,234.5'), 1234.5)

if __name__ == '__main__':
    unittest.main()
