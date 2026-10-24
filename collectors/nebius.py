"""Nebius spot GPU prices from its public billing API (no credentials).

Docs: https://docs.nebius.com/signup-billing/spot-prices
Nebius reprices spot capacity as often as every 15 minutes and keeps 30 days of history,
so each run stores the current snapshot and refreshes the hourly series for the last 30 days.

Writes:
  data/raw/nebius/<date>.json.gz       current prices and history, untouched
  data/tidy/cloud_prices.csv           today's spot price per region x GPU (source=nebius)
  data/tidy/nebius_spot_hourly.csv     hourly average spot price per region x GPU

Usage: python -m collectors.nebius [--date YYYY-MM-DD] [--days 30] [--data-dir data]
"""

import argparse
import datetime as dt
import gzip
import json
import sys
import urllib.parse

from pathlib import Path

from collectors.common import append_tidy, open_url

API = "https://api.nebius.cloud/billing/v1alpha1/spot-price"
HOURLY_FIELDS = ["timestamp", "source", "region", "platform", "gpu_model", "usd_per_gpu_hour"]

# Nebius platform id prefix -> GPU model, matched in order.
PLATFORMS = [
    ("gpu-gb300", "GB300"),
    ("gpu-gb200", "GB200"),
    ("gpu-b300", "B300"),
    ("gpu-b200", "B200"),
    ("gpu-h200", "H200"),
    ("gpu-h100", "H100"),
    ("gpu-l40s", "L40S"),
    ("gpu-rtx6000", "RTX PRO 6000"),
]


def get(url, params):
    query = urllib.parse.urlencode(params, doseq=True)
    with open_url(f"{url}?{query}") as resp:
        return json.load(resp)


def paged(url, params):
    """Yield items from every page of a list endpoint."""
    params = dict(params)
    while True:
        page = get(url, params)
        yield from page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            return
        params["pageToken"] = token


def gpu_model(platform):
    for prefix, model in PLATFORMS:
        if platform.startswith(prefix):
            return model
    return None


def is_usd_per_gpu_hour(currency, unit):
    return (currency or "").lower() == "usd" and (unit or "").lower() == "gpu hour"


def snapshot_rows(items, date):
    rows, skipped = [], set()
    for item in items:
        platform = item.get("computeInstance", {}).get("platform", "")
        price = item.get("price", {})
        model = gpu_model(platform)
        if model is None or not is_usd_per_gpu_hour(price.get("currency"), price.get("unitTitle")):
            skipped.add(platform or item.get("productTitle", "?"))
            continue
        value = float(price["value"])
        rows.append({
            "date": date,
            "source": "nebius",
            "region": item.get("region", ""),
            "sku": platform,
            "gpu_model": model,
            "gpus": 1,
            "tier": "spot",
            "usd_per_vm_hour": value,
            "usd_per_gpu_hour": value,
        })
    return rows, skipped


def hourly_rows(series):
    rows = []
    for s in series:
        platform = s.get("computeInstance", {}).get("platform", "")
        model = gpu_model(platform)
        if model is None or not is_usd_per_gpu_hour(s.get("currency"), s.get("unitTitle")):
            continue
        for point in s.get("points", []):
            rows.append({
                "timestamp": point["timestamp"],
                "source": "nebius",
                "region": s.get("region", ""),
                "platform": platform,
                "gpu_model": model,
                "usd_per_gpu_hour": float(point["value"]),
            })
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--days", type=int, default=30, help="history window, at most 30")
    p.add_argument("--data-dir", default="data")
    args = p.parse_args(argv)
    data = Path(args.data_dir)

    current = list(paged(API, {"pageSize": 100}))
    # The API rejects a start time older than 30 days, so stay a few minutes inside it.
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=min(args.days, 30)) + dt.timedelta(minutes=5)
    series = list(paged(API + "/list-series", {
        "filters.startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregation.granularity": "GRANULARITY_HOUR_1",
        "aggregation.method": "METHOD_AVG_PRICE",
        "pageSize": 100,
    }))

    raw_path = data / "raw" / "nebius" / f"{args.date}.json.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(raw_path, "wt") as f:
        json.dump({"current": current, "series": series}, f)

    rows, skipped = snapshot_rows(current, args.date)
    if not rows:
        sys.exit("No Nebius spot prices parsed; refusing to write an empty snapshot")
    append_tidy(data / "tidy" / "cloud_prices.csv", rows)

    hourly = hourly_rows(series)
    append_tidy(data / "tidy" / "nebius_spot_hourly.csv", hourly, fields=HOURLY_FIELDS,
                key=("timestamp", "region", "platform"))

    if skipped:
        print("Skipped non-GPU or non-USD items: " + ", ".join(sorted(skipped)), file=sys.stderr)
    print(f"Wrote {len(rows)} snapshot rows and {len(hourly)} hourly points", file=sys.stderr)


if __name__ == "__main__":
    main()
