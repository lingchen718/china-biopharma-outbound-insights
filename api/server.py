#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 API + 静态站点服务（仅用 Python 标准库）。"""
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

def _rows(sql, args=()):
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]

def boolify(row):
    for k in ("milestone_derivable", "has_upfront", "has_total"):
        if k in row:
            row[k] = bool(row[k])
    return row

def endpoint_deals(qs):
    where, args = [], []
    if "year_from" in qs:
        where.append("year >= ?"); args.append(int(qs["year_from"][0]))
    if "year_to" in qs:
        where.append("year <= ?"); args.append(int(qs["year_to"][0]))
    if "q" in qs:
        like = "%" + qs["q"][0] + "%"
        where.append("(licensor LIKE ? OR licensee LIKE ? OR asset LIKE ? OR target LIKE ? OR indication LIKE ?)")
        args += [like] * 5
    sql = ("SELECT deal_id AS id, date, year, licensor, licensee, asset, target, "
           "modality, indication, stage, deal_type, region, territory, confidence, currency, fx_rate, "
           "upfront, total_value, upfront_musd, total_value_musd, milestone_musd, milestone_derivable, "
           "has_upfront, has_total, value_disclosure, source_name, source_title, source_url, publish_date, analyst_note "
           "FROM deals")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date DESC"
    return {"deals": [boolify(r) for r in _rows(sql, args)]}

def endpoint_kpis():
    sql = ("SELECT COUNT(*) AS total_deals, "
           "COALESCE(SUM(total_value_musd),0) AS total_value, "
           "COALESCE(MAX(total_value_musd),0) AS highest_deal, "
           "COALESCE(SUM(upfront_musd),0) AS total_upfront, "
           "COUNT(DISTINCT licensor) AS licensors, "
           "COUNT(DISTINCT licensee) AS licensees FROM deals")
    with connect() as conn:
        return dict(conn.execute(sql).fetchone())

def endpoint_geo():
    sql = ("SELECT region, COUNT(*) AS deals, COALESCE(SUM(total_value_musd),0) AS value "
           "FROM deals GROUP BY region ORDER BY deals DESC LIMIT 8")
    return _rows(sql)

def endpoint_trends(qs):
    gran = qs.get("granularity", ["year"])[0]
    if gran == "quarter":
        pexpr = "strftime('%Y', date) || '-Q' || ((CAST(strftime('%m', date) AS INTEGER)+2)/3)"
    elif gran == "month":
        pexpr = "strftime('%Y-%m', date)"
    else:
        gran = "year"; pexpr = "strftime('%Y', date)"
    sql = (f"SELECT {pexpr} AS period, COUNT(*) AS deals, "
           "SUM(has_upfront) AS up_n, COALESCE(SUM(CASE WHEN has_upfront=1 THEN upfront_musd END),0) AS upfront, "
           "SUM(has_total) AS tot_n, COALESCE(SUM(CASE WHEN has_total=1 THEN total_value_musd END),0) AS total_value "
           "FROM deals GROUP BY period ORDER BY period")
    rows = _rows(sql)
    by = {r["period"]: r for r in rows}
    def prev(k):
        if gran == "year":
            return str(int(k) - 1)
        if gran == "quarter":
            y, q = k.split("-Q"); return f"{int(y)-1}-Q{q}"
        y, m = k.split("-"); return f"{int(y)-1}-{m}"
    for r in rows:
        p = by.get(prev(r["period"]))
        for metric, key in (("deals", "count_yoy"), ("upfront", "upfront_yoy"), ("total_value", "total_yoy")):
            r[key] = round((r[metric] - p[metric]) / p[metric] * 100, 1) if (p and p[metric]) else None
    return {"granularity": gran, "rows": rows}

def endpoint_meta():
    enums = {}
    for dim in ["modality", "indication", "stage", "deal_type", "region"]:
        enums[dim] = [r[0] for r in _rows(f"SELECT DISTINCT {dim} FROM deals WHERE {dim} IS NOT NULL AND {dim} != '' ORDER BY {dim}")]
    return {"total_rows": len(_rows("SELECT deal_id FROM deals")), "enums": enums}

class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        full = os.path.normpath(os.path.join(DEMO_DIR, rel))
        if not full.startswith(os.path.normpath(DEMO_DIR)):
            self.send_error(403); return
        if not os.path.isfile(full):
            self.send_error(404); return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        data = open(full, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path
        if path == "/api/deals":
            return self._json(endpoint_deals(qs))
        if path == "/api/overview/kpis":
            return self._json(endpoint_kpis())
        if path == "/api/geo/territory":
            return self._json(endpoint_geo())
        if path == "/api/economics/activity-value-trends":
            return self._json(endpoint_trends(qs))
        if path == "/api/meta":
            return self._json(endpoint_meta())
        return self._static(path)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    ensure_db()
    print(f"Serving on http://127.0.0.1:{PORT}/  (静态 demo + /api/*)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()