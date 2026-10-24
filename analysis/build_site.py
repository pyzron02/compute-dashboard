"""Build site/data.json for the dashboard page (site/index.html) from data/tidy and data/manual.

Everything the page shows is computed here, so the page itself only draws.
Usage: python -m analysis.build_site [--data-dir data] [--out site/data.json]
"""

import argparse
import datetime as dt
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from analysis.report import GPU_ORDER, SOURCES, gpu_key, read_csv

# Extra sources the page cites beyond the price series in analysis.report.SOURCES.
EXTRA_SOURCES = [
    {
        "name": "GPU dense BF16 tensor performance (for $ per PFLOP-hour)",
        "origin": "Epoch AI, Data on machine learning hardware",
        "url": "https://epoch.ai/data/machine-learning-hardware",
        "collector": "data/manual/gpu_specs.csv",
        "cadence": "Manual, copied Oct 24, 2026",
        "file": "data/manual/gpu_specs.csv",
    },
    {
        "name": "Chart annotations",
        "origin": "Event list with a link per event",
        "url": "https://github.com/pyzron02/compute-dashboard/blob/main/data/manual/events.csv",
        "collector": "data/manual/events.csv",
        "cadence": "Manual",
        "file": "data/manual/events.csv",
    },
]


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def market_start(hourly):
    """First hour any Nebius series moved off its starting value: before it, prices were a fixed rate."""
    first = {}
    moved = []
    for r in sorted(hourly, key=lambda r: r["timestamp"]):
        k = (r["region"], r["platform"])
        v = float(r["usd_per_gpu_hour"])
        if k not in first:
            first[k] = v
        elif v != first[k]:
            moved.append(r["timestamp"])
            break
    return moved[0][:10] if moved else None


def nebius_list(manual):
    return {r["gpu_model"]: float(r["usd_per_gpu_hour"]) for r in manual
            if r["source"] == "nebius" and r["tier"] == "on_demand"}


def scarcity_series(cloud, hourly, manual, start):
    """Spot price as a share of on-demand, per provider x GPU x day."""
    out = []
    # Nebius: daily median of hourly spot (all regions) over the list on-demand price.
    lst = nebius_list(manual)
    by = defaultdict(list)
    for r in hourly:
        day = r["timestamp"][:10]
        if start and day < start:
            continue
        by[(r["gpu_model"], day)].append(float(r["usd_per_gpu_hour"]))
    for (gpu, day), vals in by.items():
        if gpu in lst:
            spot = st.median(vals)
            out.append({"provider": "Nebius", "gpu": gpu, "date": day, "spot": round(spot, 4),
                        "on_demand": lst[gpu], "ratio": round(spot / lst[gpu], 4)})
    # Azure: median spot over median on-demand across regions, per daily snapshot.
    az = defaultdict(lambda: defaultdict(list))
    for r in cloud:
        if r["source"] == "azure" and r["tier"] in ("spot", "on_demand"):
            az[(r["gpu_model"], r["date"])][r["tier"]].append(float(r["usd_per_gpu_hour"]))
    for (gpu, day), tiers in az.items():
        if tiers["spot"] and tiers["on_demand"]:
            spot, od = st.median(tiers["spot"]), st.median(tiers["on_demand"])
            out.append({"provider": "Azure", "gpu": gpu, "date": day, "spot": round(spot, 4),
                        "on_demand": round(od, 4), "ratio": round(spot / od, 4)})
    return sorted(out, key=lambda r: (r["provider"], gpu_key(r["gpu"]), r["date"]))


def regional_series(hourly, start):
    """Nebius hourly spot per GPU x region, from the start of market pricing."""
    series = defaultdict(list)
    for r in sorted(hourly, key=lambda r: r["timestamp"]):
        if start and r["timestamp"][:10] < start:
            continue
        series[(r["gpu_model"], r["region"])].append([r["timestamp"], float(r["usd_per_gpu_hour"])])
    return [{"gpu": g, "region": reg, "points": pts}
            for (g, reg), pts in sorted(series.items(), key=lambda kv: (gpu_key(kv[0][0]), kv[0][1]))]


def latest(cloud, source):
    dates = sorted({r["date"] for r in cloud if r["source"] == source})
    return (dates[-1], [r for r in cloud if r["source"] == source and r["date"] == dates[-1]]) if dates else (None, [])


def med(rows, gpu, tier):
    vals = [float(r["usd_per_gpu_hour"]) for r in rows if r["gpu_model"] == gpu and r["tier"] == tier]
    return round(st.median(vals), 4) if vals else None


def price_matrix(cloud, manual, specs):
    """Latest price per GPU x provider x tier, plus $ per dense BF16 PFLOP-hour."""
    az_date, az = latest(cloud, "azure")
    nb_date, nb = latest(cloud, "nebius")
    lst = nebius_list(manual)
    rows = []
    for gpu in sorted({r["gpu_model"] for r in az + nb} | set(lst), key=gpu_key):
        pflops = specs.get(gpu)
        cells = {
            "azure_on_demand": med(az, gpu, "on_demand"),
            "azure_reserved_3y": med(az, gpu, "reserved_3y"),
            "azure_spot": med(az, gpu, "spot"),
            "nebius_on_demand": lst.get(gpu),
            "nebius_spot": med(nb, gpu, "spot"),
        }
        per_pflop = {k: (round(v / pflops, 4) if v is not None and pflops else None) for k, v in cells.items()}
        rows.append({"gpu": gpu, "pflops": pflops, "usd": cells, "usd_per_pflop": per_pflop})
    return {"azure_date": az_date, "nebius_date": nb_date, "rows": rows}


def tiles(hourly, scarcity, start):
    """Headline per GPU: Nebius spot now, its 7-day change, and spot as a share of on-demand."""
    by_hour = defaultdict(lambda: defaultdict(list))
    for r in hourly:
        by_hour[r["gpu_model"]][r["timestamp"]].append(float(r["usd_per_gpu_hour"]))
    latest_ratio = {}
    for s in scarcity:
        latest_ratio[(s["provider"], s["gpu"])] = s  # sorted by date, so the last one wins
    out = []
    for gpu in sorted(by_hour, key=gpu_key):
        hours = sorted(by_hour[gpu])
        now_t = parse_ts(hours[-1])
        now = st.median(by_hour[gpu][hours[-1]])
        week_ago = [h for h in hours if parse_ts(h) <= now_t - dt.timedelta(days=7)]
        prev = st.median(by_hour[gpu][week_ago[-1]]) if week_ago and (not start or week_ago[-1][:10] >= start) else None
        nb = latest_ratio.get(("Nebius", gpu))
        az = latest_ratio.get(("Azure", gpu))
        ratio = nb["ratio"] if nb else None
        out.append({
            "gpu": gpu,
            "spot": round(now, 4),
            "as_of": hours[-1],
            "change_7d": round(now / prev - 1, 4) if prev else None,
            "nebius_ratio": ratio,
            "azure_ratio": az["ratio"] if az else None,
            "status": None if ratio is None else ("tight" if ratio >= 0.6 else "balanced" if ratio >= 0.35 else "loose"),
            "regions": len(by_hour[gpu][hours[-1]]),
        })
    return out


def health(cloud, hourly):
    today = dt.date.today()
    out = []
    for source in ("azure", "nebius"):
        dates = sorted({r["date"] for r in cloud if r["source"] == source})
        rows = [r for r in cloud if r["source"] == source and dates and r["date"] == dates[-1]]
        coverage = defaultdict(set)
        for r in rows:
            coverage[r["gpu_model"]].add(r["region"])
        last = dates[-1] if dates else None
        age = (today - dt.date.fromisoformat(last)).days if last else None
        out.append({
            "source": source,
            "last_snapshot": last,
            "days_collected": len(dates),
            "rows_latest": len(rows),
            "regions_per_gpu": {g: len(v) for g, v in sorted(coverage.items(), key=lambda kv: gpu_key(kv[0]))},
            "status": "ok" if age is not None and age <= 1 else "stale",
        })
    if hourly:
        out.append({
            "source": "nebius hourly",
            "last_snapshot": max(r["timestamp"] for r in hourly),
            "days_collected": len({r["timestamp"][:10] for r in hourly}),
            "rows_latest": len(hourly),
            "regions_per_gpu": {},
            "status": "ok",
        })
    return out


def build(data_dir):
    cloud = read_csv(data_dir / "tidy" / "cloud_prices.csv")
    hourly = read_csv(data_dir / "tidy" / "nebius_spot_hourly.csv")
    manual = read_csv(data_dir / "manual" / "list_prices.csv")
    specs = {r["gpu_model"]: float(r["dense_bf16_tflops"]) / 1000
             for r in read_csv(data_dir / "manual" / "gpu_specs.csv")}
    events = read_csv(data_dir / "manual" / "events.csv")
    start = market_start(hourly)
    scarcity = scarcity_series(cloud, hourly, manual, start)
    return {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_start": start,
        "gpu_order": GPU_ORDER,
        "tiles": tiles(hourly, scarcity, start),
        "scarcity": scarcity,
        "regional": regional_series(hourly, start),
        "prices": price_matrix(cloud, manual, specs),
        "events": events,
        "health": health(cloud, hourly),
        "sources": list(SOURCES.values()) + EXTRA_SOURCES,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out", default="site/data.json")
    args = p.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(Path(args.data_dir)), separators=(",", ":")))
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
