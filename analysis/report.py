"""Build reports/latest.md: what the collected price series show, with the source of each.

Reads only data/tidy/*.csv and data/manual/*.csv, so it can be rerun at any time.
Usage: python -m analysis.report [--data-dir data] [--out reports/latest.md]
"""

import argparse
import csv
import datetime as dt
import statistics as st
from collections import defaultdict
from pathlib import Path

# Every series in the report, with where it comes from. Keyed by (source, kind).
SOURCES = {
    ("azure", "list"): {
        "name": "Azure GPU VM list prices (on-demand, spot, low priority, 1/3/5-year reserved)",
        "origin": "Azure Retail Prices API, prices.azure.com/api/retail/prices (public, no key)",
        "url": "https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices",
        "collector": "collectors/azure.py",
        "cadence": "Daily snapshot at 06:15 UTC",
        "file": "data/tidy/cloud_prices.csv (source=azure)",
    },
    ("nebius", "spot"): {
        "name": "Nebius spot GPU prices, current and hourly history",
        "origin": "Nebius billing API, api.nebius.cloud/billing/v1alpha1/spot-price (public, no key)",
        "url": "https://docs.nebius.com/signup-billing/spot-prices",
        "collector": "collectors/nebius.py",
        "cadence": "Daily snapshot plus hourly averages backfilled 30 days",
        "file": "data/tidy/cloud_prices.csv (source=nebius), data/tidy/nebius_spot_hourly.csv",
    },
    ("nebius", "list"): {
        "name": "Nebius on-demand list prices",
        "origin": "Nebius pricing page, entered by hand",
        "url": "https://nebius.com/prices",
        "collector": "data/manual/list_prices.csv",
        "cadence": "Manual, when the page changes",
        "file": "data/manual/list_prices.csv",
    },
}

GPU_ORDER = ["GB300", "GB200", "B300", "B200", "H200", "H100", "MI300X", "A100", "L40S", "RTX PRO 6000"]


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def gpu_key(model):
    return GPU_ORDER.index(model) if model in GPU_ORDER else len(GPU_ORDER)


def money(x):
    return "" if x is None else f"${x:,.2f}"


def pct(x):
    return "" if x is None else f"{x:+.0%}"


def median_or_none(values):
    return st.median(values) if values else None


def latest_snapshot(cloud_rows, source):
    dates = sorted({r["date"] for r in cloud_rows if r["source"] == source})
    if not dates:
        return None, []
    return dates[-1], [r for r in cloud_rows if r["source"] == source and r["date"] == dates[-1]]


def medians_by(rows, *keys):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(float(r["usd_per_gpu_hour"]))
    return {k: (st.median(v), min(v), max(v), len(v)) for k, v in groups.items()}


def price_table(azure_rows, nebius_rows, manual_rows):
    """Median $/GPU-hour per GPU across both providers and the main tiers."""
    az = medians_by(azure_rows, "gpu_model", "tier")
    nb = medians_by(nebius_rows, "gpu_model", "tier")
    nb_list = {(r["gpu_model"]): float(r["usd_per_gpu_hour"]) for r in manual_rows
               if r["source"] == "nebius" and r["tier"] == "on_demand"}
    models = sorted({k[0] for k in az} | {k[0] for k in nb} | set(nb_list), key=gpu_key)
    lines = [
        "| GPU | Azure on-demand | Azure 3-yr reserved | Azure spot | Nebius on-demand | Nebius spot | Azure ÷ Nebius on-demand |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in models:
        a_od = az.get((m, "on_demand"), (None,))[0]
        a_3y = az.get((m, "reserved_3y"), (None,))[0]
        a_sp = az.get((m, "spot"), (None,))[0]
        n_sp = nb.get((m, "spot"), (None,))[0]
        n_od = nb_list.get(m)
        ratio = f"{a_od / n_od:.1f}x" if a_od and n_od else ""
        lines.append(f"| {m} | {money(a_od)} | {money(a_3y)} | {money(a_sp)} | {money(n_od)} | {money(n_sp)} | {ratio} |")
    return "\n".join(lines)


def spot_discounts(azure_rows, nebius_rows, manual_rows):
    """Spot as a share of on-demand, per provider and GPU. Near 100% means no spare capacity."""
    az = medians_by(azure_rows, "gpu_model", "tier")
    nb = medians_by(nebius_rows, "gpu_model", "tier")
    nb_list = {r["gpu_model"]: float(r["usd_per_gpu_hour"]) for r in manual_rows
               if r["source"] == "nebius" and r["tier"] == "on_demand"}
    out = []
    for m in sorted({k[0] for k in az}, key=gpu_key):
        od, sp = az.get((m, "on_demand")), az.get((m, "spot"))
        if od and sp:
            out.append(("Azure", m, sp[0] / od[0]))
    for m in sorted(nb_list, key=gpu_key):
        sp = nb.get((m, "spot"))
        if sp:
            out.append(("Nebius", m, sp[0] / nb_list[m]))
    lines = ["| Provider | GPU | Spot as % of on-demand |", "| --- | --- | --- |"]
    lines += [f"| {p} | {m} | {share:.0%} |" for p, m, share in out]
    return "\n".join(lines), out


def nebius_trends(hourly_rows):
    """Per GPU: latest, 7-day and 30-day change, range and cross-region spread of hourly spot prices."""
    by_gpu_hour = defaultdict(lambda: defaultdict(list))
    for r in hourly_rows:
        by_gpu_hour[r["gpu_model"]][r["timestamp"]].append(float(r["usd_per_gpu_hour"]))
    stats = []
    for m in sorted(by_gpu_hour, key=gpu_key):
        hours = sorted(by_gpu_hour[m])
        series = [(h, st.median(by_gpu_hour[m][h])) for h in hours]
        last_t = dt.datetime.fromisoformat(series[-1][0].replace("Z", "+00:00"))

        def value_at(days):
            cutoff = last_t - dt.timedelta(days=days)
            earlier = [v for h, v in series if dt.datetime.fromisoformat(h.replace("Z", "+00:00")) <= cutoff]
            return earlier[-1] if earlier else None

        last = series[-1][1]
        v7, v30 = value_at(7), value_at(29)
        values = [v for _, v in series]
        regions_now = by_gpu_hour[m][hours[-1]]
        stats.append({
            "gpu": m,
            "last": last,
            "chg7": (last / v7 - 1) if v7 else None,
            "chg30": (last / v30 - 1) if v30 else None,
            "lo": min(values),
            "hi": max(values),
            "first": series[0][0][:10],
            "regions": len(regions_now),
            "spread": (min(regions_now), max(regions_now)),
            "points": len(series),
        })
    lines = [
        "| GPU | Latest median spot | 7-day change | 30-day change | 30-day low | 30-day high | Regions now (low to high) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in stats:
        lo, hi = s["spread"]
        lines.append(
            f"| {s['gpu']} | {money(s['last'])} | {pct(s['chg7'])} | {pct(s['chg30'])} | {money(s['lo'])} | "
            f"{money(s['hi'])} | {s['regions']} ({money(lo)} to {money(hi)}) |"
        )
    return "\n".join(lines), stats


def sources_table(present):
    lines = ["| Series | Origin | Collector | Cadence | Stored in |", "| --- | --- | --- | --- | --- |"]
    for key in present:
        s = SOURCES[key]
        lines.append(f"| {s['name']} | [{s['origin']}]({s['url']}) | `{s['collector']}` | {s['cadence']} | `{s['file']}` |")
    return "\n".join(lines)


def build(data_dir):
    cloud = read_csv(data_dir / "tidy" / "cloud_prices.csv")
    hourly = read_csv(data_dir / "tidy" / "nebius_spot_hourly.csv")
    manual = read_csv(data_dir / "manual" / "list_prices.csv")
    az_date, az_rows = latest_snapshot(cloud, "azure")
    nb_date, nb_rows = latest_snapshot(cloud, "nebius")
    az_days = len({r["date"] for r in cloud if r["source"] == "azure"})

    discount_md, discounts = spot_discounts(az_rows, nb_rows, manual)
    trend_md, trends = nebius_trends(hourly) if hourly else ("No hourly data yet.", [])

    out = [
        "# Compute price report",
        "",
        f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC from `data/`. "
        "Prices are USD per GPU-hour, Linux, medians across regions unless stated.",
        "",
        "## 1. Price levels by provider and tier",
        "",
        f"Azure snapshot {az_date or 'none'}; Nebius spot snapshot {nb_date or 'none'}; "
        "Nebius on-demand from its pricing page.",
        "",
        price_table(az_rows, nb_rows, manual),
        "",
        "## 2. Spot discount",
        "",
        "A spot price close to the on-demand price means the provider has little idle capacity of that GPU.",
        "",
        discount_md,
        "",
        "## 3. Nebius spot prices over time",
        "",
        "Hourly average spot price, median across regions.",
        "",
        trend_md,
        "",
        "## 4. Azure over time",
        "",
        f"{az_days} daily snapshot(s) so far. Day-over-day and weekly changes appear once a week of history exists.",
        "",
        "## Sources",
        "",
        sources_table([k for k in SOURCES if (k[0] == "azure" and az_rows) or (k == ("nebius", "spot") and nb_rows)
                       or (k == ("nebius", "list") and manual)]),
        "",
    ]
    return "\n".join(out), {"discounts": discounts, "trends": trends}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out", default="reports/latest.md")
    args = p.parse_args(argv)
    md, _ = build(Path(args.data_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
