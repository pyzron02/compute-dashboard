"""Runcrate on-demand GPU prices from its public pricing feed (no credentials).

Feed: https://www.runcrate.ai/api/gpu-pricing
Each GPU type has min_price_hr, the live on-demand price for one GPU for one hour, and
available_options, the number of live offers. The feed can keep a stale price for an
out-of-stock type, so types with no live offer are skipped. Only types whose model is
unambiguous are kept: the feed does not say SXM or PCIe, so H100 and A100 are left out,
and H200 NVL is a separate feed type that is not the H200 SXM this repo tracks.

Writes:
  data/raw/runcrate/<date>.json.gz   the feed response, untouched
  data/tidy/cloud_prices.csv         today's on-demand price per GPU type (source=runcrate)

Usage: python -m collectors.runcrate [--date YYYY-MM-DD] [--data-dir data]
"""

import argparse
import datetime as dt
import gzip
import json
import sys
from pathlib import Path

from collectors.common import append_tidy, open_url

API = "https://www.runcrate.ai/api/gpu-pricing"

# Feed gpu_type -> GPU model, using the same model names as the other collectors.
GPU_TYPES = {
    "B300": "B300",
    "B200": "B200",
    "H200": "H200",
    "L40S": "L40S",
    "RTXPro6000": "RTX PRO 6000",
}


def tidy_rows(feed, date):
    rows, skipped = [], set()
    for g in feed.get("gpus", []):
        model = GPU_TYPES.get(g.get("gpu_type"))
        price = g.get("min_price_hr")
        if model is None or (g.get("available_options") or 0) < 1 or not isinstance(price, (int, float)) or price <= 0:
            skipped.add(g.get("gpu_type", "?"))
            continue
        rows.append({
            "date": date,
            "source": "runcrate",
            "region": "global",
            "sku": g["gpu_type"],
            "gpu_model": model,
            "gpus": 1,
            "tier": "on_demand",
            "usd_per_vm_hour": price,
            "usd_per_gpu_hour": price,
        })
    return rows, skipped


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--data-dir", default="data")
    args = p.parse_args(argv)
    data = Path(args.data_dir)

    with open_url(API) as resp:
        feed = json.load(resp)

    raw_path = data / "raw" / "runcrate" / f"{args.date}.json.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(raw_path, "wt") as f:
        json.dump(feed, f)

    rows, skipped = tidy_rows(feed, args.date)
    if not rows:
        sys.exit("No Runcrate prices parsed; refusing to write an empty snapshot")
    append_tidy(data / "tidy" / "cloud_prices.csv", rows)
    if skipped:
        print("Skipped GPU types: " + ", ".join(sorted(skipped)), file=sys.stderr)
    print(f"Wrote {len(rows)} rows for {args.date}", file=sys.stderr)


if __name__ == "__main__":
    main()
