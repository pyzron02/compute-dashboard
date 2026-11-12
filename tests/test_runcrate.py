import csv
import json
import tempfile
import unittest
from pathlib import Path

from collectors import common, runcrate

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "runcrate.json").read_text())


class RuncrateTest(unittest.TestCase):
    def test_keeps_unambiguous_in_stock_types(self):
        rows, skipped = runcrate.tidy_rows(FIXTURE, "2026-11-08")
        self.assertEqual([r["gpu_model"] for r in rows], ["B300", "B200", "H200", "L40S", "RTX PRO 6000"])
        self.assertEqual({r["tier"] for r in rows}, {"on_demand"})
        self.assertEqual({r["gpus"] for r in rows}, {1})
        by = {r["sku"]: r for r in rows}
        self.assertEqual(by["B200"]["usd_per_gpu_hour"], next(
            g["min_price_hr"] for g in FIXTURE["gpus"] if g["gpu_type"] == "B200"))

    def test_skips_form_ambiguous_and_unmapped_types(self):
        _, skipped = runcrate.tidy_rows(FIXTURE, "2026-11-08")
        # H100 and A100 do not say SXM or PCIe, H200 NVL is not the H200 SXM, RTX 4090 is not tracked
        self.assertTrue({"H100", "A100_80G", "H200_nvl", "RTX4090", "MI350X"} <= skipped)

    def test_skips_out_of_stock_type(self):
        feed = {"gpus": [dict(g, available_options=0) if g["gpu_type"] == "B200" else g
                         for g in FIXTURE["gpus"]]}
        rows, skipped = runcrate.tidy_rows(feed, "2026-11-08")
        self.assertNotIn("B200", [r["sku"] for r in rows])
        self.assertIn("B200", skipped)

    def test_rerun_same_day_replaces_rows(self):
        rows, _ = runcrate.tidy_rows(FIXTURE, "2026-11-08")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cloud_prices.csv"
            common.append_tidy(path, rows)
            common.append_tidy(path, rows)
            with path.open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), len(rows))


if __name__ == "__main__":
    unittest.main()
