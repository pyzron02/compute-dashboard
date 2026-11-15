import unittest

from analysis import markets
from collectors import markets as col


def fact(start, end, val, form="10-Q", filed="2026-01-01"):
    e = {"end": end, "val": val, "form": form, "filed": filed}
    if start:
        e["start"] = start
    return e


class CollectorParsers(unittest.TestCase):
    def test_ytd_cash_flow_becomes_quarters(self):
        # Fiscal year from Jul 1: Q1 3-month, then 6- and 9-month YTD, then the 10-K year.
        entries = [fact("2025-07-01", "2025-09-30", 10), fact("2025-07-01", "2025-12-31", 25),
                   fact("2025-07-01", "2026-03-31", 45), fact("2025-07-01", "2026-06-30", 70, "10-K")]
        q = {k: v[0] for k, v in col.quarterly_flows(entries).items()}
        self.assertEqual(q, {"2025-09-30": 10, "2025-12-31": 15, "2026-03-31": 20, "2026-06-30": 25})

    def test_latest_filing_wins_and_balances_skip_durations(self):
        entries = [fact(None, "2026-06-30", 5, filed="2026-08-01"), fact(None, "2026-06-30", 6, filed="2026-11-01"),
                   fact("2026-04-01", "2026-06-30", 99)]
        self.assertEqual(col.balances(entries)["2026-06-30"][0], 6)

    def test_companyfacts_falls_back_to_second_concept(self):
        facts = {"facts": {"us-gaap": {"PaymentsToAcquireProductiveAssets": {"units": {"USD": [
            fact("2026-01-01", "2026-03-31", 2e10)]}}}}}
        rows = col.parse_companyfacts("AMZN", facts, ["capex"])
        self.assertEqual(rows[0]["concept"], "PaymentsToAcquireProductiveAssets")
        self.assertEqual(rows[0]["usd"], 20000000000)

    def test_tsmc_text(self):
        html = "<p>HSINCHU, Taiwan, R.O.C., Nov. 10, 2026 - TSMC today announced net revenue for October 2026: " \
               "On a consolidated basis, revenue for October 2026 was approximately NT$586.89 billion, an increase of 14.7 percent</p>"
        self.assertEqual(col.parse_tsmc(html), ("2026-10", 586890))
        self.assertEqual(col.parse_tsmc("October 2026 revenue was approximately NT$&nbsp;586.89 billion"), ("2026-10", 586890))
        self.assertIsNone(col.parse_tsmc("no figures here"))

    def test_fred_both_header_styles_and_missing(self):
        for head in ("observation_date", "DATE"):
            rows = col.parse_fred(f"{head},BAMLH0A0HYM2\n2026-11-10,3.05\n2026-11-11,.\n", "BAMLH0A0HYM2")
            self.assertEqual(rows, [{"date": "2026-11-10", "series": "BAMLH0A0HYM2", "pct": 3.05}])

    def test_finra(self):
        text = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n" \
               "20261113|NBIS|4000000|1000|9000000|B,Q,N\n20261113|AAPL|1|0|2|Q\n9999"
        self.assertEqual(col.parse_finra(text, {"NBIS"}),
                         [{"date": "2026-11-13", "symbol": "NBIS", "short_volume": 4000000, "total_volume": 9000000}])

    def test_gdelt(self):
        payload = {"timeline": [{"series": "Volume Intensity", "data": [{"date": "20261112T000000Z", "value": 0.12}]}]}
        self.assertEqual(col.parse_gdelt(payload, "q"), [{"date": "2026-11-12", "query": "q", "volume_pct": 0.12}])

    def test_stooq(self):
        text = "Date,Open,High,Low,Close,Volume\n2026-11-11,150,160,149,154.69,1\n2026-11-12,140,141,120,131.67,1\n"
        rows = col.parse_stooq(text, "NBIS", "2026-11-12")
        self.assertEqual(rows, [{"date": "2026-11-12", "symbol": "NBIS", "close": 131.67, "source": "stooq"}])

    def test_yahoo(self):
        payload = {"chart": {"result": [{"timestamp": [1794873600, 1794960000],
                                         "indicators": {"quote": [{"close": [154.69, None]}]}}]}}
        rows = col.parse_yahoo(payload, "NBIS", "2026-01-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 154.69)


class Views(unittest.TestCase):
    def test_capex_totals_and_yoy_only_when_complete(self):
        sec = [{"ticker": t, "metric": "capex", "period_end": f"{y}-09-30", "usd": str(v * 1e9)}
               for y, v in ((2025, 10), (2026, 15)) for t in ("MSFT", "GOOGL", "AMZN", "META", "ORCL")]
        rows = markets.capex(sec)
        self.assertEqual([r["total"] for r in rows], [50, 75])
        self.assertAlmostEqual(rows[1]["yoy"], 0.5)
        self.assertEqual(markets.capex(sec[:4])[0]["complete"], False)

    def test_funding_adds_current_debt_and_manual_rows(self):
        sec = [{"ticker": "CRWV", "metric": "debt", "period_end": "2026-09-30", "usd": "40e9"},
               {"ticker": "CRWV", "metric": "debt_current", "period_end": "2026-09-30", "usd": "6.9e9"}]
        manual = [{"ticker": "NBIS", "metric": "cash", "period_end": "2026-09-30", "usd": "7.4e9"}]
        rows = {r["ticker"]: r for r in markets.funding(sec, manual)}
        self.assertAlmostEqual(rows["CRWV"]["debt"], 46.9)
        self.assertAlmostEqual(rows["NBIS"]["cash"], 7.4)

    def test_basket_indexes_from_first_common_date(self):
        prices = [{"date": d, "symbol": s, "close": str(c)} for d, s, c in
                  [("2026-11-10", "NBIS", 100), ("2026-11-11", "NBIS", 150), ("2026-11-11", "CRWV", 50),
                   ("2026-11-12", "NBIS", 120), ("2026-11-12", "CRWV", 60)]]
        b = markets.basket(prices)
        self.assertEqual(b["start"], "2026-11-11")
        self.assertEqual(b["series"][0]["points"][-1], ["2026-11-12", 100.0])  # (80 + 120) / 2

    def test_guidance_revisions_need_two_points(self):
        rows = [{"company": "N", "item": "rev", "unit": "$B", "period": "2026", "guided_on": d, "low": "3", "high": h,
                 "actual": "", "outcome": o, "note": "", "url": "u"} for d, h, o in (("2026-08-12", "3.4", ""), ("2026-11-12", "3.2", "cut"))]
        score, revs = markets.guidance(rows)
        self.assertEqual(len(score), 1)
        self.assertEqual([p["high"] for p in revs[0]["points"]], [3.4, 3.2])

    def test_tsmc_collected_overrides_seed(self):
        seed = [{"month": f"2026-0{i}", "ntd_million": "300000", "url": "s"} for i in (1, 2, 3)]
        got = markets.tsmc([{"month": "2026-03", "ntd_million": "330000", "url": "c"}], seed)
        self.assertEqual(got[-1]["ntd_billion"], 330.0)
        self.assertEqual(got[-1]["avg3"], 310.0)


if __name__ == "__main__":
    unittest.main()
