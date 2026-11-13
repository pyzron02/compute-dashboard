import unittest

from analysis import thesis


def day(date, ratio):
    return {"provider": "Nebius", "gpu": "B300", "date": date, "ratio": ratio}


class ThesisTest(unittest.TestCase):
    def test_fires_after_seven_days_below_half(self):
        s = [day(f"2026-11-{d:02d}", 0.4) for d in range(1, 8)]
        self.assertEqual(thesis.b300_trigger(s)["status"], "fired")

    def test_six_days_below_is_watch(self):
        s = [day("2026-11-01", 0.8)] + [day(f"2026-11-{d:02d}", 0.4) for d in range(2, 8)]
        self.assertEqual(thesis.b300_trigger(s)["status"], "watch")

    def test_recent_dip_then_recovery_is_watch_then_ok(self):
        s = [day(f"2026-11-{d:02d}", r) for d, r in enumerate([0.9, 0.9, 0.9, 0.9, 0.45, 0.47, 0.8], 1)]
        self.assertEqual(thesis.b300_trigger(s)["status"], "ok")
        s[3]["ratio"] = 0.4
        self.assertEqual(thesis.b300_trigger(s)["status"], "watch")

    def test_no_data_is_pending_and_fired_sorts_first(self):
        self.assertEqual(thesis.b300_trigger([])["status"], "pending")
        manual = [{"id": "x", "trigger": "t", "breaks_if": "b", "status": "fired", "last_checked": "",
                   "next_check": "", "evidence": "e", "source_url": "u"}]
        rows = thesis.thesis_watch([day("2026-11-01", 0.9)], manual)
        self.assertEqual([r["status"] for r in rows], ["fired", "ok"])


if __name__ == "__main__":
    unittest.main()
