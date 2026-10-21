# -*- coding: utf-8 -*-
"""地域分类口径：region 规范键 + 互斥 region_group + territory 受控解析。

- region：授权区域原文归一后的规范键（保留分析师粒度）。
- region_group：互斥上层大区，用于汇总与全局筛选，避免“北美 vs 美国+加拿大”
  这类语义重叠造成的误解；每个 region 只归入一个 group。
- territory：原始自由文本保留；geo_territory 为受控解析后的单一国家/地区桶
  （first-match-wins，杜绝一单多国重复计数）；解析不到归 Other 并标记 review。
"""

# 原始 region 文本 -> 规范键
REGION_CANON = {
    "全球 Global": "Global",
    "全球除大中华区及部分亚太 Global ex-Greater China & Partial APAC": "Global ex-Greater China",
    "新兴市场 Emerging Markets": "Emerging Markets",
    "亚太 APAC": "APAC",
    "其他 Other": "Other",
    "北美 North America": "North America",
    "欧洲 Europe": "Europe",
    "美国+加拿大 US & Canada": "US & Canada",
    "中国境内权益 China Mainland Rights": "China Mainland",
    "韩国 Korea": "South Korea",
    "大中华 Greater China": "Greater China",
    "欧美区 US & Europe": "US & Europe",
    "日本 Japan": "Japan",
}

# 互斥上层大区（region_group）
REGION_GROUPS = [
    "Global",
    "Global ex-Greater China",
    "Greater China",
    "North America",
    "Europe",
    "US & Europe",
    "APAC",
    "Emerging Markets",
    "Other",
]

REGION_GROUP = {
    "Global": "Global",
    "Global ex-Greater China": "Global ex-Greater China",
    "Greater China": "Greater China",
    "China Mainland": "Greater China",
    "North America": "North America",
    "US & Canada": "North America",
    "US & Europe": "US & Europe",
    "Europe": "Europe",
    "APAC": "APAC",
    "Japan": "APAC",
    "South Korea": "APAC",
    "Emerging Markets": "Emerging Markets",
    "Other": "Other",
}

# geo_territory -> region_group（用于世界地图按上层大区着色/筛选）
GEO_REGION_GROUP = {
    "Global": "Global",
    "Global ex-Greater China": "Global ex-Greater China",
    "Greater China": "Greater China",
    "China Mainland": "Greater China",
    "US & Canada": "North America",
    "US & Europe": "US & Europe",
    "North America": "North America",
    "United States": "North America",
    "Canada": "North America",
    "Europe": "Europe",
    "Germany": "Europe",
    "United Kingdom": "Europe",
    "France": "Europe",
    "Switzerland": "Europe",
    "APAC": "APAC",
    "Southeast Asia": "APAC",
    "Japan": "APAC",
    "South Korea": "APAC",
    "Singapore": "APAC",
    "Australia": "APAC",
    "Emerging Markets": "Emerging Markets",
    "Middle East & North Africa": "Emerging Markets",
    "Latin America": "Emerging Markets",
    "CIS": "Emerging Markets",
    "Indonesia": "Emerging Markets",
    "India": "Emerging Markets",
    "Brazil": "Emerging Markets",
    "Vietnam": "Emerging Markets",
    "Turkey": "Emerging Markets",
    "Philippines": "Emerging Markets",
    "Malaysia": "Emerging Markets",
    "Pakistan": "Emerging Markets",
    "Thailand": "Emerging Markets",
    "Bangladesh": "Emerging Markets",
    "Russia": "Emerging Markets",
    "Saudi Arabia": "Emerging Markets",
    "Argentina": "Emerging Markets",
    "Uruguay": "Emerging Markets",
    "Paraguay": "Emerging Markets",
    "Other": "Other",
}

# 有序规则：first-match-wins。keyword 为小写子串，任一命中即匹配。
TERRITORY_RULES = [
    # 组合/跨境区域（放最前，优先于单国）
    ("US & Canada", ["us and canada", "united states and canada", "美国+加拿大", "美国及加拿大", "美加", "coherus territory"]),
    ("US & Europe", ["us & europe", "欧美", "美国及欧洲", "美国与欧洲"]),
    ("Global ex-Greater China", [
        "global ex-greater china", "global excluding greater china", "worldwide outside greater china",
        "全球除大中华", "除大中华区", "ex-greater china", "excluding greater china",
        "ex-mainland china, hong kong, macau, taiwan", "excluding mainland china, hong kong, macau and taiwan",
        "excluding china's mainland, hong kong, macau and taiwan",
        "worldwide excluding mainland china, hong kong, macau and taiwan",
        "worldwide outside of china", "worldwide rights outside of china",
        "全球（除大中华", "全球除大中华", "大中华地区以外全球", "大中华区以外",
        "除中国大陆、香港", "除中国内地、香港", "不包括中国内地、香港",
    ]),
    ("Greater China", ["大中华", "greater china", "中国大陆、香港", "中国内地、香港", "中国（包括", "中国包括"]),
    ("China Mainland", ["中国大陆", "中国境内", "china mainland", "mainland china rights", "中国市场", "罗沙司他在中国"]),
    ("Europe", ["europe", "欧洲", "欧盟", "eea", "巴尔干"]),
    ("Middle East & North Africa", ["middle east", "中东", "mena", "menat", "北非", "gcc", "saudi arabia", "沙特"]),
    ("Latin America", ["latin america", "拉丁美洲", "巴西以及其余拉丁美洲"]),
    ("Southeast Asia", ["southeast asia", "东南亚", "东盟"]),
    ("CIS", ["cis", "独联体", "俄罗斯及其他独联体"]),
    ("Emerging Markets", ["emerging markets", "新兴市场"]),
    ("Global", ["global", "worldwide", "全球", "全世界", "全球范围"]),
    # 单国（按特异性排序）
    ("United States", ["united states", "美国", " u.s.", "us territory", "美国权益"]),
    ("Canada", ["canada", "加拿大"]),
    ("Japan", ["japan", "日本"]),
    ("South Korea", ["korea", "韩国"]),
    ("Germany", ["germany", "德国"]),
    ("United Kingdom", ["united kingdom", " uk", "英国"]),
    ("France", ["france", "法国"]),
    ("Switzerland", ["switzerland", "瑞士"]),
    ("Singapore", ["singapore", "新加坡"]),
    ("Australia", ["australia", "澳大利亚", "澳洲"]),
    ("Indonesia", ["indonesia", "印度尼西亚", "印尼"]),
    ("India", [" india", "印度"]),
    ("Brazil", ["brazil", "巴西"]),
    ("Vietnam", ["vietnam", "越南"]),
    ("Turkey", ["turkey", "土耳其"]),
    ("Philippines", ["philippines", "菲律宾"]),
    ("Malaysia", ["malaysia", "马来西亚"]),
    ("Pakistan", ["pakistan", "巴基斯坦"]),
    ("Thailand", ["thailand", "泰国"]),
    ("Bangladesh", ["bangladesh", "孟加拉"]),
    ("Russia", ["russia", "俄罗斯"]),
    ("Argentina", ["argentina", "阿根廷"]),
    ("Uruguay", ["uruguay", "乌拉圭"]),
    ("Paraguay", ["paraguay", "巴拉圭"]),
    ("Other", ["未授予区域", "无区域", "未披露", "未揭露"]),
]


def resolve_region(raw):
    canon = REGION_CANON.get((raw or "").strip())
    if canon is None:
        canon = "Other"
    return canon, REGION_GROUP.get(canon, "Other")


def resolve_territory(terr):
    text = (terr or "").strip().lower()
    if not text:
        return "Other", GEO_REGION_GROUP["Other"], "review"
    for geo, keywords in TERRITORY_RULES:
        for kw in keywords:
            if kw in text:
                return geo, GEO_REGION_GROUP.get(geo, "Other"), "resolved"
    return "Other", GEO_REGION_GROUP["Other"], "review"
