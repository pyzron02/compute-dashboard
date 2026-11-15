import unittest

from analysis import interpret as it


def ratios(gpu, values, start=1):
    return [{"provider": "Nebius", "gpu": gpu, "date": f"2026-11-{start + i:02d}", "ratio": v}
            for i, v in enumerate(values)]


EMPTY = {"generated": "2026-11-20T06:00:00Z", "markets": {"facts": {}, "speculation": {}, "perception": {}}}


class InterpretTest(unittest.TestCase):
    def test_every_chart_reads_an_empty_site_without_error(self):
        out = it.readings(EMPTY)
        self.assertEqual(set(out), set(it.READERS))
        for key, r in out.items():
            self.assertTrue(r["how"], key)
            self.assertEqual(r["tone"], "none", key)

    def test_week_below_half_is_against_and_says_trigger_fired(self):
        site = dict(EMPTY, scarcity=ratios("B300", [0.4] * 8 + [0.9]))   # last row is today, partial
        site["generated"] = "2026-11-09T06:00:00Z"
        r = it.scarcity_reading(site)
        self.assertEqual(r["tone"], "against")
        self.assertIn("trigger has fired", r["means"])

    def test_tight_spot_supports(self):
        site = dict(EMPTY, scarcity=ratios("B300", [0.8] * 8))
        self.assertEqual(it.scarcity_reading(site)["tone"], "supports")

    def test_capex_falling_quarter_on_quarter_is_against(self):
        site = {"markets": {"facts": {"capex": [
            {"quarter": "2026 Q2", "by_company": {"MSFT": 40}, "total": 40, "complete": True, "yoy": 0.5},
            {"quarter": "2026 Q3", "by_company": {"MSFT": 30}, "total": 30, "complete": True, "yoy": 0.1}]}}}
        r = it.capex_reading(site)
        self.assertEqual(r["tone"], "against")
        self.assertIn("-25% on the quarter", r["now"])

    def test_funding_flags_interest_above_operating_income(self):
        site = {"markets": {"facts": {"funding": [
            {"ticker": "CRWV", "quarter": "2026 Q3", "period_end": "2026-09-30", "debt": 40.0, "cash": 4.0,
             "deferred_revenue": 5.0, "interest_expense": 0.8, "operating_income": 0.2}]}}}
        r = it.funding_reading(site)
        self.assertEqual(r["tone"], "against")
        self.assertIn("CRWV does not cover interest", r["means"])
        self.assertIn("$800M", r["now"])

    def test_money_formats(self):
        self.assertEqual(it.money(0.039), "$39M")
        self.assertEqual(it.money(-0.186), "-$186M")
        self.assertEqual(it.money(230.42), "$230B")


if __name__ == "__main__":
    unittest.main()
