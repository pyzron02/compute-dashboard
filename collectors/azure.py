"""Daily snapshot of Azure GPU VM prices from the public Retail Prices API.

No credentials needed. Writes:
  data/raw/azure/<date>.json.gz   every API item, untouched (lets us re-parse later)
  data/tidy/cloud_prices.csv      one row per region x SKU x tier, normalised to $/GPU-hour

Usage: python -m collectors.azure [--date YYYY-MM-DD] [--data-dir data]
"""

import argparse
import csv
import datetime as dt
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://prices.azure.com/api/retail/prices"

# Substrings of armSkuName we query for. Checked in this order when labelling a SKU,
# so "GB200" wins over "B200".
GPU_MODELS = ["GB300", "GB200", "B200", "H200", "H100", "MI300X", "A100"]

# GPUs per VM, matched against armSkuName. First match wins, so specific patterns go first.
GPUS_PER_VM = [
    (r"^Standard_ND\d+.*_(H100|H200|MI300X)_v\d", 8),
    (r"^Standard_ND96am?sr?_A100_v4$", 8),
    (r"^Standard_ND\d+isrf?_(NDR_)?G?B\d00_v6$", 4),
    (r"^Standard_NCC?40ads_H100_v5$", 1),
    (r"^Standard_NC80adis_H100_v5$", 2),
    (r"^Standard_NC24ads_A100_v4$", 1),
    (r"^Standard_NC48ads_A100_v4$", 2),
    (r"^Standard_NC96ads_A100_v4$", 4),
]

HOURS_PER_YEAR = 8760
TIDY_FIELDS = [
    "date", "source", "region", "sku", "gpu_model", "gpus", "tier",
    "usd_per_vm_hour", "usd_per_gpu_hour",
]


def fetch_items(gpu_substring, sleep=0.2):
    """All Linux VM price items whose SKU name contains gpu_substring, across every region."""
    flt = (
        "serviceName eq 'Virtual Machines' "
        f"and contains(armSkuName, '{gpu_substring}')"
    )
    url = API + "?" + urllib.parse.urlencode({"$filter": flt})
    items = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as resp:
            page = json.load(resp)
        items.extend(page.get("Items", []))
        url = page.get("NextPageLink")
        time.sleep(sleep)
    return items


def gpus_per_vm(sku):
    for pattern, n in GPUS_PER_VM:
        if re.search(pattern, sku):
            return n
    return None


def model_of(sku):
    for model in GPU_MODELS:
        if model in sku:
            return model
    return None


def item_key(item):
    return (item.get("meterId"), item.get("armRegionName"), item.get("type"),
            item.get("reservationTerm"), item.get("productName"))


def tier_of(item):
    """Map an API item to a pricing tier, or None for rows we skip."""
    if "Windows" in item.get("productName", ""):
        return None
    if item.get("type") == "DevTestConsumption":
        return None
    meter = item.get("meterName", "")
    if item.get("type") == "Reservation":
        years = (item.get("reservationTerm") or "").split()[0]
        return f"reserved_{years}y" if years.isdigit() else None
    if item.get("type") != "Consumption":
        return None
    if meter.endswith("Spot"):
        return "spot"
    if meter.endswith("Low Priority"):
        return "low_priority"
    return "on_demand"


def hourly_price(item, tier):
    """Reservation prices are quoted for the whole term; everything else is per hour."""
    price = float(item["retailPrice"])
    if tier.startswith("reserved_"):
        years = int(tier[len("reserved_"):-1])
        return price / (years * HOURS_PER_YEAR)
    return price


def tidy_rows(items, date):
    rows, unknown = [], set()
    for item in items:
        if item.get("unitOfMeasure", "1 Hour") != "1 Hour" and item.get("type") != "Reservation":
            continue
        tier = tier_of(item)
        if tier is None:
            continue
        sku = item["armSkuName"]
        if not sku.startswith("Standard_"):
            continue  # dedicated hosts, not VMs
        gpus = gpus_per_vm(sku)
        if gpus is None:
            unknown.add(sku)
            continue
        gpu_model = model_of(sku)
        vm_hour = hourly_price(item, tier)
        rows.append({
            "date": date,
            "source": "azure",
            "region": item.get("armRegionName", ""),
            "sku": sku,
            "gpu_model": gpu_model,
            "gpus": gpus,
            "tier": tier,
            "usd_per_vm_hour": round(vm_hour, 6),
            "usd_per_gpu_hour": round(vm_hour / gpus, 6),
        })
    return rows, unknown


def append_tidy(path, rows):
    """Append rows, replacing any rows already stored for the same date and source."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = {(r["date"], r["source"]) for r in rows}
    kept = []
    if path.exists():
        with path.open(newline="") as f:
            kept = [r for r in csv.DictReader(f) if (r["date"], r["source"]) not in dates]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TIDY_FIELDS)
        w.writeheader()
        w.writerows(kept + rows)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--data-dir", default="data")
    args = p.parse_args(argv)
    data = Path(args.data_dir)

    # Queries overlap ("B200" also matches GB200 SKUs), so dedupe before parsing.
    raw = {}
    for model in GPU_MODELS:
        items = fetch_items(model)
        print(f"{model}: {len(items)} items", file=sys.stderr)
        for item in items:
            raw[item_key(item)] = item
    items = list(raw.values())
    rows, unknown = tidy_rows(items, args.date)

    raw_path = data / "raw" / "azure" / f"{args.date}.json.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(raw_path, "wt") as f:
        json.dump(items, f)

    if not rows:
        sys.exit("No rows parsed; refusing to write an empty snapshot")
    append_tidy(data / "tidy" / "cloud_prices.csv", rows)
    if unknown:
        print("Skipped SKUs with unknown GPU count: " + ", ".join(sorted(unknown)), file=sys.stderr)
    print(f"Wrote {len(rows)} rows for {args.date}", file=sys.stderr)


if __name__ == "__main__":
    main()
