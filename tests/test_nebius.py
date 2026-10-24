import csv
import json
import tempfile
import unittest
from pathlib import Path

from collectors import common, nebius

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "nebius.json").read_text())


class NebiusTest(unittest.TestCase):
    def test_snapshot_keeps_gpu_prices_only(self):
        rows, skipped = nebius.snapshot_rows(FIXTURE["current"], "2026-10-24")
        self.assertEqual([r["gpu_model"] for r in rows], ["H200", "H100", "B200"])
        self.assertEqual(rows[1]["usd_per_gpu_hour"], 0.79)
        self.assertEqual(skipped, {"cpu-d3"})

    def test_platform_variants_map_to_one_model(self):
        self.assertEqual(nebius.gpu_model("gpu-b200-sxm-a"), "B200")
        self.assertEqual(nebius.gpu_model("gpu-rtx6000-a"), "RTX PRO 6000")
        self.assertIsNone(nebius.gpu_model("cpu-d3"))

    def test_hourly_rows_and_rerun_dedupe(self):
        hourly = nebius.series_rows(FIXTURE["series"])
        self.assertEqual(len(hourly), 2)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.csv"
            key = ("timestamp", "region", "platform")
            common.append_tidy(path, hourly, fields=nebius.HOURLY_FIELDS, key=key)
            common.append_tidy(path, hourly, fields=nebius.HOURLY_FIELDS, key=key)
            with path.open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 2)


if __name__ == "__main__":
    unittest.main()
