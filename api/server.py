#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 API + 静态站点服务（仅标准库）。聚合逻辑全部在服务端 SQL/内存完成。"""
import json, mimetypes, os, sqlite3, subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "db", "app.db")
DEMO_DIR = os.path.join(ROOT, "demo")
PORT = 8090

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
    for k, col in (("deal_type","deal_type"),("modality","modality"),("indication","indication"),("stage","stage"),("region","region")):
        if k in qs:
            vals = [x for x in qs[k][0].split(",") if x]
            if vals:
                where.append(col + " IN (" + ",".join("?"*len(vals)) + ")"); args += vals
    if "q" in qs:
        like = "%" + qs["q"][0] + "%"
        where.append("(licensor LIKE ? OR licensee LIKE ? OR asset LIKE ? OR target LIKE ? OR indication LIKE ?)")
        args += [like]*5
    return (" WHERE " + " AND ".join(where) if where else "", args)

# ---------- 页面聚合 ----------
def ep_meta():
    enums = {}
    for dim in ["modality","indication","stage","deal_type","region"]:
        enums[dim] = [r["v"] for r in rows(f"SELECT DISTINCT {dim} AS v FROM deals WHERE {dim} IS NOT NULL AND {dim}!='' ORDER BY {dim}")]
    return {"total_rows": len(rows("SELECT deal_id FROM deals")), "enums": enums}

def ep_deals(qs):
    w, a = filter_clause(qs)
    limit = int(qs.get("limit",[0])[0]) or None
    sql = ("SELECT deal_id AS id, date, year, licensor, licensee, asset, target, modality, indication, stage, "
           "deal_type, region, territory, confidence, upfront_musd, total_value_musd, milestone_musd, milestone_derivable, "
           "has_upfront, has_total, value_disclosure, source_name, source_title, source_url, publish_date, analyst_note "
           "FROM deals" + w + " ORDER BY date DESC")
    if limit: sql += " LIMIT " + str(limit)
    return {"deals": [boolify(r) for r in rows(sql, a)]}

def ep_overview_kpis():
    sql = ("SELECT COUNT(*) AS total_deals, COALESCE(SUM(total_value_musd),0) AS total_value, "
           "COALESCE(MAX(total_value_musd),0) AS highest_deal, COALESCE(SUM(upfront_musd),0) AS total_upfront, "
           "COUNT(DISTINCT licensor) AS licensors, COUNT(DISTINCT licensee) AS licensees FROM deals")
    return one(sql)

def ep_overview_trends(qs):
    metric = qs.get("metric",["count"])[0]
    dim = qs.get("dim",["modality"])[0]
    val = {"count":"COUNT(*)","upfront":"COALESCE(SUM(CASE WHEN has_upfront=1 THEN upfront_musd END),0)",
           "total":"COALESCE(SUM(CASE WHEN has_total=1 THEN total_value_musd END),0)"}.get(metric, "COUNT(*)")
    cats = [r["v"] for r in rows(f"SELECT DISTINCT {dim} AS v FROM deals WHERE {dim} IS NOT NULL AND {dim}!='' ORDER BY {dim}")]
    years = [2020,2021,2022,2023,2024,2025,2026]
    grid = rows(f"SELECT year, {dim} AS dim, {val} AS v FROM deals GROUP BY year, {dim}")
    g = {(r["year"], r["dim"]): r["v"] for r in grid}
    series = [{"name": c, "data": [g.get((y,c),0) for y in years]} for c in cats]
    return {"years": years, "categories": cats, "series": series}

def ep_geo():
    return rows("SELECT region, COUNT(*) AS deals, COALESCE(SUM(total_value_musd),0) AS value FROM deals GROUP BY region ORDER BY deals DESC LIMIT 8")

def ep_landscape(qs, dim):
    if dim not in ("modality","indication","stage","deal_type"): dim = "modality"
    w, a = filter_clause(qs)
    base = w if w else " WHERE 1=1"
    total = one("SELECT COUNT(*) AS n FROM deals"+base, a)["n"]
    counts = rows(f"SELECT {dim} AS key, COUNT(*) AS value FROM deals"+base+f" GROUP BY {dim} ORDER BY value DESC", a)
    up = rows(f"SELECT {dim} AS key, SUM(upfront_musd) AS value FROM deals"+base+" AND has_upfront=1"+f" GROUP BY {dim} ORDER BY value DESC", a)
    up_n = one("SELECT COUNT(*) AS n FROM deals"+base+" AND has_upfront=1", a)["n"]
    return {"total": total, "coverage": round(up_n/total*100) if total else 0, "counts": counts, "upfront": up}

def ep_economics_snapshot():
    return {
        "upfront_deals": one("SELECT COUNT(*) n FROM deals WHERE has_upfront=1")["n"],
        "total_deals_count": one("SELECT COUNT(*) n FROM deals WHERE has_total=1")["n"],
        "total_rows": one("SELECT COUNT(*) n FROM deals")["n"],
        "total_upfront": one("SELECT COALESCE(SUM(upfront_musd),0) v FROM deals WHERE has_upfront=1")["v"],
        "median_upfront": median([r["v"] for r in rows("SELECT upfront_musd v FROM deals WHERE has_upfront=1")]),
        "total_value": one("SELECT COALESCE(SUM(total_value_musd),0) v FROM deals WHERE has_total=1")["v"],
    }

def ep_economics_trends(qs):
    gran = qs.get("granularity",["year"])[0]
    if gran=="quarter": pexpr = "strftime('%Y', date) || '-Q' || ((CAST(strftime('%m', date) AS INTEGER)+2)/3)"
    elif gran=="month": pexpr = "strftime('%Y-%m', date)"
    else: gran="year"; pexpr = "strftime('%Y', date)"
    data = rows(f"SELECT {pexpr} AS period, COUNT(*) AS deals, SUM(has_upfront) AS up_n, "
                "COALESCE(SUM(CASE WHEN has_upfront=1 THEN upfront_musd END),0) AS upfront, "
                "SUM(has_total) AS tot_n, COALESCE(SUM(CASE WHEN has_total=1 THEN total_value_musd END),0) AS total_value "
                "FROM deals GROUP BY period ORDER BY period")
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

def ep_economics_distribution():
    raw = rows("SELECT modality, total_value_musd v FROM deals WHERE has_total=1")
    g = {}
    for r in raw: g.setdefault(r["modality"], []).append(r["v"])
    return {"boxplot": [{"modality": k, "n": len(v), "q": quartiles(v)} for k,v in sorted(g.items())]}

def ep_economics_bubble():
    return {"deals": [boolify(r) for r in rows(
        "SELECT deal_id AS id, date, licensor, licensee, asset, target, modality, indication, stage, deal_type, region, "
        "upfront_musd, total_value_musd, milestone_musd, milestone_derivable FROM deals WHERE has_total=1")]}

def ep_economics_milestones():
    return {"milestones": rows("SELECT deal_id AS id, asset, licensor, licensee, upfront_musd, total_value_musd, milestone_musd "
        "FROM deals WHERE milestone_derivable=1 ORDER BY milestone_musd DESC LIMIT 10"),
        "not_derivable": one("SELECT COUNT(*) n FROM deals WHERE has_total=1 AND milestone_derivable=0")["n"]}

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

ENDPOINTS = {
    "/api/meta": lambda qs: ep_meta(),
    "/api/deals": ep_deals,
    "/api/overview/kpis": lambda qs: ep_overview_kpis(),
    "/api/overview/trends": ep_overview_trends,
    "/api/geo/territory": lambda qs: ep_geo(),
    "/api/economics/snapshot": lambda qs: ep_economics_snapshot(),
    "/api/economics/activity-value-trends": ep_economics_trends,
    "/api/economics/distribution": lambda qs: ep_economics_distribution(),
    "/api/economics/bubble": lambda qs: ep_economics_bubble(),
    "/api/economics/milestones": lambda qs: ep_economics_milestones(),
    "/api/pipeline/modality-trend": lambda qs: ep_pipeline_modality(),
    "/api/pipeline/target-rank": lambda qs: ep_pipeline_target(),
    "/api/pipeline/target-modality-heatmap": lambda qs: ep_pipeline_heatmap(),
    "/api/pipeline/assets": lambda qs: ep_pipeline_assets(),
    "/api/therapy/area-trends": lambda qs: ep_therapy_trends(),
    "/api/therapy/deep-dive": ep_therapy_deep,
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
        if p.path.startswith("/api/landscape/"):
            return self._json(ep_landscape(qs, p.path.rsplit("/",1)[-1]))
        fn = ENDPOINTS.get(p.path)
        if fn:
            try: return self._json(fn(qs))
            except Exception as e: return self._json({"error": str(e)}, 500)
        return self._static(p.path)
    def log_message(self, fmt, *args): pass

if __name__ == "__main__":
    ensure_db()
    print(f"Serving on http://127.0.0.1:{PORT}/  (静态 demo + /api/*)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()