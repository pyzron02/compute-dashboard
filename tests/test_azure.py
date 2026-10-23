import csv
import json
import tempfile
import unittest
from pathlib import Path

from collectors import azure

FIXTURE = Path(__file__).parent / "fixtures" / "azure_items.json"


class TidyRowsTest(unittest.TestCase):
    def setUp(self):
        items = json.loads(FIXTURE.read_text())
        self.rows, self.unknown = azure.tidy_rows(items, "2026-10-23")
        self.by = {(r["sku"], r["tier"]): r for r in self.rows}

    def test_skips_windows_and_devtest(self):
        self.assertEqual(len(self.rows), 8)

    def test_on_demand_per_gpu(self):
        r = self.by[("Standard_ND96isr_H100_v5", "on_demand")]
        self.assertEqual(r["gpus"], 8)
        self.assertAlmostEqual(r["usd_per_gpu_hour"], 12.29)

    def test_reservations_are_converted_to_hourly(self):
        one = self.by[("Standard_ND96isr_H100_v5", "reserved_1y")]
        three = self.by[("Standard_ND96isr_H100_v5", "reserved_3y")]
        self.assertAlmostEqual(one["usd_per_vm_hour"], 551221 / 8760, places=4)
        self.assertAlmostEqual(three["usd_per_vm_hour"], 1134310 / (3 * 8760), places=4)
        self.assertLess(three["usd_per_gpu_hour"], one["usd_per_gpu_hour"])

    def test_spot_and_low_priority(self):
        self.assertAlmostEqual(self.by[("Standard_ND96isr_H100_v5", "spot")]["usd_per_gpu_hour"], 2.271192)
        self.assertIn(("Standard_ND96isr_H100_v5", "low_priority"), self.by)

    def test_small_vms_and_gb200(self):
        self.assertEqual(self.by[("Standard_NC40ads_H100_v5", "on_demand")]["gpus"], 1)
        self.assertEqual(self.by[("Standard_NC80adis_H100_v5", "on_demand")]["usd_per_gpu_hour"], 6.98)
        gb = self.by[("Standard_ND128isr_GB200_v6", "on_demand")]
        self.assertEqual((gb["gpu_model"], gb["gpus"]), ("GB200", 4))

    def test_unknown_sku_reported_not_guessed(self):
        self.assertEqual(self.unknown, {"Standard_NV_Mystery_H100"})


class AppendTidyTest(unittest.TestCase):
    def test_rerun_same_day_replaces_rows(self):
        items = json.loads(FIXTURE.read_text())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cloud_prices.csv"
            day1, _ = azure.tidy_rows(items, "2026-10-22")
            day2, _ = azure.tidy_rows(items, "2026-10-23")
            azure.append_tidy(path, day1)
            azure.append_tidy(path, day2)
            azure.append_tidy(path, day2)
            with path.open() as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2 * len(day1))


if __name__ == "__main__":
    unittest.main()
