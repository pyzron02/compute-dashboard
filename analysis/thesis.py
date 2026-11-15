"""Thesis watch: the signals that would change the view on Nebius and the neocloud trade.

Three triggers are checked by hand and logged in data/manual/thesis_triggers.csv with a source
link. One is computed from the price data: Nebius B300 spot below half of on-demand for a week.
Usage: python -m analysis.thesis [--data-dir data] [--alert-out PATH]
  With --alert-out, writes an alert body to PATH and prints PATH if any trigger has fired.
"""

import argparse
from pathlib import Path

B300_LINE = 0.5   # spot as a share of on-demand
B300_DAYS = 7     # consecutive daily medians below the line before it counts as fired
STATUS_ORDER = {"fired": 0, "watch": 1, "pending": 2, "ok": 3}


def b300_trigger(scarcity):
    days = [s for s in scarcity if s["provider"] == "Nebius" and s["gpu"] == "B300"]
    base = {
        "id": "b300_spot",
        "trigger": "Blackwell rental demand stays ahead of supply",
        "breaks_if": f"Nebius B300 spot stays below {B300_LINE:.0%} of on-demand for {B300_DAYS} days in a row",
        "source_url": "https://docs.nebius.com/signup-billing/spot-prices",
        "next_check": "daily (automatic)",
        "auto": True,
    }
    if not days:
        return {**base, "status": "pending", "last_checked": None, "evidence": "No B300 data yet."}
    last = days[-1]
    window = days[-B300_DAYS:]
    below = sum(d["ratio"] < B300_LINE for d in window)
    if len(window) == B300_DAYS and below == B300_DAYS:
        status = "fired"
    elif last["ratio"] < B300_LINE or below >= 3:
        status = "watch"
    else:
        status = "ok"
    return {**base, "status": status, "last_checked": last["date"],
            "evidence": f"Spot {last['ratio']:.0%} of on-demand on {last['date']}; "
                        f"below {B300_LINE:.0%} on {below} of the last {len(window)} days."}


def thesis_watch(scarcity, manual):
    rows = [{**r, "auto": False} for r in manual] + [b300_trigger(scarcity)]
    return sorted(rows, key=lambda r: STATUS_ORDER.get(r["status"], 9))


def markdown(rows):
    lines = ["| Signal | Status | Breaks the thesis if | Latest evidence | Next check |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['trigger']} | **{r['status']}** | {r['breaks_if']} | "
                     f"[{r['evidence']}]({r['source_url']}) | {r['next_check']} |")
    return lines


def main(argv=None):
    from analysis.build_site import build
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data")
    p.add_argument("--alert-out")
    args = p.parse_args(argv)
    rows = build(Path(args.data_dir))["thesis"]
    fired = [r for r in rows if r["status"] == "fired"]
    if not args.alert_out:
        print("\n".join(markdown(rows)))
    elif fired:
        body = ["A thesis trigger has fired. Review the Nebius and neocloud view.", ""]
        body += [f"- **{r['trigger']}**: {r['evidence']}" for r in fired]
        body += ["", "## All signals", ""] + markdown(rows)
        body += ["", "Dashboard: https://pyzron02.github.io/compute-dashboard/#thesis",
                 "Close this issue once the trigger has been reviewed; a new one opens if a trigger fires again."]
        Path(args.alert_out).write_text("\n".join(body) + "\n")
        print(args.alert_out)


if __name__ == "__main__":
    main()
