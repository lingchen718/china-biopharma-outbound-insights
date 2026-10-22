# -*- coding: utf-8 -*-
"""读取 2020–2026 清洗后 CSV，规范化并输出统一数据集与质量报告。"""
import csv, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from etl.geo_taxonomy import REGION_CANON, REGION_GROUPS, resolve_region, resolve_territory
BASE = os.environ.get("ETL_DATA_DIR", os.path.join(ROOT, "normalized_data"))
YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
OUT_DIR = os.path.join(ROOT, "data")
UPDATES_DIR = os.environ.get("ETL_UPDATES_DIR", os.path.join(ROOT, "updates"))

# ---------- 规范化映射（源值 -> 英文规范键） ----------
MODALITY = {
    "ADC": "ADC",
    "双抗 Bispecific antibody": "Bispecific",
    "单抗（非ADC）Monoclonal antibody": "mAb",
    "小分子 Small molecule": "Small molecule",
    "小分子 Small molecule / ADC": "Small molecule",
    "CAR-T / 细胞疗法 Cell therapy": "CAR-T / Cell",
    "多肽/蛋白 Peptide/Protein": "Peptide/Protein",
    "融合蛋白 Fusion protein": "Fusion protein",
    "RNA疗法 (siRNA/mRNA/ASO)": "RNA therapy",
    "溶瘤病毒/基因疗法 Other GTx": "Other GTx",
    "疫苗 Vaccine": "Vaccine",
    "其他 Other": "Other",
}
INDICATION = {
    "肿瘤 Oncology": "Oncology",
    "自免 Autoimmune": "Autoimmune",
    "中枢神经 CNS": "CNS",
    "代谢 Metabolic": "Metabolic",
    "感染 Infectious": "Infectious",
    "罕见病 Rare disease": "Rare disease",
    "疫苗 Vaccine": "Vaccine",
    "呼吸 Respiratory": "Respiratory",
    "心血管 CV": "CV",
    "眼科 Ophthalmology": "Ophthalmology",
    "其他": "Other",
    "其他 Other": "Other",
    "肿瘤 Oncology、罕见病 Rare disease": "Oncology",
}
STAGE = {
    "临床前 Preclinical": "Preclinical",
    "IND获批 IND approved": "IND approved",
    "I期 Phase I": "Phase I",
    "II期 Phase II": "Phase II",
    "III期 Phase III": "Phase III",
    "注册阶段 Registration": "Registration",
    "已上市 Marketed": "Marketed",
    "I期 Phase I、注册阶段 Registration": "Multiple Stages",
    "": "Unknown",
}
DEAL_TYPE = {
    "独占许可 Exclusive license": "License-out",
    "合作开发 Co-development": "Co-development",
    "资产转让 Assignment / asset sale": "Asset transfer",
    "非独占许可 Non-exclusive license": "Non-exclusive",
    "期权协议 Option agreement": "Option",
    "并购 Acquisition": "M&A",
    "合资公司 Joint venture": "JV",
    "分销 / 商业化 Distribution / commercialization": "Distribution",
    "其他 Other": "Other",
}
REGION = {
    "全球 Global": "Global",
    "全球除大中华区及部分亚太 Global ex-Greater China & Partial APAC": "Global ex-Greater China",
    "美国+加拿大 US & Canada": "US & Canada",
    "北美 North America": "North America",
    "欧洲 Europe": "Europe",
    "欧美区 US & Europe": "US & Europe",
    "亚太 APAC": "APAC",
    "日本 Japan": "Japan",
    "韩国 Korea": "South Korea",
    "大中华 Greater China": "Greater China",
    "中国境内权益 China Mainland Rights": "China Mainland",
    "新兴市场 Emerging Markets": "Emerging Markets",
    "其他 Other": "Other",
}
MILESTONE_DERIVABLE_TYPES = {"License-out", "Co-development", "Asset transfer", "Non-exclusive", "Option"}

def norm(key, mapping, raw, unmapped):
    v = (raw or "").strip()
    if v in mapping:
        return mapping[v]
    if v:
        unmapped[key].add(v)
    return "Other" if key in ("modality", "indication", "deal_type", "region") else "Unknown"

def fnum(s):
    s = (s or "").strip().replace(",", "")
    if s == "":
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def _source_fingerprint():
    """按输入 CSV（含增量更新）与地域分类规则内容计算确定性指纹（不依赖日期/环境）。"""
    h = hashlib.sha256()
    for y in YEARS:
        with open(os.path.join(BASE, f"cleaned_data_{y}.csv"), "rb") as f:
            h.update(f.read())
        h.update(b"\x00")
    if os.path.isdir(UPDATES_DIR):
        for fn in sorted(os.listdir(UPDATES_DIR)):
            if fn.lower().endswith(".csv"):
                with open(os.path.join(UPDATES_DIR, fn), "rb") as f:
                    h.update(f.read())
                h.update(b"\x00")
    # 分类规则变化也会改变输出，需纳入指纹，避免“改了规则但快照指纹不变”的漂移
    with open(os.path.join(os.path.dirname(__file__), "geo_taxonomy.py"), "rb") as f:
        h.update(f.read())
    h.update(b"\x00")
    return h.hexdigest()[:12]



def _year_from_deal_id(did):
    did = (did or "").strip()
    return int(did[:4]) if len(did) >= 4 and did[:4].isdigit() else None


def _deal_from_row(r, default_year, unmapped, terr_review):
    upfront_musd = fnum(r.get("upfront_musd"))
    total_musd = fnum(r.get("total_value_musd"))
    deal_type = norm("deal_type", DEAL_TYPE, r.get("deal_type"), unmapped)
    has_upfront = upfront_musd is not None
    has_total = total_musd is not None
    derivable = has_upfront and has_total and deal_type in MILESTONE_DERIVABLE_TYPES and total_musd >= upfront_musd
    milestone = round(total_musd - upfront_musd, 2) if derivable else None

    stage = norm("stage", STAGE, r.get("stage"), unmapped)
    empty_stage = 1 if (r.get("stage") or "").strip() == "" else 0
    conf = (r.get("confidence") or "").strip().lower()
    empty_conf = 1 if conf == "" else 0
    if conf == "":
        conf = "unknown"
    ind = norm("indication", INDICATION, r.get("indication"), unmapped)
    multi = 1 if "、" in (r.get("indication") or "") else 0

    region_raw = (r.get("region") or "").strip()
    region_canon, region_group = resolve_region(region_raw)
    if region_raw and region_canon == "Other" and region_raw not in REGION_CANON:
        unmapped["region"].add(region_raw)
    geo_territory, geo_region_group, geo_status = resolve_territory(r.get("territory"))
    if geo_status == "review" and (r.get("territory") or "").strip():
        terr_review.add((r.get("territory") or "").strip())

    date = (r.get("announce_date") or "").strip()
    year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else default_year

    deal = {
        "id": (r.get("deal_id") or "").strip(),
        "date": date,
        "year": year,
        "licensor": (r.get("licensor") or "").strip(),
        "licensee": (r.get("licensee") or "").strip(),
        "asset": (r.get("drug_name") or "").strip(),
        "target": (r.get("target") or "").strip(),
        "modality": norm("modality", MODALITY, r.get("modality"), unmapped),
        "indication": ind,
        "stage": stage,
        "deal_type": deal_type,
        "region": region_canon,
        "region_group": region_group,
        "geo_territory": geo_territory,
        "geo_region_group": geo_region_group,
        "geo_status": geo_status,
        "territory": (r.get("territory") or "").strip(),
        "confidence": conf,
        "currency": (r.get("currency") or "").strip() or None,
        "fx_rate": fnum(r.get("fx_rate")),
        "upfront": fnum(r.get("upfront")),
        "total_value": fnum(r.get("total_value")),
        "upfront_musd": upfront_musd,
        "total_value_musd": total_musd,
        "milestone_musd": milestone,
        "milestone_derivable": derivable,
        "has_upfront": has_upfront,
        "has_total": has_total,
        "value_disclosure": (r.get("value_disclosure") or "").strip(),
        "source_name": (r.get("source_name") or "").strip(),
        "source_title": (r.get("source_title") or "").strip(),
        "source_url": (r.get("source_url") or "").strip(),
        "publish_date": (r.get("publish_date") or "").strip(),
        "analyst_note": (r.get("analyst_note") or "").strip(),
    }
    stats = {"has_upfront": 1 if has_upfront else 0, "has_total": 1 if has_total else 0,
             "empty_stage": empty_stage, "empty_conf": empty_conf, "multi": multi}
    return deal, stats


def collect(base_dir, updates_dir, years=YEARS):
    deals_by_id = {}
    order = []
    seen_ids = {}
    unmapped = {k: set() for k in ("modality", "indication", "stage", "deal_type", "region")}
    terr_review = set()
    issues = []
    yearly = []

    for y in years:
        p = os.path.join(base_dir, f"cleaned_data_{y}.csv")
        with open(p, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        n_up = n_tot = 0
        n_empty_stage = 0
        n_empty_conf = 0
        n_multi = 0
        for r in rows:
            did = (r.get("deal_id") or "").strip()
            if not did:
                issues.append(f"{y}: 空 deal_id 行，已跳过")
                continue
            if did in seen_ids:
                issues.append(f"{y}: 重复 deal_id {did}（首次出现于 {seen_ids[did]}），已跳过")
                continue
            seen_ids[did] = y
            deal, st = _deal_from_row(r, y, unmapped, terr_review)
            n_up += st["has_upfront"]
            n_tot += st["has_total"]
            n_empty_stage += st["empty_stage"]
            n_empty_conf += st["empty_conf"]
            n_multi += st["multi"]
            deals_by_id[did] = deal
            order.append(did)
        yearly.append({"year": y, "rows": len(rows), "has_upfront": n_up, "has_total": n_tot,
                       "empty_stage": n_empty_stage, "empty_confidence": n_empty_conf, "multi_value": n_multi})

    update_stats = []
    if os.path.isdir(updates_dir):
        for fn in sorted(os.listdir(updates_dir)):
            if not fn.lower().endswith(".csv"):
                continue
            p = os.path.join(updates_dir, fn)
            with open(p, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            added = updated = skipped = 0
            for r in rows:
                did = (r.get("deal_id") or "").strip()
                if not did:
                    issues.append(f"{fn}: 空 deal_id 行，已跳过")
                    skipped += 1
                    continue
                default_year = _year_from_deal_id(did)
                if default_year is None:
                    issues.append(f"{fn}: deal_id 无年份前缀 {did}，已跳过")
                    skipped += 1
                    continue
                deal, st = _deal_from_row(r, default_year, unmapped, terr_review)
                if did in deals_by_id:
                    deals_by_id[did] = deal
                    updated += 1
                else:
                    deals_by_id[did] = deal
                    order.append(did)
                    added += 1
            update_stats.append({"file": fn, "rows": len(rows), "added": added, "updated": updated, "skipped": skipped})

    deals = [deals_by_id[did] for did in order]
    return deals, unmapped, terr_review, issues, yearly, update_stats, len(deals_by_id)


def main():
    deals, unmapped, terr_review, issues, yearly, update_stats, unique = collect(BASE, UPDATES_DIR)

    meta = {
        "source_years": YEARS,
        "total_rows": len(deals),
        "unique_deal_ids": unique,
        "modality": sorted({d["modality"] for d in deals}),
        "indication": sorted({d["indication"] for d in deals}),
        "stage": sorted({d["stage"] for d in deals}),
        "deal_type": sorted({d["deal_type"] for d in deals}),
        "region": sorted({d["region"] for d in deals}),
        "region_group": sorted({d["region_group"] for d in deals}),
        "geo_territory": sorted({d["geo_territory"] for d in deals}),
        "confidence": sorted({d["confidence"] for d in deals}),
        "data_fingerprint": _source_fingerprint(),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {"meta": meta, "deals": deals}
    with open(os.path.join(OUT_DIR, "deals.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    demo_dir = os.path.join(os.path.dirname(OUT_DIR), "demo", "data")
    os.makedirs(demo_dir, exist_ok=True)
    with open(os.path.join(demo_dir, "deals.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = ["# 数据质量报告（ETL 自动生成）", "", f"- 数据指纹：{meta['data_fingerprint']}", f"- 总记录：{meta['total_rows']}", f"- 唯一 deal_id：{meta['unique_deal_ids']}", ""]
    lines.append("## 按年统计")
    lines.append("| 年份 | 原始行数 | 已披露首付款 | 已披露总额 | 空阶段 | 空置信度 | 多值字段 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for t in yearly:
        lines.append(f"| {t['year']} | {t['rows']} | {t['has_upfront']} | {t['has_total']} | {t['empty_stage']} | {t['empty_confidence']} | {t['multi_value']} |")
    lines.append("")
    if update_stats:
        lines.append("## 增量更新（updates/）")
        lines.append("| 文件 | 行数 | 新增 | 覆盖更新 | 跳过 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for u in update_stats:
            lines.append(f"| {u['file']} | {u['rows']} | {u['added']} | {u['updated']} | {u['skipped']} |")
        lines.append("")
    lines.append("## 未映射/需人工复核的枚举值")
    for k, vs in unmapped.items():
        if vs:
            lines.append(f"- **{k}**: {sorted(vs)}")
    if not any(unmapped.values()):
        lines.append("- 无")
    lines.append("")
    lines.append("## 地域解析待人工复核（territory）")
    lines.append(f"- 未解析条数：{len(terr_review)}")
    for t in sorted(terr_review)[:40]:
        lines.append(f"- {t}")
    if len(terr_review) > 40:
        lines.append(f"- … 以及其余 {len(terr_review) - 40} 条")
    lines.append("")
    lines.append("## 其他问题")
    if issues:
        lines += [f"- {i}" for i in issues]
    else:
        lines.append("- 无")
    with open(os.path.join(OUT_DIR, "quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("rows:", len(deals), "| unique ids:", unique)
    for t in yearly:
        print(t)


if __name__ == "__main__":
    main()
