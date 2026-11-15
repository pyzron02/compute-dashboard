"""Facts / speculation / perception views for the dashboard, built from data/tidy and data/manual.

Every block carries its rows plus the source of each, so the page only draws. A block whose
data has not been collected yet comes back empty, and the page says so instead of drawing.
"""

import datetime as dt
from collections import defaultdict

from analysis.report import read_csv

def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def quarter_label(end):
    """Calendar quarter containing a period end date. Oracle's fiscal quarters end a month
    before calendar ones (e.g. Aug 31), so its figures sit in the quarter they end in."""
    d = dt.date.fromisoformat(end)
    return f"{d.year} Q{(d.month - 1) // 3 + 1}"


def capex(sec):
    """Quarterly hyperscaler capex in $B by calendar quarter, plus year-on-year change of the total."""
    by = defaultdict(dict)
    for r in sec:
        if r["metric"] == "capex" and r["ticker"] in ("MSFT", "GOOGL", "AMZN", "META", "ORCL"):
            by[quarter_label(r["period_end"])][r["ticker"]] = round(float(r["usd"]) / 1e9, 2)
    quarters = sorted(by)
    totals = {q: sum(by[q].values()) for q in quarters}
    rows = []
    for q in quarters:
        y, n = q.split(" ")
        prev = totals.get(f"{int(y) - 1} {n}")
        complete = len(by[q]) == 5
        rows.append({"quarter": q, "by_company": by[q], "total": round(totals[q], 2), "complete": complete,
                     "yoy": round(totals[q] / prev - 1, 4) if prev and complete else None})
    return rows


def funding(sec, manual):
    """Per company and quarter: debt, cash, deferred revenue (prepayments), interest, operating income, in $B."""
    out = defaultdict(lambda: defaultdict(dict))
    for r in sec:
        if r["ticker"] in ("CRWV", "APLD", "IREN"):
            out[r["ticker"]][r["period_end"]][r["metric"]] = float(r["usd"]) / 1e9
    for r in manual:
        out[r["ticker"]][r["period_end"]][r["metric"]] = float(r["usd"]) / 1e9
    rows = []
    for ticker, periods in out.items():
        for end, m in sorted(periods.items()):
            debt = m.get("debt", 0) + m.get("debt_current", 0) if ("debt" in m or "debt_current" in m) else None
            deferred = m.get("deferred_revenue")
            if deferred is None and ("deferred_revenue_current" in m or "deferred_revenue_noncurrent" in m):
                deferred = m.get("deferred_revenue_current", 0) + m.get("deferred_revenue_noncurrent", 0)
            rows.append({"ticker": ticker, "period_end": end, "quarter": quarter_label(end),
                         "debt": _r(debt), "cash": _r(m.get("cash")), "deferred_revenue": _r(deferred),
                         "interest_expense": _r(m.get("interest_expense")),
                         "operating_income": _r(m.get("operating_income"))})
    return sorted(rows, key=lambda r: (r["ticker"], r["period_end"]))


def _r(x, n=3):
    return None if x is None else round(x, n)


def tsmc(collected, seed):
    by = {r["month"]: r for r in seed}
    by.update({r["month"]: r for r in collected})   # filed 6-Ks win over the seed
    months = sorted(by)
    rows = []
    for i, m in enumerate(months):
        window = [float(by[x]["ntd_million"]) for x in months[max(0, i - 2): i + 1]]
        rows.append({"month": m, "ntd_billion": round(float(by[m]["ntd_million"]) / 1000, 1),
                     "avg3": round(sum(window) / len(window) / 1000, 1) if len(window) == 3 else None,
                     "url": by[m]["url"]})
    return rows


def guidance(rows):
    """Scorecard rows (those with an outcome) and revision ranges grouped by company + item."""
    scorecard = [{**r, "low": _f(r["low"]), "high": _f(r["high"]), "actual": _f(r["actual"])}
                 for r in rows if r["outcome"]]
    revisions = defaultdict(list)
    for r in rows:
        if r["guided_on"]:
            revisions[f"{r['company']}: {r['item']}"].append(
                {"guided_on": r["guided_on"], "low": _f(r["low"]), "high": _f(r["high"]), "unit": r["unit"], "url": r["url"]})
    revs = [{"label": k, "points": sorted(v, key=lambda p: p["guided_on"])} for k, v in revisions.items() if len(v) > 1]
    return scorecard, revs


def latest_close(prices, symbol):
    rows = sorted((r for r in prices if r["symbol"] == symbol), key=lambda r: r["date"])
    return {"date": rows[-1]["date"], "close": float(rows[-1]["close"])} if rows else None


def basket(prices, start_days=180):
    """Each stock indexed to 100 at the first common date in the window, plus an equal-weight neocloud basket."""
    if not prices:
        return {"start": None, "series": []}
    end = max(r["date"] for r in prices)
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=start_days)).isoformat()
    by = defaultdict(dict)
    for r in prices:
        if r["date"] >= start:
            by[r["symbol"]][r["date"]] = float(r["close"])
    common = sorted(set.intersection(*(set(v) for v in by.values()))) if by else []
    if not common:
        return {"start": None, "series": []}
    base = common[0]
    series = [{"symbol": s, "points": [[d, round(v / by[s][base] * 100, 2)] for d, v in sorted(by[s].items()) if d >= base]}
              for s in sorted(by)]
    neo = [s for s in by if s != "NVDA"]
    pts = [[d, round(sum(by[s][d] / by[s][base] for s in neo) / len(neo) * 100, 2)] for d in common]
    series.insert(0, {"symbol": "Neocloud basket", "points": pts})
    return {"start": base, "series": series}


def short_share(rows, window=5):
    """Short volume over total volume, as a trailing 5-trading-day ratio (daily values are noisy)."""
    by = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["date"]):
        by[r["symbol"]].append((r["date"], float(r["short_volume"]), float(r["total_volume"])))
    out = []
    for s, days in sorted(by.items()):
        pts = []
        for i in range(window - 1, len(days)):
            w = days[i - window + 1: i + 1]
            tot = sum(d[2] for d in w)
            if tot:
                pts.append([days[i][0], round(sum(d[1] for d in w) / tot, 4)])
        out.append({"symbol": s, "points": pts})
    return out


def series_by(rows, key, value, date="date"):
    by = defaultdict(list)
    for r in sorted(rows, key=lambda r: r[date]):
        by[r[key]].append([r[date], float(r[value])])
    return [{"name": k, "points": v} for k, v in by.items()]


def build_markets(data_dir, scarcity):
    t, m = data_dir / "tidy", data_dir / "manual"
    sec = read_csv(t / "sec_quarterly.csv")
    prices = read_csv(t / "stock_prices.csv")
    scorecard, revisions = guidance(read_csv(m / "guidance.csv"))
    targets = read_csv(m / "analyst_targets.csv")
    for r in targets:
        r["usd"] = float(r["usd"])
    b300 = [[s["date"], s["ratio"]] for s in scarcity if s["provider"] == "Nebius" and s["gpu"] == "B300"]
    deals = read_csv(m / "deals.csv")
    return {
        "facts": {
            "capex": capex(sec),
            "funding": funding(sec, read_csv(m / "funding_manual.csv")),
            "deals": [{**d, "usd_m_per_mw_year": float(d["usd_m_per_mw_year"])} for d in deals],
            "capacity": [{**c, "contracted_gw": _f(c["contracted_gw"]), "live_gw": _f(c["live_gw"])}
                         for c in read_csv(m / "capacity.csv")],
            "sites": sorted(read_csv(m / "site_events.csv"), key=lambda r: r["date"]),
            "tsmc": tsmc(read_csv(t / "tsmc_revenue.csv"), read_csv(m / "tsmc_revenue_seed.csv")),
        },
        "speculation": {
            "scorecard": scorecard,
            "revisions": revisions,
            "targets": targets,
            "target_prices": {s: latest_close(prices, s) for s in sorted({r["symbol"] for r in targets})},
            "rumours": sorted(read_csv(m / "rumours.csv"), key=lambda r: r["first_reported"], reverse=True),
            "implied_moves": [{**r, "implied_pct": _f(r["implied_pct"]), "actual_pct": _f(r["actual_pct"])}
                              for r in read_csv(m / "implied_moves.csv")],
        },
        "perception": {
            "basket": basket(prices),
            "b300_ratio": b300,
            "deal_points": [[d["date"], float(d["usd_m_per_mw_year"])] for d in deals
                            if d["neocloud"] in ("Nebius", "CoreWeave", "IREN")],
            "attention": series_by(read_csv(t / "news_attention.csv"), "query", "volume_pct"),
            "short_share": short_share(read_csv(t / "short_volume.csv")),
            "credit_spread": series_by(read_csv(t / "credit_spread.csv"), "series", "pct"),
            "narratives": [{**n, "evidence_score": float(n["evidence_score"]),
                            "price_impact_score": float(n["price_impact_score"])} for n in read_csv(m / "narratives.csv")],
        },
        "not_built": [
            {"chart": "Forward GPU prices (futures curve)",
             "why": "No free, redistributable source of GPU forward prices was found; exchange data is licensed."},
            {"chart": "Google Trends search interest",
             "why": "Google offers no public API and its terms bar automated collection; GDELT news counts are used instead."},
            {"chart": "Stocktwits retail sentiment",
             "why": "Its terms do not allow republishing the data on a public page."},
        ],
    }


MARKET_SOURCES = [
    {"name": "Hyperscaler capex and neocloud funding stack (debt, cash, deferred revenue, interest, operating income)",
     "origin": "SEC EDGAR XBRL company facts API (public, no key)", "url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
     "collector": "collectors/markets.py", "cadence": "Daily check; changes when a 10-Q or 10-K is filed", "file": "data/tidy/sec_quarterly.csv"},
    {"name": "Nebius funding figures (files 6-K without quarterly XBRL)", "origin": "Nebius Q3 2026 results tables, entered by hand",
     "url": "https://www.stocktitan.net/news/NBIS/nebius-reports-third-quarter-2026-financial-4dtv2j8ebv4v.html",
     "collector": "data/manual/funding_manual.csv", "cadence": "Manual, each quarter", "file": "data/manual/funding_manual.csv"},
    {"name": "TSMC monthly revenue", "origin": "TSMC monthly revenue 6-K filings on SEC EDGAR; 2026 history from TSMC investor relations",
     "url": "https://investor.tsmc.com/english/monthly-revenue/2026", "collector": "collectors/markets.py",
     "cadence": "Daily check; TSMC reports around the 10th", "file": "data/tidy/tsmc_revenue.csv, data/manual/tsmc_revenue_seed.csv"},
    {"name": "US high-yield credit spread", "origin": "ICE BofA US High Yield Index OAS via FRED (BAMLH0A0HYM2)",
     "url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "collector": "collectors/markets.py", "cadence": "Daily",
     "file": "data/tidy/credit_spread.csv"},
    {"name": "Short share of daily volume", "origin": "FINRA Reg SHO daily short sale volume files (consolidated NMS)",
     "url": "https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files",
     "collector": "collectors/markets.py", "cadence": "Daily", "file": "data/tidy/short_volume.csv"},
    {"name": "News attention for \"AI bubble\" and neoclouds", "origin": "GDELT DOC 2.0 API, share of monitored news coverage",
     "url": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/", "collector": "collectors/markets.py", "cadence": "Daily",
     "file": "data/tidy/news_attention.csv"},
    {"name": "Daily closing prices (NBIS, CRWV, IREN, APLD, NVDA), shown only as an index", "origin": "Yahoo Finance public chart endpoint (daily closes)",
     "url": "https://finance.yahoo.com/", "collector": "collectors/markets.py", "cadence": "Daily", "file": "data/tidy/stock_prices.csv"},
    {"name": "Deals ($/MW), capacity, site events, guidance, rumours, analyst targets, implied moves, narrative scores",
     "origin": "Hand-entered, one source link per row", "url": "https://github.com/pyzron02/compute-dashboard/tree/main/data/manual",
     "collector": "data/manual/*.csv", "cadence": "Manual", "file": "data/manual/"},
]
