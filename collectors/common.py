"""Helpers shared by every collector."""

import csv

# Columns of data/tidy/cloud_prices.csv, one row per source x region x SKU x tier per day.
TIDY_FIELDS = [
    "date", "source", "region", "sku", "gpu_model", "gpus", "tier",
    "usd_per_vm_hour", "usd_per_gpu_hour",
]


def append_tidy(path, rows, fields=TIDY_FIELDS, key=("date", "source")):
    """Append rows, replacing stored rows that share a key with a new row.

    The default key (date, source) makes a same-day rerun replace that day's snapshot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    new_keys = {tuple(str(r[k]) for k in key) for r in rows}
    kept = []
    if path.exists():
        with path.open(newline="") as f:
            kept = [r for r in csv.DictReader(f) if tuple(r[k] for k in key) not in new_keys]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(kept + rows)
