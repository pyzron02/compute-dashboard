"""Market and funding series for the facts / speculation / perception views. Free sources only.

Each source is collected independently: one failing does not stop the others, but the run exits
non-zero so the workflow shows it. Raw responses are not stored (some are large); every tidy
row keeps enough to trace it back to its source.

Sources and outputs:
  SEC EDGAR XBRL company facts (no key)  -> data/tidy/sec_quarterly.csv
      hyperscaler capex (MSFT, GOOGL, AMZN, META, ORCL) and the neocloud funding stack
      (CRWV, APLD, IREN): debt, cash, deferred revenue, interest expense, operating income
  SEC EDGAR TSMC 6-K monthly revenue reports (no key) -> data/tidy/tsmc_revenue.csv
  FRED fredgraph CSV (no key)            -> data/tidy/credit_spread.csv
      ICE BofA US High Yield option-adjusted spread (BAMLH0A0HYM2)
  FINRA Reg SHO daily short volume (no key) -> data/tidy/short_volume.csv
  GDELT DOC 2.0 timeline (no key; covers a rolling 3 months, so history is kept by appending) -> data/tidy/news_attention.csv
  Yahoo Finance chart endpoint (no key)  -> data/tidy/stock_prices.csv (shown only as an index)

Set SEC_USER_AGENT (e.g. a repository secret) to "<name> <contact email>" if SEC refuses the default.
Usage: python -m collectors.markets [--only sec,tsmc,fred,finra,gdelt,prices] [--data-dir data] [--dry-run]
"""

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from collectors.common import append_tidy

# SEC asks automated clients to identify themselves; this names the project, not a person.
SEC_UA = os.environ.get("SEC_USER_AGENT") or "compute-dashboard actions@users.noreply.github.com"
WEB_UA = "compute-dashboard/1.0 (+https://github.com/pyzron02/compute-dashboard)"

HYPERSCALERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]
NEOCLOUDS = ["CRWV", "APLD", "IREN"]
BASKET = ["NBIS", "CRWV", "IREN", "APLD", "NVDA"]

# Metric -> XBRL concepts tried in order (companies tag the same line differently).
CONCEPTS = {
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForProceedsFromProductiveAssets"],
    "debt": ["LongTermDebt", "LongTermDebtNoncurrent", "DebtInstrumentCarryingAmount"],
    "debt_current": ["LongTermDebtCurrent", "DebtCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "deferred_revenue": ["ContractWithCustomerLiability"],
    "deferred_revenue_current": ["ContractWithCustomerLiabilityCurrent"],
    "deferred_revenue_noncurrent": ["ContractWithCustomerLiabilityNoncurrent"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "operating_income": ["OperatingIncomeLoss"],
}
FLOW = {"capex", "interest_expense", "operating_income"}   # duration items; the rest are balances
METRICS = {t: ["capex"] for t in HYPERSCALERS}
METRICS.update({t: list(CONCEPTS) for t in NEOCLOUDS})

SEC_FIELDS = ["ticker", "metric", "concept", "period_end", "usd", "form", "filed"]
TSMC_FIELDS = ["month", "ntd_million", "filed", "url"]
SPREAD_FIELDS = ["date", "series", "pct"]
SHORT_FIELDS = ["date", "symbol", "short_volume", "total_volume"]
NEWS_FIELDS = ["date", "query", "volume_pct"]
PRICE_FIELDS = ["date", "symbol", "close", "source"]

NEWS_QUERIES = ['"AI bubble"', 'neocloud OR neoclouds']
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def fetch(url, ua=WEB_UA, timeout=60, retries=3):
    """GET a URL as text. Retries 429/5xx with backoff; on a final error, prints the start of
    the response body so the workflow log shows why (e.g. a block page)."""
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate", "Accept": "*/*"}
    if "sec.gov" in url:
        headers["Host"] = urllib.parse.urlsplit(url).netloc
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < retries:
                time.sleep(10 * (attempt + 1))
                continue
            body = e.read()
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            text = re.sub(r"<[^>]+>|\s+", " ", body.decode("utf-8", "replace"))[:300]
            print(f"HTTP {e.code} from {url}: {text}", file=sys.stderr)
            raise


# --- SEC ---------------------------------------------------------------------------------

def cik_map(tickers_json):
    return {v["ticker"].upper(): f"{int(v['cik_str']):010d}" for v in tickers_json.values()}


def _days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def quarterly_flows(entries):
    """Quarterly values from 10-Q/10-K duration facts, which are often year-to-date.

    Facts sharing a start date are YTD steps of one fiscal year: each quarter is the
    difference between consecutive steps. A ~3-month fact is used as is.
    """
    latest = {}
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K") or "start" not in e:
            continue
        k = (e["start"], e["end"])
        if k not in latest or e["filed"] > latest[k]["filed"]:
            latest[k] = e
    out = {}
    by_start = defaultdict(list)
    for (start, end), e in latest.items():
        by_start[start].append(e)
    for start, es in by_start.items():
        es.sort(key=lambda e: e["end"])
        prev = None
        for e in es:
            span = _days(start, e["end"])
            if 80 <= span <= 100:
                out[e["end"]] = (e["val"], e)
            elif prev is not None and 80 <= _days(prev["end"], e["end"]) <= 100:
                out.setdefault(e["end"], (e["val"] - prev["val"], e))
            prev = e
    return out


def balances(entries):
    latest = {}
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K") or "start" in e:
            continue
        if e["end"] not in latest or e["filed"] > latest[e["end"]]["filed"]:
            latest[e["end"]] = e
    return {end: (e["val"], e) for end, e in latest.items()}


def parse_companyfacts(ticker, facts, metrics, since="2023-01-01"):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    rows = []
    for metric in metrics:
        for concept in CONCEPTS[metric]:
            entries = gaap.get(concept, {}).get("units", {}).get("USD", [])
            if not entries:
                continue
            series = quarterly_flows(entries) if metric in FLOW else balances(entries)
            series = {k: v for k, v in series.items() if k >= since}
            if not series:
                continue
            rows += [{"ticker": ticker, "metric": metric, "concept": concept, "period_end": end,
                      "usd": round(val), "form": e["form"], "filed": e["filed"]}
                     for end, (val, e) in sorted(series.items())]
            break
    return rows


def collect_sec(data_dir, dry_run=False):
    ciks = cik_map(json.loads(fetch("https://www.sec.gov/files/company_tickers.json", SEC_UA)))
    rows, missing = [], []
    for ticker, metrics in METRICS.items():
        if ticker not in ciks:
            missing.append(ticker)
            continue
        facts = json.loads(fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[ticker]}.json", SEC_UA))
        got = parse_companyfacts(ticker, facts, metrics)
        if not got:
            missing.append(ticker)
        rows += got
    print(f"sec: {len(rows)} rows; no data for {missing or 'none'}")
    if not dry_run:
        append_tidy(data_dir / "tidy" / "sec_quarterly.csv", rows, SEC_FIELDS, key=("ticker", "metric", "period_end"))
    return rows


# --- TSMC monthly revenue (6-K on EDGAR) --------------------------------------------------

TSMC_CIK = "0001046179"
TSMC_RE = re.compile(
    r"(?:revenue for\s+)?(" + "|".join(MONTHS) + r")\s+(\d{4})\s+(?:revenue\s+)?(?:was|were|of)\s+approximately\s+"
    r"NT\$\s*([\d,]+(?:\.\d+)?)\s*billion", re.I)


def parse_tsmc(text):
    """(YYYY-MM, NT$ million) from a TSMC monthly revenue report, or None."""
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"&nbsp;|&#160;", " ", plain)
    plain = re.sub(r"\s+", " ", plain)
    m = TSMC_RE.search(plain)
    if not m:
        return None
    month = MONTHS.index(m.group(1).capitalize()) + 1
    return f"{int(m.group(2)):04d}-{month:02d}", round(float(m.group(3).replace(",", "")) * 1000)


def collect_tsmc(data_dir, dry_run=False, limit=6):
    subs = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{TSMC_CIK}.json", SEC_UA))
    recent = subs["filings"]["recent"]
    rows = []
    for form, acc, doc, filed in zip(recent["form"], recent["accessionNumber"], recent["primaryDocument"], recent["filingDate"]):
        if form != "6-K" or "revenue" not in doc.lower():
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(TSMC_CIK)}/{acc.replace('-', '')}/{doc}"
        got = parse_tsmc(fetch(url, SEC_UA))
        if got:
            rows.append({"month": got[0], "ntd_million": got[1], "filed": filed, "url": url})
        if len(rows) >= limit:
            break
    print(f"tsmc: {len(rows)} months")
    if not rows:
        raise RuntimeError("no TSMC revenue 6-K parsed")
    if not dry_run:
        append_tidy(data_dir / "tidy" / "tsmc_revenue.csv", rows, TSMC_FIELDS, key=("month",))
    return rows


# --- FRED --------------------------------------------------------------------------------

def parse_fred(text, series):
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 2 or not re.match(r"\d{4}-\d{2}-\d{2}$", r[0]) or r[1] in (".", ""):
            continue
        rows.append({"date": r[0], "series": series, "pct": float(r[1])})
    return rows


def collect_fred(data_dir, dry_run=False, series="BAMLH0A0HYM2"):
    start = (dt.date.today() - dt.timedelta(days=730)).isoformat()
    rows = parse_fred(fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"), series)
    print(f"fred: {len(rows)} rows")
    if not rows:
        raise RuntimeError("no FRED rows")
    if not dry_run:
        append_tidy(data_dir / "tidy" / "credit_spread.csv", rows, SPREAD_FIELDS, key=("date", "series"))
    return rows


# --- FINRA -------------------------------------------------------------------------------

def parse_finra(text, symbols):
    rows = []
    for line in text.splitlines():
        p = line.strip().split("|")
        if len(p) < 5 or p[1] not in symbols or not p[0].isdigit():
            continue
        d = f"{p[0][:4]}-{p[0][4:6]}-{p[0][6:8]}"
        rows.append({"date": d, "symbol": p[1], "short_volume": int(float(p[2])), "total_volume": int(float(p[4]))})
    return rows


def collect_finra(data_dir, dry_run=False, days=45):
    path = data_dir / "tidy" / "short_volume.csv"
    have = set()
    if path.exists():
        with path.open(newline="") as f:
            have = {r["date"] for r in csv.DictReader(f)}
    rows, today = [], dt.date.today()
    for i in range(1, days + 1):
        d = today - dt.timedelta(days=i)
        if d.weekday() >= 5 or d.isoformat() in have:
            continue
        try:
            text = fetch(f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):   # holiday or not yet published
                continue
            raise
        rows += parse_finra(text, set(BASKET))
    print(f"finra: {len(rows)} new rows")
    if not dry_run and rows:
        append_tidy(path, rows, SHORT_FIELDS, key=("date", "symbol"))
    return rows


# --- GDELT -------------------------------------------------------------------------------

def parse_gdelt(payload, query):
    rows = []
    for series in payload.get("timeline", []):
        for p in series.get("data", []):
            d = p["date"][:8]
            rows.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "query": query, "volume_pct": round(float(p["value"]), 5)})
    return rows


def collect_gdelt(data_dir, dry_run=False):
    rows = []
    for i, q in enumerate(NEWS_QUERIES):
        if i:
            time.sleep(8)   # GDELT allows about one request every 5 seconds
        params = {"query": q, "mode": "timelinevol", "format": "json", "timespan": "3m", "timelinesmooth": "0"}
        text = fetch("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params))
        if not text.strip():
            print(f"gdelt: empty response for {q}", file=sys.stderr)
            continue
        rows += parse_gdelt(json.loads(text), q)
    print(f"gdelt: {len(rows)} rows")
    if not rows:
        raise RuntimeError("no GDELT rows")
    if not dry_run:
        append_tidy(data_dir / "tidy" / "news_attention.csv", rows, NEWS_FIELDS, key=("date", "query"))
    return rows


# --- Stock prices ------------------------------------------------------------------------

def parse_stooq(text, symbol, since):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        d, c = r.get("Date"), r.get("Close")
        if d and c and d >= since:
            rows.append({"date": d, "symbol": symbol, "close": float(c), "source": "stooq"})
    return rows


def parse_yahoo(payload, symbol, since):
    res = (payload.get("chart", {}).get("result") or [None])[0]
    if not res:
        return []
    closes = res["indicators"]["quote"][0]["close"]
    rows = []
    for t, c in zip(res["timestamp"], closes):
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()
        if c is not None and d >= since:
            rows.append({"date": d, "symbol": symbol, "close": round(float(c), 4), "source": "yahoo"})
    return rows


def collect_prices(data_dir, dry_run=False):
    since = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    rows, missing = [], []
    for s in BASKET:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=1y&interval=1d"
        got = parse_yahoo(json.loads(fetch(url)), s, since)
        (rows.extend(got) if got else missing.append(s))
        time.sleep(1)
    print(f"prices: {len(rows)} rows; missing {missing or 'none'}")
    if missing:
        raise RuntimeError(f"no prices for {missing}")
    if not dry_run:
        append_tidy(data_dir / "tidy" / "stock_prices.csv", rows, PRICE_FIELDS, key=("date", "symbol"))
    return rows


COLLECTORS = {"sec": collect_sec, "tsmc": collect_tsmc, "fred": collect_fred,
              "finra": collect_finra, "gdelt": collect_gdelt, "prices": collect_prices}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", default=",".join(COLLECTORS))
    p.add_argument("--data-dir", default="data")
    p.add_argument("--dry-run", action="store_true", help="fetch and parse, write nothing")
    args = p.parse_args(argv)
    failed, refused = [], []
    for name in args.only.split(","):
        try:
            COLLECTORS[name](Path(args.data_dir), args.dry_run)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                refused.append(f"{name} (HTTP {e.code})")
            else:
                failed.append(name)
                traceback.print_exc()
        except Exception:
            failed.append(name)
            traceback.print_exc()
    if refused:
        # The provider turned the request away (block or rate limit). Earlier data is kept;
        # the dashboard shows the series' last date. Flagged in the log, not a code failure.
        print(f"::warning::refused by provider: {', '.join(refused)}")
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
