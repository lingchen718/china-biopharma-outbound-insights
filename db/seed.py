# -*- coding: utf-8 -*-
"""把 data/deals.json 规范化数据落库到 SQLite。"""
import json, os, sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "db", "app.db")
DATA_PATH = os.path.join(ROOT, "data", "deals.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
  deal_id TEXT PRIMARY KEY,
  date TEXT, year INTEGER,
  licensor TEXT, licensee TEXT, asset TEXT, target TEXT,
  modality TEXT, indication TEXT, stage TEXT, deal_type TEXT,
  region TEXT, territory TEXT, confidence TEXT, currency TEXT, fx_rate REAL,
  upfront REAL, total_value REAL,
  upfront_musd REAL, total_value_musd REAL, milestone_musd REAL,
  milestone_derivable INTEGER, has_upfront INTEGER, has_total INTEGER,
  value_disclosure TEXT, source_name TEXT, source_title TEXT,
  source_url TEXT, publish_date TEXT, analyst_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_deals_year ON deals(year);
CREATE INDEX IF NOT EXISTS idx_deals_modality ON deals(modality);
CREATE INDEX IF NOT EXISTS idx_deals_indication ON deals(indication);
CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_deal_type ON deals(deal_type);
CREATE INDEX IF NOT EXISTS idx_deals_region ON deals(region);
"""

COLS = ["deal_id","date","year","licensor","licensee","asset","target","modality",
        "indication","stage","deal_type","region","territory","confidence","currency",
        "fx_rate","upfront","total_value","upfront_musd","total_value_musd",
        "milestone_musd","milestone_derivable","has_upfront","has_total",
        "value_disclosure","source_name","source_title","source_url","publish_date","analyst_note"]

def ensure_db(path=DB_PATH):
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        n = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        if n == 0:
            with open(DATA_PATH, encoding="utf-8") as f:
                data = json.load(f)
            rows = [tuple(d.get(c) for c in COLS) for d in data["deals"]]
            conn.executemany(
                f"INSERT OR REPLACE INTO deals ({','.join(COLS)}) VALUES ({','.join('?'*len(COLS))})",
                rows)
            n = len(rows)
    return n

if __name__ == "__main__":
    print("SQLite 落库完成，deals 行数 =", ensure_db())