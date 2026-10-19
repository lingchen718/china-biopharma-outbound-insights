-- 中国生物医药出海交易洞察 · PostgreSQL 生产库 schema
-- 单位：金额统一 M USD（百万美元）

BEGIN;

CREATE TABLE IF NOT EXISTS lookup_dim (
  dim        text NOT NULL,
  key        text NOT NULL,
  label_en   text NOT NULL,
  label_zh   text NOT NULL,
  sort_order int  NOT NULL DEFAULT 0,
  color      text,
  PRIMARY KEY (dim, key)
);

CREATE TABLE IF NOT EXISTS companies (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL UNIQUE,
  name_en    text,
  country    text,
  region     text,
  is_chinese boolean NOT NULL,
  aliases    text[]
);

CREATE TABLE IF NOT EXISTS assets (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  drug_name    text NOT NULL UNIQUE,
  drug_name_en text,
  target       text,
  modality     text,
  indication   text,
  latest_stage text
);

CREATE TABLE IF NOT EXISTS deals (
  deal_id             text PRIMARY KEY,
  signing_date        date NOT NULL,
  announce_date       date,
  licensor_id         bigint REFERENCES companies(id),
  licensee_id         bigint REFERENCES companies(id),
  asset_id            bigint REFERENCES assets(id),
  drug_name           text,
  target              text,
  modality            text,
  indication          text,
  deal_type           text,
  stage               text,
  upfront             numeric,
  total_value         numeric,
  upfront_musd        numeric(14,2),
  total_value_musd    numeric(14,2),
  milestone_musd      numeric(14,2),
  milestone_derivable boolean,
  value_disclosure    text,
  confidence          text,
  region              text,
  territory           text,
  currency            text,
  fx_rate             numeric,
  source_name         text,
  source_title        text,
  source_url          text,
  publish_date        date,
  analyst_note        text,
  ingest_batch        text NOT NULL DEFAULT 'seed',
  created_at          timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deal_territory (
  deal_id   text REFERENCES deals(deal_id) ON DELETE CASCADE,
  territory text,
  region    text,
  PRIMARY KEY (deal_id, territory)
);

CREATE TABLE IF NOT EXISTS ingest_run (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  batch       text NOT NULL,
  source_file text,
  started_at  timestamptz DEFAULT now(),
  finished_at timestamptz,
  rows_total  int,
  rows_upsert int,
  report      jsonb
);

CREATE INDEX IF NOT EXISTS idx_deals_signing_date ON deals(signing_date);
CREATE INDEX IF NOT EXISTS idx_deals_modality      ON deals(modality);
CREATE INDEX IF NOT EXISTS idx_deals_indication    ON deals(indication);
CREATE INDEX IF NOT EXISTS idx_deals_stage         ON deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_deal_type     ON deals(deal_type);
CREATE INDEX IF NOT EXISTS idx_deals_region        ON deals(region);

COMMIT;
