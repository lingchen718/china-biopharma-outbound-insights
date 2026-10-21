# 中国生物医药出海交易洞察

中国药企对外授权（license-out）交易情报平台（MVP）。暗色主题、中英双语，7 个分析页面 + 交易卡片，数据覆盖 2020–2026。

## 架构（轻量栈，已正式化）

```
清洗后 CSV (2020–2026)
        │  etl/build_dataset.py（规范化 + 质量报告）
        ▼
data/deals.json  ──►  db/seed.py（落库到本地 SQLite）
        │                    │
        │                    ▼
        │              api/server.py（HTTP + 聚合接口）
        │                    │
        └────────►  demo/index.html（前端，调用 /api/*）
```

- **前端**：`demo/index.html` —— 原生 JS + ECharts，静态单文件，暗色主题。
- **API**：`api/server.py` —— 仅用 Python 标准库，聚合逻辑全部在服务端。
- **数据库**：本地 SQLite（`db/` 目录，由 seed 自动生成，已 .gitignore 忽略）。
- **生产 schema**：`db/schema`（PostgreSQL 建表 DDL 文件），供未来迁库使用。
- **数据管道**：`etl/build_dataset.py` —— 读取清洗后 CSV，输出统一数据集与质量报告。

## 目录结构

```
demo/index.html        前端页面
api/server.py          API + 静态站点服务
db/seed.py             本地库落库脚本
db/schema              生产库建表 DDL
etl/build_dataset.py   数据规范化 ETL
data/deals.json        统一数据集
data/quality_report.md 数据质量报告
tests/                 单元测试 + E2E 脚本
docs/                  产品设计文档、技术方案设计
```

## 快速开始

```bash
# 1) 规范化数据（输出 data/deals.json + demo/data/deals.json + 质量报告）
python3 etl/build_dataset.py

# 2) 落库到本地 SQLite
python3 db/seed.py

# 3) 启动服务（静态站点 + /api/*）
python3 api/server.py
```

浏览器访问 `http://127.0.0.1:8090/`。

## 测试

```bash
# 单元测试（ETL + 聚合接口，无需第三方依赖）
python3 -m unittest discover -s tests -v

# 浏览器端 E2E（需先安装 Playwright）
# npm i -D @playwright/test && npx playwright install chromium
# npx playwright test tests/e2e_playwright.spec.js
```

## 数据口径（要点）

- 金额统一为百万美元（M USD），直接采用 CSV 中已按交易当日汇率折算的 `upfront_musd` / `total_value_musd`。
- 里程碑仅在首付款与潜在总额对价一致、可拆分、两端均已披露时按 `total − upfront` 派生；否则标记 Not Derivable。
- 未披露金额 ≠ 0，不计入求和；金额图展示披露率。
- 枚举（药物形式 / 治疗领域 / 研发阶段 / 交易类型 / 区域）已规范化到英文规范键，中文作为显示别名。
