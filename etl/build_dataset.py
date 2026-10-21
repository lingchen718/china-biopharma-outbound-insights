# -*- coding: utf-8 -*-
"""读取 2020–2026 清洗后 CSV，规范化并输出统一数据集与质量报告。"""
import csv, hashlib, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("ETL_DATA_DIR", os.path.join(ROOT, "normalized_data"))
YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
OUT_DIR = os.path.join(ROOT, "data")

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
    """按输入 CSV 内容计算确定性指纹（不依赖日期/环境，保证可复现）。"""
    h = hashlib.sha256()
    for y in YEARS:
        with open(os.path.join(BASE, f"cleaned_data_{y}.csv"), "rb") as f:
            h.update(f.read())
        h.update(b"\x00")
    return h.hexdigest()[:12]

def main():
    deals = []
    unmapped = {k: set() for k in ("modality", "indication", "stage", "deal_type", "region")}
    issues = []
    seen_ids = {}
    yearly = []

    for y in YEARS:
        p = os.path.join(BASE, f"cleaned_data_{y}.csv")
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

            upfront_musd = fnum(r.get("upfront_musd"))
            total_musd = fnum(r.get("total_value_musd"))
            deal_type = norm("deal_type", DEAL_TYPE, r.get("deal_type"), unmapped)
            has_upfront = upfront_musd is not None
            has_total = total_musd is not None
            derivable = has_upfront and has_total and deal_type in MILESTONE_DERIVABLE_TYPES and total_musd >= upfront_musd
            milestone = round(total_musd - upfront_musd, 2) if derivable else None

            stage = norm("stage", STAGE, r.get("stage"), unmapped)
            if (r.get("stage") or "").strip() == "":
                n_empty_stage += 1
            conf = (r.get("confidence") or "").strip().lower()
            if conf == "":
                conf = "unknown"
                n_empty_conf += 1
            ind = norm("indication", INDICATION, r.get("indication"), unmapped)
            if "、" in (r.get("indication") or ""):
                n_multi += 1

            date = (r.get("announce_date") or "").strip()
            year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else y

            if has_upfront:
                n_up += 1
            if has_total:
                n_tot += 1

            deals.append({
                "id": did,
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
                "region": norm("region", REGION, r.get("region"), unmapped),
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
            })
        yearly.append({"year": y, "rows": len(rows), "has_upfront": n_up, "has_total": n_tot,
                       "empty_stage": n_empty_stage, "empty_confidence": n_empty_conf, "multi_value": n_multi})

    meta = {
        "source_years": YEARS,
        "total_rows": len(deals),
        "unique_deal_ids": len(seen_ids),
        "modality": sorted({d["modality"] for d in deals}),
        "indication": sorted({d["indication"] for d in deals}),
        "stage": sorted({d["stage"] for d in deals}),
        "deal_type": sorted({d["deal_type"] for d in deals}),
        "region": sorted({d["region"] for d in deals}),
        "confidence": sorted({d["confidence"] for d in deals}),
        "data_fingerprint": _source_fingerprint(),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {"meta": meta, "deals": deals}
    with open(os.path.join(OUT_DIR, "deals.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # 同步一份到 demo 目录，供前端原型直接 fetch
    demo_dir = os.path.join(os.path.dirname(OUT_DIR), "demo", "data")
    os.makedirs(demo_dir, exist_ok=True)
    with open(os.path.join(demo_dir, "deals.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 质量报告
    lines = ["# 数据质量报告（ETL 自动生成）", "", f"- 数据指纹：{meta['data_fingerprint']}", f"- 总记录：{meta['total_rows']}", f"- 唯一 deal_id：{meta['unique_deal_ids']}", ""]
    lines.append("## 按年统计")
    lines.append("| 年份 | 原始行数 | 已披露首付款 | 已披露总额 | 空阶段 | 空置信度 | 多值字段 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for t in yearly:
        lines.append(f"| {t['year']} | {t['rows']} | {t['has_upfront']} | {t['has_total']} | {t['empty_stage']} | {t['empty_confidence']} | {t['multi_value']} |")
    lines.append("")
    lines.append("## 未映射/需人工复核的枚举值")
    for k, vs in unmapped.items():
        if vs:
            lines.append(f"- **{k}**: {sorted(vs)}")
    if not any(unmapped.values()):
        lines.append("- 无")
    lines.append("")
    lines.append("## 其他问题")
    if issues:
        lines += [f"- {i}" for i in issues]
    else:
        lines.append("- 无")
    with open(os.path.join(OUT_DIR, "quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("rows:", len(deals), "| unique ids:", len(seen_ids))
    for t in yearly:
        print(t)

if __name__ == "__main__":
    main()
