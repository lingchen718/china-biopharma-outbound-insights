#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 API + 静态站点服务（仅标准库）。聚合逻辑全部在服务端 SQL/内存完成。"""
import csv, io, json, mimetypes, os, sqlite3, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "db", "app.db")
DEMO_DIR = os.path.join(ROOT, "demo")
PORT = int(os.environ.get("PORT", "8090"))
HOST = os.environ.get("HOST", "127.0.0.1")
MAX_PAGE_SIZE = 1000
CACHE_TTL = 30
_CACHE = {}

def cached(key, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]
    val = fn()
    _CACHE[key] = (now + CACHE_TTL, val)
    if len(_CACHE) > 500:
        for k in list(_CACHE):
            if _CACHE[k][0] <= now:
                _CACHE.pop(k, None)
    return val

def ensure_db():
    if not os.path.exists(DB_PATH):
        subprocess.run([sys.executable, os.path.join(ROOT, "db", "seed.py")], check=True)

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def rows(sql, args=()):
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]

def one(sql, args=()):
    with connect() as conn:
        r = conn.execute(sql, args).fetchone()
    return dict(r) if r else {}

def median(a):
    if not a: return None
    s = sorted(a); m = len(s)//2
    return (s[m] if len(s)%2 else (s[m-1]+s[m])/2)

def quartiles(a):
    if not a: return None
    s = sorted(a)
    def q(p):
        i = (len(s)-1)*p; lo=int(i); hi=min(len(s)-1, lo+1)
        return round(s[lo]+(s[hi]-s[lo])*(i-lo), 2)
    return [s[0], q(.25), q(.5), q(.75), s[-1]]

def boolify(row):
    for k in ("milestone_derivable","has_upfront","has_total"):
        if k in row: row[k] = bool(row[k])
    return row

# ---------- 通用过滤 ----------
def filter_clause(qs):
    where, args = [], []
    for k in ("year_from","year_to"):
        if k in qs: where.append("year" + (">=" if k=="year_from" else "<=") + " ?"); args.append(int(qs[k][0]))
    for k, col in (("deal_type","deal_type"),("modality","modality"),("indication","indication"),("stage","stage"),("region","region"),("region_group","region_group")):
        if k in qs:
            vals = [x for x in qs[k][0].split(",") if x]
            if vals:
                where.append(col + " IN (" + ",".join("?"*len(vals)) + ")"); args += vals
    if "q" in qs:
        like = "%" + qs["q"][0] + "%"
        where.append("(licensor LIKE ? OR licensee LIKE ? OR asset LIKE ? OR target LIKE ? OR indication LIKE ?)")
        args += [like]*5
    if "disclosure" in qs:
        conds = []
        for v in [x for x in qs["disclosure"][0].split(",") if x]:
            if v == "upfront": conds.append("has_upfront=1")
            elif v == "total": conds.append("has_total=1")
            elif v == "undisclosed": conds.append("(has_upfront=0 AND has_total=0)")
        if conds:
            where.append("(" + " OR ".join(conds) + ")")
    # 金额区间（百万美元；未披露为 NULL，不参与区间比较）
    for k, col in (("upfront_min","upfront_musd"),("upfront_max","upfront_musd"),
                   ("total_min","total_value_musd"),("total_max","total_value_musd")):
        if k in qs and qs[k][0] not in ("", None):
            try:
                val = float(qs[k][0])
            except ValueError:
                continue
            op = ">=" if k.endswith("_min") else "<="
            where.append(f"{col} IS NOT NULL AND {col} {op} ?"); args.append(val)
    # 签署日期区间（date 为 YYYY-MM-DD 字符串，可直接字典序比较）
    for k, op in (("date_from",">="),("date_to","<=")):
        if k in qs and qs[k][0] not in ("", None):
            where.append(f"date {op} ?"); args.append(qs[k][0])
    # 里程碑可派生
    if "milestone" in qs:
        conds = []
        for v in [x for x in qs["milestone"][0].split(",") if x]:
            if v == "derivable": conds.append("milestone_derivable=1")
            elif v == "not_derivable": conds.append("milestone_derivable=0")
        if conds:
            where.append("(" + " OR ".join(conds) + ")")
    return (" WHERE " + " AND ".join(where) if where else "", args)

# ---------- 页面聚合 ----------
def ep_meta():
    enums = {}
    for dim in ["modality","indication","stage","deal_type","region","region_group","geo_territory"]:
        enums[dim] = [r["v"] for r in rows(f"SELECT DISTINCT {dim} AS v FROM deals WHERE {dim} IS NOT NULL AND {dim}!='' ORDER BY {dim}")]
    return {"total_rows": len(rows("SELECT deal_id FROM deals")), "enums": enums}

def ep_deals(qs):
    w, a = filter_clause(qs)
    limit = int(qs.get("limit",[0])[0]) or None
    offset = int(qs.get("offset",[0])[0]) or 0
    if limit is not None:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
    total = one("SELECT COUNT(*) AS n FROM deals" + w, a)["n"]
    sql = ("SELECT deal_id AS id, date, year, licensor, licensee, asset, target, modality, indication, stage, "
           "deal_type, region, region_group, territory, geo_territory, geo_region_group, geo_status, confidence, "
           "upfront_musd, total_value_musd, milestone_musd, milestone_derivable, "
           "has_upfront, has_total, value_disclosure, source_name, source_title, source_url, publish_date, analyst_note "
           "FROM deals" + w + " ORDER BY date DESC")
    args = a
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        args = a + [limit, offset]
    return {"deals": [boolify(r) for r in rows(sql, args)], "total": total}

EXPORT_COLS = [
    ("deal_id","交易ID Deal ID"), ("date","签署日期 Date"), ("year","年份 Year"),
    ("licensor","中国授权方 Licensor"), ("licensee","海外引进方 Licensee"),
    ("asset","资产 Asset"), ("target","靶点 Target"),
    ("modality","药物形式 Modality"), ("indication","治疗领域 Therapeutic Area"),
    ("stage","研发阶段 Stage"), ("deal_type","交易类型 Deal Type"),
    ("region","授权区域 Region"), ("region_group","上层大区 Region Group"),
    ("territory","授权区域原文 Territory"), ("geo_territory","解析地域 Geo Territory"),
    ("upfront_musd","首付款(百万美元) Upfront (USD M)"),
    ("total_value_musd","潜在总额(百万美元) Total Value (USD M)"),
    ("milestone_musd","里程碑(百万美元) Milestone (USD M)"),
    ("milestone_derivable","里程碑可派生 Milestone Derivable"),
    ("has_upfront","已披露首付款 Has Upfront"),
    ("has_total","已披露总额 Has Total"),
    ("confidence","置信度 Confidence"), ("value_disclosure","披露类型 Value Disclosure"),
    ("source_name","信源 Source"), ("source_url","信源链接 URL"),
    ("publish_date","发布时间 Publish Date"), ("analyst_note","分析备注 Analyst Note"),
]

def ep_deals_csv(qs):
    """按当前筛选导出全部匹配交易为 CSV（带 BOM，Excel 可直接打开中文）。"""
    w, a = filter_clause(qs)
    cols = [c[0] for c in EXPORT_COLS]
    sql = "SELECT " + ",".join(cols) + " FROM deals" + w + " ORDER BY date DESC"
    data = rows(sql, a)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c[1] for c in EXPORT_COLS])
    for r in data:
        writer.writerow([r.get(c[0], "") for c in EXPORT_COLS])
    return "\ufeff" + buf.getvalue()

def ep_overview_kpis(qs):
    w, a = filter_clause(qs)
    sql = ("SELECT COUNT(*) AS total_deals, COALESCE(SUM(total_value_musd),0) AS total_value, "
           "COALESCE(MAX(total_value_musd),0) AS highest_deal, COALESCE(SUM(upfront_musd),0) AS total_upfront, "
           "COUNT(DISTINCT licensor) AS licensors, COUNT(DISTINCT licensee) AS licensees FROM deals" + w)
    return one(sql, a)

def ep_overview_trends(qs):
    metric = qs.get("metric",["count"])[0]
    dim = qs.get("dim",["modality"])[0]
    val = {"count":"COUNT(*)","upfront":"COALESCE(SUM(CASE WHEN has_upfront=1 THEN upfront_musd END),0)",
           "total":"COALESCE(SUM(CASE WHEN has_total=1 THEN total_value_musd END),0)"}.get(metric, "COUNT(*)")
    cats = [r["v"] for r in rows(f"SELECT DISTINCT {dim} AS v FROM deals WHERE {dim} IS NOT NULL AND {dim}!='' ORDER BY {dim}")]
    years = [2020,2021,2022,2023,2024,2025,2026]
    w, a = filter_clause(qs)
    grid = rows(f"SELECT year, {dim} AS dim, {val} AS v FROM deals" + w + f" GROUP BY year, {dim}", a)
    g = {(r["year"], r["dim"]): r["v"] for r in grid}
    series = [{"name": c, "data": [g.get((y,c),0) for y in years]} for c in cats]
    return {"years": years, "categories": cats, "series": series}

def ep_geo(qs):
    w, a = filter_clause(qs)
    return rows("SELECT region, COUNT(*) AS deals, COALESCE(SUM(total_value_musd),0) AS value FROM deals" + w + " GROUP BY region ORDER BY deals DESC LIMIT 8", a)

def ep_geo_countries(qs):
    w, a = filter_clause(qs)
    raw = rows("SELECT geo_territory, geo_region_group, has_total, total_value_musd FROM deals" + (w or ""), a)
    agg = {}
    for r in raw:
        k = r["geo_territory"] or "Other"
        g = agg.setdefault(k, {"deals":0,"value":0.0,"region":r["geo_region_group"] or "Other"})
        g["deals"] += 1
        if r["has_total"] and r["total_value_musd"] is not None:
            g["value"] += r["total_value_musd"]
    out = [{"country":k,"region":g["region"],"deals":g["deals"],"value":round(g["value"],2)} for k,g in agg.items()]
    out.sort(key=lambda x:-x["deals"])
    return out[:12]

def ep_landscape(qs, dim):
    if dim not in ("modality","indication","stage","deal_type"): dim = "modality"
    w, a = filter_clause(qs)
    base = w if w else " WHERE 1=1"
    total = one("SELECT COUNT(*) AS n FROM deals"+base, a)["n"]
    counts = rows(f"SELECT {dim} AS key, COUNT(*) AS value FROM deals"+base+f" GROUP BY {dim} ORDER BY value DESC", a)
    up = rows(f"SELECT {dim} AS key, SUM(upfront_musd) AS value FROM deals"+base+" AND has_upfront=1"+f" GROUP BY {dim} ORDER BY value DESC", a)
    up_n = one("SELECT COUNT(*) AS n FROM deals"+base+" AND has_upfront=1", a)["n"]
    return {"total": total, "coverage": round(up_n/total*100) if total else 0, "counts": counts, "upfront": up}

def ep_economics_snapshot(qs):
    w, a = filter_clause(qs)
    base = w if w else " WHERE 1=1"
    return {
        "upfront_deals": one("SELECT COUNT(*) n FROM deals" + base + " AND has_upfront=1", a)["n"],
        "total_deals_count": one("SELECT COUNT(*) n FROM deals" + base + " AND has_total=1", a)["n"],
        "total_rows": one("SELECT COUNT(*) n FROM deals" + base, a)["n"],
        "total_upfront": one("SELECT COALESCE(SUM(upfront_musd),0) v FROM deals" + base + " AND has_upfront=1", a)["v"],
        "median_upfront": median([r["v"] for r in rows("SELECT upfront_musd v FROM deals" + base + " AND has_upfront=1", a)]),
        "total_value": one("SELECT COALESCE(SUM(total_value_musd),0) v FROM deals" + base + " AND has_total=1", a)["v"],
    }

def ep_economics_trends(qs):
    gran = qs.get("granularity",["year"])[0]
    if gran=="quarter": pexpr = "strftime('%Y', date) || '-Q' || ((CAST(strftime('%m', date) AS INTEGER)+2)/3)"
    elif gran=="month": pexpr = "strftime('%Y-%m', date)"
    else: gran="year"; pexpr = "strftime('%Y', date)"
    w, a = filter_clause(qs)
    data = rows(f"SELECT {pexpr} AS period, COUNT(*) AS deals, SUM(has_upfront) AS up_n, "
                "COALESCE(SUM(CASE WHEN has_upfront=1 THEN upfront_musd END),0) AS upfront, "
                "SUM(has_total) AS tot_n, COALESCE(SUM(CASE WHEN has_total=1 THEN total_value_musd END),0) AS total_value "
                "FROM deals" + w + " GROUP BY period ORDER BY period", a)
    by = {r["period"]: r for r in data}
    def prev(k):
        if gran=="year": return str(int(k)-1)
        if gran=="quarter":
            y,q = k.split("-Q"); return f"{int(y)-1}-Q{q}"
        y,m = k.split("-"); return f"{int(y)-1}-{m}"
    for r in data:
        p = by.get(prev(r["period"]))
        for metric,key in (("deals","count_yoy"),("upfront","upfront_yoy"),("total_value","total_yoy")):
            r[key] = round((r[metric]-p[metric])/p[metric]*100,1) if (p and p[metric]) else None
    return {"granularity": gran, "rows": data}

def ep_economics_distribution(qs):
    w, a = filter_clause(qs)
    base = w if w else " WHERE 1=1"
    raw = rows("SELECT modality, total_value_musd v FROM deals" + base + " AND has_total=1", a)
    g = {}
    for r in raw: g.setdefault(r["modality"], []).append(r["v"])
    return {"boxplot": [{"modality": k, "n": len(v), "q": quartiles(v)} for k,v in sorted(g.items())]}

def ep_economics_bubble(qs):
    w, a = filter_clause(qs)
    base = w if w else " WHERE 1=1"
    return {"deals": [boolify(r) for r in rows(
        "SELECT deal_id AS id, date, licensor, licensee, asset, target, modality, indication, stage, deal_type, region, "
        "upfront_musd, total_value_musd, milestone_musd, milestone_derivable FROM deals" + base + " AND has_total=1", a)]}

def ep_economics_milestones(qs):
    w, a = filter_clause(qs)
    base = w if w else " WHERE 1=1"
    return {"milestones": rows("SELECT deal_id AS id, asset, licensor, licensee, upfront_musd, total_value_musd, milestone_musd "
        "FROM deals" + base + " AND milestone_derivable=1 ORDER BY milestone_musd DESC LIMIT 10", a),
        "not_derivable": one("SELECT COUNT(*) n FROM deals" + base + " AND has_total=1 AND milestone_derivable=0", a)["n"]}

def ep_pipeline_modality():
    cats = [r["v"] for r in rows("SELECT DISTINCT modality AS v FROM deals WHERE modality!='' ORDER BY modality")]
    years = [2020,2021,2022,2023,2024,2025,2026]
    grid = rows("SELECT year, modality, COUNT(*) v FROM deals GROUP BY year, modality")
    g = {(r["year"],r["modality"]): r["v"] for r in grid}
    return {"years": years, "series": [{"name": c, "data":[g.get((y,c),0) for y in years]} for c in cats]}

def ep_pipeline_target():
    return rows("SELECT target, COUNT(*) deals FROM deals WHERE target!='' GROUP BY target ORDER BY deals DESC LIMIT 15")

def ep_pipeline_heatmap():
    return rows("SELECT modality, target, COUNT(*) v FROM deals WHERE target!='' GROUP BY modality, target")

def ep_pipeline_assets():
    return rows("SELECT asset, target, modality, indication, stage, licensor, MAX(total_value_musd) total, COUNT(*) deals "
        "FROM deals GROUP BY asset ORDER BY stage, deals DESC LIMIT 50")

def ep_therapy_trends():
    cats = [r["v"] for r in rows("SELECT DISTINCT indication AS v FROM deals WHERE indication!='' ORDER BY indication")]
    years = [2020,2021,2022,2023,2024,2025,2026]
    grid = rows("SELECT year, indication, COUNT(*) v FROM deals GROUP BY year, indication")
    g = {(r["year"],r["indication"]): r["v"] for r in grid}
    return {"years": years, "series": [{"name": c, "data":[g.get((y,c),0) for y in years]} for c in cats]}

def ep_therapy_deep(qs):
    ind = qs.get("indication",["Oncology"])[0]
    w, a = filter_clause(qs)
    cond = (w if w else " WHERE 1=1") + " AND indication=?"
    a2 = a + [ind]
    return {
        "modality": rows("SELECT modality, COUNT(*) v FROM deals"+cond+f" GROUP BY modality ORDER BY v DESC", a2),
        "stage": rows("SELECT stage, COUNT(*) v FROM deals"+cond+f" GROUP BY stage ORDER BY v DESC", a2),
        "companies": rows("SELECT licensor, COUNT(*) deals, COALESCE(SUM(total_value_musd),0) total FROM deals"+cond+f" GROUP BY licensor ORDER BY deals DESC LIMIT 10", a2),
    }

def _med(vals):
    if not vals: return None
    a = sorted(vals); m = len(a)//2
    return round((a[m] if len(a)%2 else (a[m-1]+a[m])/2), 2)

def ep_therapy_opportunity(qs):
    w, a = filter_clause(qs)
    raw = rows("SELECT indication, modality, asset, year, has_total, has_upfront, upfront_musd, total_value_musd FROM deals" + (w or ""), a)
    known = [r for r in raw if r["modality"] and r["modality"] not in ("Other","Unknown")
             and r["indication"] and r["indication"] not in ("Other","Unknown")]
    combos = {}
    for r in known:
        k = r["indication"] + " | " + r["modality"]
        combos.setdefault(k, {"indication": r["indication"], "modality": r["modality"], "list": []})["list"].append(r)
    yrs = sorted({r["year"] for r in known})
    complete = yrs[:-1]; recent3 = complete[-3:]; prev3 = complete[-6:-3]
    tm = []
    for c in combos.values():
        tot_vals = [r["total_value_musd"] for r in c["list"] if r["has_total"]]
        up_vals = [r["upfront_musd"] for r in c["list"] if r["has_upfront"]]
        mt, mu = _med(tot_vals), _med(up_vals)
        if not (mt or mu): continue
        assets = len({r["asset"] for r in c["list"] if r["asset"]})
        discN = len(tot_vals)
        tm.append({"indication": c["indication"], "modality": c["modality"], "n": len(c["list"]),
                   "assets": assets, "total": round(sum(tot_vals),2), "medianTotal": mt, "medianUp": mu,
                   "discN": discN, "discRate": round(discN/len(c["list"])*100) if c["list"] else 0,
                   "r": sum(1 for r in c["list"] if r["year"] in recent3),
                   "p": sum(1 for r in c["list"] if r["year"] in prev3)})
    maxN = max([c["n"] for c in tm] or [1])
    for c in tm:
        c["act"] = round(c["n"]/maxN*100, 1)
        if c["p"] > 0:
            g = (c["r"] - c["p"]) / c["p"]
            c["cat"] = "增长" if g > 0.1 else ("下降" if g < -0.1 else "稳定")
        else:
            c["cat"] = "新兴"
    return {"rows": tm, "years": yrs, "recent3": recent3, "prev3": prev3}

PIPE_MODS = ["ADC","Bispecific","mAb","Small molecule","CAR-T / Cell","Peptide/Protein","Fusion protein","RNA therapy","Other GTx","Vaccine"]
PIPE_STAGES = ["Preclinical","IND approved","Phase I","Phase II","Phase III","Registration","Marketed","Multiple Stages"]
BAD_TARGET = __import__("re").compile(r"未披露|undisclosed|不适用|unknown|待核实|未公开|未具名", __import__("re").I)

def ep_pipeline_aggregates(qs):
    w, a = filter_clause(qs)
    raw = rows("SELECT deal_id AS id, asset, target, modality, indication, stage, licensor, year, has_total, has_upfront, upfront_musd, total_value_musd FROM deals" + (w or ""), a)
    known = [r for r in raw if r["modality"] and r["modality"] not in ("Other","Unknown")
             and r["target"] and r["target"] != "Other" and not BAD_TARGET.search(r["target"] or "")]
    yrs = sorted({r["year"] for r in raw})

    def distinct_assets(lst): return len({r["asset"] for r in lst if r["asset"]})

    tg_map = {}
    for r in known:
        t = tg_map.setdefault(r["target"], {"n":0, "assets":set()})
        t["n"] += 1; t["assets"].add(r["asset"])
    tg_list = sorted(({"target":k,"n":v["n"],"assets":len(v["assets"])} for k,v in tg_map.items()), key=lambda x:-x["n"])
    top_tg = [t["target"] for t in tg_list[:12]]

    md_map = {}
    for r in known:
        m = md_map.setdefault(r["modality"], {"n":0,"tg":set(),"assets":set()})
        m["n"] += 1; m["tg"].add(r["target"]); m["assets"].add(r["asset"])
    md_list = []
    for k in PIPE_MODS:
        m = md_map.get(k, {"n":0,"tg":set(),"assets":set()})
        md_list.append({"modality":k,"n":m["n"],"tg":len(m["tg"]),"assets":len(m["assets"])})
    md_list.sort(key=lambda x:-x["n"])

    combo_map = {}
    for r in known:
        combo_map.setdefault((r["target"], r["modality"]), []).append(r)
    combos = []
    for (tgt, mod), lst in combo_map.items():
        dl = [r for r in lst if r["has_total"]]
        rec = sum(1 for r in lst if r["year"] >= yrs[-2]) if len(yrs)>=2 else len(lst)
        old = sum(1 for r in lst if r["year"] <= yrs[-3]) if len(yrs)>=3 else 0
        combos.append({"target":tgt,"modality":mod,"n":len(lst),"assets":distinct_assets(lst),
                       "total":round(sum(r["total_value_musd"] for r in dl if r["total_value_musd"] is not None),2),
                       "median_total":median([r["total_value_musd"] for r in dl if r["total_value_musd"] is not None]),
                       "median_up":median([r["upfront_musd"] for r in dl if r["upfront_musd"] is not None]),
                       "rec":rec,"old":old,"growth":(rec-old)/old if old>0 else (1 if rec>0 else 0)})
    combos.sort(key=lambda x:-x["n"])

    trend = {k:{y:0 for y in yrs} for k in PIPE_MODS}
    for r in known:
        if r["modality"] in trend and r["year"] in trend[r["modality"]]:
            trend[r["modality"]][r["year"]] += 1
    trend_series = [{"name":k,"data":[trend[k][y] for y in yrs]} for k in PIPE_MODS]

    mat_count = {k:{st:0 for st in PIPE_STAGES} for k in PIPE_MODS}
    mat_assets = {k:{st:set() for st in PIPE_STAGES} for k in PIPE_MODS}
    for r in known:
        if r["modality"] in mat_count and r["stage"] in PIPE_STAGES:
            mat_count[r["modality"]][r["stage"]] += 1
            mat_assets[r["modality"]][r["stage"]].add(r["asset"])
    maturity_count = {k:{st:mat_count[k][st] for st in PIPE_STAGES} for k in PIPE_MODS}
    maturity_assets = {k:{st:len(mat_assets[k][st]) for st in PIPE_STAGES} for k in PIPE_MODS}

    heat_c = {}; heat_a = {}
    for r in known:
        k = (r["modality"], r["target"])
        heat_c[k] = heat_c.get(k,0)+1
        heat_a.setdefault(k,set()).add(r["asset"])
    heat_count = [{"modality":m,"target":t,"v":heat_c.get((m,t),0)} for m in PIPE_MODS for t in top_tg if heat_c.get((m,t),0)>0]
    heat_assets = [{"modality":m,"target":t,"v":len(heat_a.get((m,t),set()))} for m in PIPE_MODS for t in top_tg if heat_a.get((m,t),set())]

    stagebox = []
    for st in PIPE_STAGES:
        vals = [r["total_value_musd"] for r in raw if r["stage"]==st and r["has_total"] and r["total_value_musd"] is not None]
        if vals:
            stagebox.append({"stage":st,"n":len(vals),"q":quartiles(vals)})

    recYrs = yrs[-2:]; prevYrs = yrs[-4:-2]
    recTot = sum(1 for r in known if r["year"] in recYrs) or 1
    prevTot = sum(1 for r in known if r["year"] in prevYrs) or 1
    growth = []
    for k in PIPE_MODS:
        rec = sum(1 for r in known if r["modality"]==k and r["year"] in recYrs)
        prev = sum(1 for r in known if r["modality"]==k and r["year"] in prevYrs)
        growth.append({"modality":k,"rec":rec,"prev":prev,"rec_share":round(rec/recTot*100,1),"prev_share":round(prev/prevTot*100,1),"chg":rec-prev})
    growth.sort(key=lambda x:-x["rec"])

    asset_map = {}
    for r in raw:
        a = asset_map.setdefault(r["asset"], {"asset":r["asset"],"target":r["target"],"modality":r["modality"],
            "indication":r["indication"],"stage":r["stage"],"licensor":r["licensor"],"total":0.0,"n":0})
        a["n"] += 1
        if r["total_value_musd"] is not None:
            a["total"] = max(a["total"], r["total_value_musd"])
    assets = sorted(asset_map.values(), key=lambda x:-x["total"])[:16]

    return {"yrs":yrs, "tg_list":tg_list, "top_tg":top_tg, "md_list":md_list, "mods_shown":PIPE_MODS,
            "combos":combos, "trend":trend_series, "maturity_count":maturity_count, "maturity_assets":maturity_assets,
            "heat_count":heat_count, "heat_assets":heat_assets, "stagebox":stagebox, "growth":growth,
            "rec_years":recYrs, "prev_years":prevYrs, "assets":assets}

def ep_companies_leaderboard(qs):
    side = "licensor" if qs.get("side",["licensor"])[0]=="licensor" else "licensee"
    sort = qs.get("sort",["deals"])[0]
    rows_ = rows(f"SELECT {side} AS name, COUNT(*) deals, COALESCE(SUM(total_value_musd),0) total, "
                 f"COUNT(DISTINCT modality) mods, COUNT(DISTINCT indication) inds FROM deals GROUP BY {side}")
    for r in rows_:
        vals = [x["v"] for x in rows(f"SELECT total_value_musd v FROM deals WHERE {side}=? AND has_total=1", (r["name"],))]
        r["median"] = round(median(vals),2) if vals else None
    key = {"total":"total","median":"median","mods":"mods","inds":"inds"}.get(sort,"deals")
    rows_.sort(key=lambda r: r[key] if r[key] is not None else -1, reverse=True)
    return {"rows": rows_[:12]}

def ep_companies_network():
    nodes = rows("SELECT name, is_chinese, COUNT(*) deals FROM ("
        "SELECT licensor AS name, 1 AS is_chinese FROM deals "
        "UNION ALL SELECT licensee AS name, 0 AS is_chinese FROM deals) GROUP BY name, is_chinese")
    edges = rows("SELECT licensor AS source, licensee AS target, COUNT(*) deals, COALESCE(SUM(total_value_musd),0) value "
        "FROM deals GROUP BY licensor, licensee")
    return {"nodes": nodes, "edges": edges}

def ep_quality(qs):
    total = one("SELECT COUNT(*) n FROM deals")["n"]
    per_year = rows("SELECT year, COUNT(*) rows, SUM(has_upfront) up_n, SUM(has_total) tot_n FROM deals GROUP BY year ORDER BY year")
    conf = rows("SELECT confidence, COUNT(*) n FROM deals GROUP BY confidence ORDER BY n DESC")
    return {
        "total": total,
        "per_year": per_year,
        "confidence": conf,
        "disclosure": {
            "upfront_disclosed": one("SELECT COUNT(*) n FROM deals WHERE has_upfront=1")["n"],
            "total_disclosed": one("SELECT COUNT(*) n FROM deals WHERE has_total=1")["n"],
            "milestone_derivable": one("SELECT COUNT(*) n FROM deals WHERE milestone_derivable=1")["n"],
            "milestone_not_derivable": one("SELECT COUNT(*) n FROM deals WHERE has_total=1 AND milestone_derivable=0")["n"],
            "stage_unknown": one("SELECT COUNT(*) n FROM deals WHERE stage='Unknown'")["n"],
            "confidence_unknown": one("SELECT COUNT(*) n FROM deals WHERE confidence='unknown'")["n"],
        },
    }

ENDPOINTS = {
    "/api/meta": lambda qs: ep_meta(),
    "/api/deals": ep_deals,
    "/api/overview/kpis": ep_overview_kpis,
    "/api/overview/trends": ep_overview_trends,
    "/api/geo/territory": ep_geo,
    "/api/geo/countries": ep_geo_countries,
    "/api/economics/snapshot": ep_economics_snapshot,
    "/api/economics/activity-value-trends": ep_economics_trends,
    "/api/economics/distribution": ep_economics_distribution,
    "/api/economics/bubble": ep_economics_bubble,
    "/api/economics/milestones": ep_economics_milestones,
    "/api/pipeline/modality-trend": lambda qs: ep_pipeline_modality(),
    "/api/pipeline/target-rank": lambda qs: ep_pipeline_target(),
    "/api/pipeline/target-modality-heatmap": lambda qs: ep_pipeline_heatmap(),
    "/api/pipeline/assets": lambda qs: ep_pipeline_assets(),
    "/api/therapy/area-trends": lambda qs: ep_therapy_trends(),
    "/api/therapy/deep-dive": ep_therapy_deep,
    "/api/therapy/opportunity-matrix": ep_therapy_opportunity,
    "/api/pipeline/aggregates": ep_pipeline_aggregates,
    "/api/quality": ep_quality,
    "/api/companies/leaderboard": ep_companies_leaderboard,
    "/api/companies/network": lambda qs: ep_companies_network(),
}

class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers(); self.wfile.write(body)
    def _static(self, path):
        rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        full = os.path.normpath(os.path.join(DEMO_DIR, rel))
        if not full.startswith(os.path.normpath(DEMO_DIR)): return self.send_error(403)
        if not os.path.isfile(full): return self.send_error(404)
        data = open(full, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        p = urlparse(self.path); qs = parse_qs(p.query)
        key = p.path + ("?" + p.query if p.query else "")
        if p.path.startswith("/api/landscape/"):
            dim = p.path.rsplit("/",1)[-1]
            try: return self._json(cached(key, lambda: ep_landscape(qs, dim)))
            except Exception as e: return self._json({"error": str(e)}, 500)
        if p.path == "/api/deals/export":
            try:
                body = ep_deals_csv(qs).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="deals_export.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
            except Exception as e:
                return self._json({"error": str(e)}, 500)
        fn = ENDPOINTS.get(p.path)
        if fn:
            try:
                if p.path == "/api/deals":
                    return self._json(fn(qs))
                return self._json(cached(key, lambda: fn(qs)))
            except Exception as e: return self._json({"error": str(e)}, 500)
        return self._static(p.path)
    def log_message(self, fmt, *args): pass

if __name__ == "__main__":
    ensure_db()
    print(f"Serving on http://{HOST}:{PORT}/  (静态 demo + /api/*)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()