import datetime as dt
import unittest

from analysis import build_site, digest


def point(ts, gpu, usd, region="r1"):
    return {"timestamp": ts, "source": "nebius", "region": region, "platform": f"gpu-{gpu.lower()}",
            "gpu_model": gpu, "usd_per_gpu_hour": str(usd)}


def hours(day, gpu, price_at):
    """One point per hour of a UTC day, priced by price_at(hour)."""
    return [point(f"{day}T{h:02d}:00:00Z", gpu, price_at(h)) for h in range(24)]


class PatternsTest(unittest.TestCase):
    def test_intraday_removes_daily_level(self):
        # Day 2 is twice as dear as day 1, but both peak at 18:00 by the same 20%.
        rows = (hours("2026-10-20", "B200", lambda h: 2.4 if h == 18 else 2.0)
                + hours("2026-10-21", "B200", lambda h: 4.8 if h == 18 else 4.0))
        out = build_site.intraday([], rows, None)
        g = out["gpus"][0]
        self.assertEqual(out["hour_granularity"], "1 hour")
        self.assertEqual(g["hour_days"], 2)
        self.assertEqual(max(range(24), key=lambda h: g["by_hour"][h]), 18)
        self.assertAlmostEqual(g["by_hour"][18], 2.4 / (2.0 + 0.4 / 24) - 1, places=3)

    def test_intraday_skips_partial_days_and_needs_a_week_for_weekdays(self):
        rows = hours("2026-10-20", "B200", lambda h: 2.0)[:12]
        g = build_site.intraday([], rows, None)["gpus"][0]
        self.assertEqual(g["hour_days"], 0)
        self.assertEqual(g["by_weekday"], [None] * 7)

    def test_weekday_dip(self):
        # Fourteen days, Saturdays (Oct 17 and 24) 20% cheaper; weekdays priced 5.
        start = dt.date(2026, 10, 15)
        rows = []
        for i in range(14):
            d = start + dt.timedelta(days=i)
            price = 4.0 if d.weekday() == 5 else 5.0
            rows += hours(d.isoformat(), "B300", lambda h, p=price: p)
        g = build_site.intraday([], rows, None)["gpus"][0]
        sat = g["by_weekday"][5]
        self.assertLess(sat, -0.15)
        self.assertEqual(min(v for v in g["by_weekday"] if v is not None), sat)

    def test_at_cap_counts_intervals_within_three_percent(self):
        manual = [{"date": "2026-10-24", "source": "nebius", "gpu_model": "B300", "tier": "on_demand",
                   "usd_per_gpu_hour": "9.50", "note": "", "url": ""}]
        rows = [point("2026-10-20T00:00:00Z", "B300", 9.50), point("2026-10-20T00:15:00Z", "B300", 9.30),
                point("2026-10-20T00:30:00Z", "B300", 9.00), point("2026-10-20T00:45:00Z", "B300", 5.00),
                point("2026-10-20T00:00:00Z", "A100", 1.00)]
        out = build_site.at_cap(rows, [], manual, None)
        self.assertEqual(out, [{"gpu": "B300", "date": "2026-10-20", "share": 0.5, "intervals": 4}])


class DigestTest(unittest.TestCase):
    def data(self):
        return {
            "tiles": [{"gpu": "B200", "spot": 6.0, "change_7d": 1.5, "status": "tight",
                       "nebius_ratio": 0.7, "regions": 2}],
            "scarcity": [{"provider": "Nebius", "gpu": "B200", "date": "2026-10-16", "ratio": 0.2}],
            "at_cap": [{"gpu": "B200", "date": "2026-10-22", "share": 0.25, "intervals": 96}],
            "intraday": {"gpus": []},
            "health": [{"source": "Azure", "status": "ok", "last_snapshot": "2026-10-24"}],
            "sources": [{"name": "Nebius spot", "origin": "Nebius billing API", "url": "https://docs.nebius.com"}],
        }

    def test_render_reports_move_flip_and_sources(self):
        hourly = [point("2026-10-16T00:00:00Z", "B200", 2.4, "eu"), point("2026-10-24T00:00:00Z", "B200", 6.0, "eu")]
        events = [{"date": "2026-10-20", "label": "Something happened", "url": "https://example.com"}]
        md = digest.render(self.data(), [], hourly, events, dt.date(2026, 10, 24))
        self.assertIn("**B200** Nebius spot $6.00/GPU-hr, +150% on the week, loose → tight", md)
        self.assertIn("at the on-demand cap 25% of the time", md)
        self.assertIn("B200 in eu: $2.40 → $6.00 (+150%)", md)
        self.assertIn("[Something happened](https://example.com)", md)
        self.assertIn("No consistent time-of-day or weekday pattern yet.", md)
        self.assertIn("All feeds updated on schedule.", md)
        self.assertIn("[Nebius billing API](https://docs.nebius.com)", md)


if __name__ == "__main__":
    unittest.main()
