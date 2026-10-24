"""Weekly digest: what moved in the last 7 days, with context and sources.

Builds on the same numbers as the dashboard (analysis.build_site) and writes
reports/weekly/<date>.md. The workflow posts it as a GitHub issue each Monday.
Usage: python -m analysis.digest [--data-dir data] [--out-dir reports/weekly]
"""

import argparse
import datetime as dt
import statistics as st
from collections import defaultdict
from pathlib import Path

from analysis.build_site import build, parse_ts
from analysis.report import gpu_key, read_csv

DASHBOARD = "https://pyzron02.github.io/compute-dashboard/"
REPO = "https://github.com/pyzron02/compute-dashboard"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def money(x):
    return "n/a" if x is None else f"${x:,.2f}"


def pct(x):
    return "n/a" if x is None else f"{x:+.0%}"


def status_of(ratio):
    if ratio is None:
        return None
    return "tight" if ratio >= 0.6 else "balanced" if ratio >= 0.35 else "loose"


def week_mean(rows, gpu, start, end, key="share"):
    vals = [r[key] for r in rows if r["gpu"] == gpu and start <= r["date"] < end]
    return st.mean(vals) if vals else None


def regional_moves(hourly, now):
    """Largest 7-day change of any single Nebius region, so a median move can be checked."""
    by = defaultdict(list)
    for r in hourly:
        by[(r["gpu_model"], r["region"])].append((parse_ts(r["timestamp"]), float(r["usd_per_gpu_hour"])))
    moves = []
    for (gpu, region), pts in by.items():
        pts.sort()
        before = [v for t, v in pts if t <= now - dt.timedelta(days=7)]
        if before and pts[-1][1] and before[-1]:
            moves.append((pts[-1][1] / before[-1] - 1, gpu, region, before[-1], pts[-1][1]))
    return sorted(moves, key=lambda m: -abs(m[0]))


def azure_changes(cloud, today):
    """Median Azure price change per GPU and tier versus the snapshot closest to 7 days earlier."""
    dates = sorted({r["date"] for r in cloud if r["source"] == "azure"})
    if len(dates) < 2:
        return None, []
    target = (dt.date.fromisoformat(dates[-1]) - dt.timedelta(days=7)).isoformat()
    base = max([d for d in dates if d <= target] or [dates[0]])
    if base == dates[-1]:
        return None, []

    def med(date):
        g = defaultdict(list)
        for r in cloud:
            if r["source"] == "azure" and r["date"] == date and r["tier"] in ("on_demand", "spot", "reserved_3y"):
                g[(r["gpu_model"], r["tier"])].append(float(r["usd_per_gpu_hour"]))
        return {k: st.median(v) for k, v in g.items()}

    old, new = med(base), med(dates[-1])
    out = [(k[0], k[1], old[k], new[k], new[k] / old[k] - 1) for k in new if k in old and old[k]]
    return base, sorted(out, key=lambda c: (gpu_key(c[0]), c[1]))


def render(data, cloud, hourly, events, today):
    now = max((parse_ts(r["timestamp"]) for r in hourly), default=dt.datetime.now(dt.timezone.utc))
    week_ago = (today - dt.timedelta(days=7)).isoformat()
    two_weeks = (today - dt.timedelta(days=14)).isoformat()
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    lines = [f"# Compute prices, week to {today:%b} {today.day}, {today.year}", "",
             f"Live dashboard: {DASHBOARD}", ""]

    # 1. Headlines per GPU (Nebius spot), sorted by size of move.
    scar = data["scarcity"]
    rows = []
    for t in data["tiles"]:
        prev_ratio = [s["ratio"] for s in scar if s["provider"] == "Nebius" and s["gpu"] == t["gpu"] and s["date"] <= week_ago]
        before = status_of(prev_ratio[-1]) if prev_ratio else None
        cap_now = week_mean(data["at_cap"], t["gpu"], week_ago, tomorrow)
        cap_prev = week_mean(data["at_cap"], t["gpu"], two_weeks, week_ago)
        rows.append((t, before, cap_now, cap_prev))
    rows.sort(key=lambda r: -abs(r[0]["change_7d"] or 0))

    lines += ["## What moved", ""]
    for t, before, cap_now, cap_prev in rows:
        flip = f", {before} → {t['status']}" if before and t["status"] and before != t["status"] else ""
        cap = ""
        if cap_now is not None:
            cap = f"; at the on-demand cap {cap_now:.0%} of the time"
            if cap_prev is not None:
                cap += f" (prior week {cap_prev:.0%})"
        plural = "s" if t["regions"] != 1 else ""
        ratio = (f" Spot is {t['nebius_ratio']:.0%} of on-demand" if t["nebius_ratio"] is not None else " Median")
        lines.append(f"- **{t['gpu']}** Nebius spot {money(t['spot'])}/GPU-hr, {pct(t['change_7d'])} on the week"
                     f"{flip}{cap}.{ratio} across {t['regions']} region{plural}.")
    lines.append("")

    moves = regional_moves(hourly, now)[:3]
    if moves:
        lines += ["Largest single-region moves (check these before reading a median move as a market move):", ""]
        lines += [f"- {g} in {reg}: {money(a)} → {money(b)} ({pct(m)})" for m, g, reg, a, b in moves]
        lines.append("")

    base, az = azure_changes(cloud, today)
    lines += ["## Azure list prices", ""]
    if not az:
        lines += ["Not enough history yet for a week-on-week comparison.", ""]
    else:
        changed = [c for c in az if abs(c[4]) >= 0.005]
        if changed:
            lines += [f"Median change since {base}:", ""]
            lines += [f"- {g} {tier.replace('_', ' ')}: {money(a)} → {money(b)} ({pct(c)})" for g, tier, a, b, c in changed]
        else:
            lines.append(f"No median price changes since {base}.")
        lines.append("")

    # 2. Patterns (only stated when every Blackwell GPU agrees).
    intraday = {g["gpu"]: g for g in data["intraday"]["gpus"]}
    lines += ["## Patterns", ""]
    blackwell = [intraday[g] for g in ("B300", "B200") if g in intraday]
    weekend = [(g["gpu"], g["by_weekday"][5]) for g in blackwell if g["by_weekday"][5] is not None]
    if weekend and all(v < -0.05 for _, v in weekend):
        n = min(g["weekday_days"] for g in blackwell)
        lines.append(f"- Blackwell spot dips on Saturdays ({', '.join(f'{g} {pct(v)}' for g, v in weekend)} "
                     "against the surrounding week), "
                     f"based on {n} trend-adjusted days. Treat as early evidence.")
    for g in blackwell:
        hours = g["by_hour"]
        if all(v is not None for v in hours):
            hi, lo = max(range(24), key=lambda h: hours[h]), min(range(24), key=lambda h: hours[h])
            if hours[hi] - hours[lo] >= 0.1:
                lines.append(f"- {g['gpu']} is dearest around {hi:02d}:00 UTC ({pct(hours[hi])}) and cheapest around "
                             f"{lo:02d}:00 UTC ({pct(hours[lo])}), over {g['hour_days']} full days.")
    if lines[-1] == "":
        lines.append("- No consistent time-of-day or weekday pattern yet.")
    lines.append("")

    # 3. Context: events in the week, as possible reasons, never as proven causes.
    week_events = [e for e in events if week_ago <= e["date"] <= today.isoformat()]
    lines += ["## Context this week", ""]
    lines += ([f"- {e['date']}: [{e['label']}]({e['url']})" for e in week_events]
              or ["- No events logged. Add one to `data/manual/events.csv` with a source link."])
    lines += ["", "Events are listed as possible context. A price move that lines up with one is not proof it caused it.", ""]

    # 4. Health.
    stale = [h for h in data["health"] if h["status"] != "ok"]
    lines += ["## Data health", ""]
    lines += ([f"- {h['source']}: last update {h['last_snapshot']} (stale)" for h in stale] or ["- All feeds updated on schedule."])
    lines += ["", "## Sources", ""]
    lines += [f"- {s['name']}: [{s['origin']}]({s['url']})" for s in data["sources"]]
    lines += ["", f"Code and raw data: {REPO}", ""]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out-dir", default="reports/weekly")
    p.add_argument("--date", default=dt.date.today().isoformat())
    args = p.parse_args(argv)
    data_dir = Path(args.data_dir)
    today = dt.date.fromisoformat(args.date)
    md = render(build(data_dir), read_csv(data_dir / "tidy" / "cloud_prices.csv"),
                read_csv(data_dir / "tidy" / "nebius_spot_hourly.csv"),
                read_csv(data_dir / "manual" / "events.csv"), today)
    out = Path(args.out_dir) / f"{today.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(out)


if __name__ == "__main__":
    main()
