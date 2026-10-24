import unittest

from analysis import build_site


def hourly(ts, region, platform, gpu, usd):
    return {"timestamp": ts, "source": "nebius", "region": region, "platform": platform,
            "gpu_model": gpu, "usd_per_gpu_hour": str(usd)}


class BuildSiteTest(unittest.TestCase):
    def setUp(self):
        self.hourly = [
            hourly("2026-10-06T00:00:00Z", "r1", "gpu-b200-sxm", "B200", 3.95),
            hourly("2026-10-07T00:00:00Z", "r1", "gpu-b200-sxm", "B200", 3.95),
            hourly("2026-10-08T05:00:00Z", "r1", "gpu-b200-sxm", "B200", 1.50),
            hourly("2026-10-09T00:00:00Z", "r1", "gpu-b200-sxm", "B200", 4.25),
        ]
        self.manual = [{"date": "2026-10-24", "source": "nebius", "gpu_model": "B200", "tier": "on_demand",
                        "usd_per_gpu_hour": "8.50", "note": "", "url": ""}]
        self.cloud = [
            {"date": "2026-10-24", "source": "azure", "region": "eastus", "sku": "x", "gpu_model": "H100", "gpus": "8",
             "tier": "on_demand", "usd_per_vm_hour": "80", "usd_per_gpu_hour": "10"},
            {"date": "2026-10-24", "source": "azure", "region": "eastus", "sku": "x", "gpu_model": "H100", "gpus": "8",
             "tier": "spot", "usd_per_vm_hour": "20", "usd_per_gpu_hour": "2.5"},
        ]

    def test_market_start_is_first_price_move(self):
        self.assertEqual(build_site.market_start(self.hourly), "2026-10-08")

    def test_scarcity_skips_fixed_rate_days_and_divides_by_list(self):
        s = build_site.scarcity_series(self.cloud, self.hourly, self.manual, "2026-10-08")
        nebius = [r for r in s if r["provider"] == "Nebius"]
        self.assertEqual([r["date"] for r in nebius], ["2026-10-08", "2026-10-09"])
        self.assertAlmostEqual(nebius[-1]["ratio"], 0.5)
        azure = [r for r in s if r["provider"] == "Azure"]
        self.assertAlmostEqual(azure[0]["ratio"], 0.25)

    def test_price_per_pflop(self):
        m = build_site.price_matrix(self.cloud, self.manual, {"H100": 0.9895, "B200": 2.25})
        b200 = next(r for r in m["rows"] if r["gpu"] == "B200")
        self.assertAlmostEqual(b200["usd_per_pflop"]["nebius_on_demand"], 8.5 / 2.25, places=3)


if __name__ == "__main__":
    unittest.main()
