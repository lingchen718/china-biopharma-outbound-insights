# 数据修正日志 Data Correction Log

本文件记录对原始数据、口径映射、派生字段的每一次修正，保证研究可追溯。
任何会改变 `data/deals.json` 或前端展示结果的改动，都必须在此追加一条记录。

## 记录格式

| 日期 | 类别 | 影响范围 | 修正前 → 修正后 | 原因与依据 | 相关提交/指纹 |
| --- | --- | --- | --- | --- | --- |

## 修正记录

### 2026-10-21 · 地域分类口径重构（region / territory）
- 类别：口径映射（不改原始 CSV，改派生字段）
- 影响范围：全部交易的 `region_group`、`geo_territory`、`geo_region_group`、`geo_status`
- 修正前 → 修正后：
  - `region` 语义重叠（Japan / South Korea 与 APAC 重叠、US & Canada 与 North America 重叠）→ 新增互斥上层大区 `region_group` 用于汇总与全局筛选。
  - `territory` 关键词匹配（多命中、漏识别、大量 Other）→ 受控 first-match-wins 规则 `geo_territory`，未识别归 Other 并标记 review。
- 原因与依据：避免按区域汇总时重复计数，保证地图/筛选口径一致。
- 规则位置：`etl/geo_taxonomy.py`
- region_group 取值：Global / Global ex-Greater China / Greater China / North America / Europe / US & Europe / APAC / Emerging Markets / Other

### 2026-10-21 · 移除 2 笔 2023 交易
- 类别：原始数据修正
- 影响范围：2023 年 62 → 60 笔；总笔数 571 → 569
- 移除交易 ID：
  - `2023-PhaseB-JiXing-71e9c04c`
  - `2023-MerckK-Hasten-be982e78`
- 原因与依据：方向/范围复核后剔除，均不符合「中国药企出海（licensing-out）」口径。
  - `2023-PhaseB-JiXing-71e9c04c`：中国授权方（licensor）字段为外国公司 PhaseBio Pharmaceuticals, Inc.（实际为境外方向中国方箕星药业转让资产，inbound）。
  - `2023-MerckK-Hasten-be982e78`：中国方（海森生物）受让境外资产（inbound）。
- 相关提交：`bf0420c`

### 金额口径说明（基准）
- 类别：口径说明
- `upfront_musd` / `total_value_musd`：已按交易签署日汇率折算为百万美元，ETL 不再二次换算。
- `milestone_musd`：仅当首付款与潜在总额对价范围一致、可拆分时按 `total_value_musd − upfront_musd` 派生；含股权/分成等无法拆分的交易标记为 Not Derivable。
- 未披露金额 ≠ 0：`has_upfront` / `has_total` 单独标记，金额求和只纳入已披露交易。
