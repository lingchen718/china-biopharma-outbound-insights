# 增量更新目录（updates/）

在这里放置**增量 / 更新**的 CSV 文件，即可在不修改 `normalized_data/` 基础文档的前提下增补或覆盖交易数据。

## 规则

- 文件名任意，只要以 `.csv` 结尾；会按文件名排序后合并，保证结果可复现。
- 列头必须与基础 CSV 一致（以下 26 列）：

```
deal_id,announce_date,licensor,licensee,drug_name,target,modality,indication,deal_type,stage,upfront,total_value,value_disclosure,milestones,territory,source_name,source_title,publish_date,analyst_note,confidence,region,currency,source_url,fx_rate,upfront_musd,total_value_musd
```

- **合并口径（按 `deal_id` 去重 / upsert）**：
  - `deal_id` 已存在 → 用更新行**整体覆盖**原行；
  - `deal_id` 不存在 → 作为**新增行**追加。
- 年份判定：优先取 `announce_date` 的前 4 位；为空时回退到 `deal_id` 的前 4 位（`YYYY-...`）。两者都没有则跳过并记入质量报告。

## 使用步骤

1. 把新的 CSV（例如 `2020_additions.csv`、`2026_updates.csv`）放进本目录。
2. 执行一键刷新：

```bash
bash scripts/refresh.sh
```

或手动执行：

```bash
python3 etl/build_dataset.py   # 合并 base + updates/ → data/deals.json
python3 db/seed.py             # 重新落库
```

3. 若 API 服务正在运行，重启它：

```bash
python3 api/server.py
```

## 注意

- 更新文件会参与数据指纹计算，请把更新 CSV 与重新生成的 `data/deals.json`、`data/quality_report.md`、`demo/data/deals.json` **一起提交**，否则 CI 的可复现性门禁会失败。
- `upfront_musd` / `total_value_musd` 已是按签约日汇率折算的美元金额（M USD），直接填最终美元值即可。
