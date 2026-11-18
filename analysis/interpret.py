"""Plain-language readings for each dashboard chart.

For every chart this builds three short texts and a tone:
  how   - what the chart shows and how to read it (fixed)
  now   - what the latest data says (computed from site/data.json content)
  means - what that reading implies for the neocloud thesis
  tone  - "supports", "against", "mixed" or "none" (no data yet)

The thesis being tested: demand and pricing for AI compute stay strong enough that
neoclouds keep pricing power; the binding risk is funding. The thresholds used here
are the same ones as the thesis watch (spot at 60%+ of on-demand is tight, under 50%
for a week is the B300 trigger, new deals at or above $25M per MW).
"""

import datetime as dt
import statistics

TIGHT, TRIGGER, LOOSE = 0.60, 0.50, 0.35
DEAL_FLOOR = 25.0


def pct(x, digits=0):
    return f"{x * 100:.{digits}f}%"


def signed_pct(x, digits=0):
    return f"{'+' if x >= 0 else ''}{x * 100:.{digits}f}%"


def money(x, unit="B"):
    """$B by default; amounts under $1B are shown in $M."""
    sign, x = ("-" if x < 0 else ""), abs(x)
    if unit == "B" and x < 1:
        return f"{sign}${x * 1000:,.0f}M"
    return f"{sign}${x:,.1f}{unit}" if x < 100 else f"{sign}${x:,.0f}{unit}"


def reading(how, now, means, tone):
    return {"how": how, "now": now, "means": means, "tone": tone}


def none(how, why):
    return reading(how, why, "No reading until data arrives.", "none")


def nebius_ratios(scarcity, gpu):
    return [r for r in scarcity if r["provider"] == "Nebius" and r["gpu"] == gpu and r.get("ratio") is not None]


def full_days(rows, today):
    """Drop today's row: it covers only part of the day."""
    return [r for r in rows if r["date"] < today] or rows


# --- Prices and scarcity ---------------------------------------------------

def tiles_reading(site):
    how = ("Each tile is the latest Nebius spot price for one GPU (median across regions) with its "
           "7-day change. The badge compares spot with on-demand: tight is 60% or more, loose is under 35%.")
    t = [x for x in site.get("tiles", []) if x.get("status")]
    if not t:
        return none(how, "No spot prices yet.")
    by = {s: [x["gpu"] for x in t if x["status"] == s] for s in ("tight", "balanced", "loose")}
    parts = [f"{s}: {', '.join(g)}" for s, g in by.items() if g]
    now = "; ".join(parts) + "."
    now = now[0].upper() + now[1:]
    moves = [f"{x['gpu']} {signed_pct(x['change_7d'])}" for x in t if x.get("change_7d") is not None]
    if moves:
        now += " 7-day change: " + ", ".join(moves) + "."
    blackwell = [x for x in t if x["gpu"] in ("B300", "B200")]
    if blackwell and all(x["status"] == "loose" for x in blackwell):
        return reading(how, now, "Spare Blackwell capacity is being sold cheaply right now, which cuts against "
                       "\"compute is sold out\". One snapshot; the scarcity chart below shows whether it lasts.", "against")
    if by["tight"]:
        return reading(how, now, "At least one GPU class is close to sold out on spot, which supports pricing power.", "supports")
    return reading(how, now, "Spot capacity is available at a discount but not dumped; neither tight nor slack.", "mixed")


def scarcity_reading(site):
    how = ("Daily spot price as a share of on-demand, per GPU. Near 100% means spot buyers pay close to list, "
           "so there is little idle capacity. A falling line means more idle capacity is being sold off cheaply. "
           "60% and above is tight; under 50% for seven days running is the B300 thesis trigger.")
    today = site.get("generated", "")[:10]
    rows = full_days(nebius_ratios(site.get("scarcity", []), "B300"), today)
    if len(rows) < 3:
        return none(how, "Not enough B300 history yet.")
    last7 = rows[-7:]
    avg7 = statistics.mean(r["ratio"] for r in last7)
    below = sum(r["ratio"] < TRIGGER for r in last7)
    prior = rows[-37:-30] or rows[:7]
    avg_prior = statistics.mean(r["ratio"] for r in prior)
    now = (f"B300 averaged {pct(avg7)} of on-demand over the last {len(last7)} full days "
           f"(versus {pct(avg_prior)} about a month earlier), below 50% on {below} of them. "
           f"Latest full day {rows[-1]['date']}: {pct(rows[-1]['ratio'])}.")
    others = []
    for g in ("B200", "H200", "H100"):
        r = full_days(nebius_ratios(site["scarcity"], g), today)[-7:]
        if r:
            others.append(f"{g} {pct(statistics.mean(x['ratio'] for x in r))}")
    if others:
        now += " 7-day averages for other GPUs: " + ", ".join(others) + "."
    if avg7 >= TIGHT:
        return reading(how, now, "Blackwell capacity is close to sold out; this supports neocloud pricing power.", "supports")
    if below >= 7:
        return reading(how, now, "The B300 trigger has fired: a week of cheap spot means real idle Blackwell capacity. "
                       "Rethink the pricing-power leg of the thesis.", "against")
    if avg7 < TRIGGER:
        return reading(how, now, "Blackwell spot has loosened. Not yet the seven-day trigger, but it is moving the wrong "
                       "way; watch whether new capacity coming online is outrunning demand.", "against")
    means = "Between tight and slack: there is some idle Blackwell capacity, but spot is not being dumped."
    if rows[-1]["ratio"] < TRIGGER:
        means += " The latest full day was below 50%, so the trigger count has started; seven in a row would fire it."
    return reading(how, now, means, "mixed")


def regional_reading(site):
    how = ("Hourly Nebius spot price in each region, $ per GPU-hour. When regions move together the cause is "
           "market-wide (demand or new supply); when one region drops alone it is usually a local capacity addition. "
           "Dashed lines mark dated events.")
    reg = [r for r in site.get("regional", []) if r["gpu"] == "B300" and r["points"]]
    if not reg:
        return none(how, "No regional B300 prices yet.")
    moves = []
    for r in reg:
        pts = r["points"]
        last = pts[-1][1]
        week_ago = next((v for t, v in reversed(pts) if t <= shift(pts[-1][0], -7)), pts[0][1])
        moves.append((r["region"], last, (last / week_ago - 1) if week_ago else 0))
    now = "B300 latest: " + ", ".join(f"{g} ${v:.2f} ({signed_pct(c)} vs a week ago)" for g, v, c in moves) + "."
    down = sum(c < -0.1 for _, _, c in moves)
    up = sum(c > 0.1 for _, _, c in moves)
    if down == len(moves):
        return reading(how, now, "Every region fell, so the softness is market-wide rather than one new cluster.", "against")
    if up == len(moves):
        return reading(how, now, "Every region rose: demand is outrunning spare capacity across the network.", "supports")
    return reading(how, now, "Regions are moving apart, which points to local capacity changes rather than a demand shift.", "mixed")


def shift(ts, days):
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) + dt.timedelta(days=days)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def atcap_reading(site):
    how = ("Share of each day that spot sat within 3% of on-demand, meaning spot capacity was effectively sold out. "
           "Higher and rising means buyers are queuing for capacity.")
    today = site.get("generated", "")[:10]
    rows = full_days([r for r in site.get("at_cap", []) if r["gpu"] == "B300"], today)
    if len(rows) < 7:
        return none(how, "Not enough B300 history yet.")
    last, prev = rows[-7:], rows[-14:-7]
    a = statistics.mean(r["share"] for r in last)
    now = f"B300 sat at the cap {pct(a)} of the time over the last 7 full days"
    if prev:
        b = statistics.mean(r["share"] for r in prev)
        now += f", versus {pct(b)} the week before."
    else:
        b = None
        now += "."
    if a >= 0.25:
        return reading(how, now, "Blackwell spot sells out for a large part of each day: strong short-dated demand.", "supports")
    if b is not None and a < b * 0.6:
        return reading(how, now, "Sold-out hours are shrinking, consistent with new capacity or softer short-term demand.", "against")
    return reading(how, now, "Spot rarely sells out; demand is met without queuing.", "mixed")


def shape_reading(site):
    how = ("How spot prices move within a day (UTC) and across the week, after removing the trend. Peaks in "
           "working hours point to interactive and inference use, which is stickier demand than batch training. "
           "A flat profile means usage is mostly round-the-clock jobs.")
    g = next((x for x in site.get("intraday", {}).get("gpus", []) if x["gpu"] == "B300" and any(x["by_hour"])), None)
    if not g:
        return none(how, "Not enough intraday data yet.")
    hours = [(h, v) for h, v in enumerate(g["by_hour"]) if v is not None]
    hi, lo = max(hours, key=lambda x: x[1]), min(hours, key=lambda x: x[1])
    swing = hi[1] - lo[1]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    wd = [(days[i], v) for i, v in enumerate(g.get("by_weekday", [])) if v is not None]
    now = (f"B300 is dearest around {hi[0]:02d}:00 UTC ({signed_pct(hi[1], 1)}) and cheapest around "
           f"{lo[0]:02d}:00 UTC ({signed_pct(lo[1], 1)}), a {pct(swing)} swing.")
    if wd:
        wlo = min(wd, key=lambda x: x[1])
        now += f" Cheapest day: {wlo[0]} ({signed_pct(wlo[1], 1)})."
    now += f" Based on {g['hour_days']} days, so treat it as early."
    if swing >= 0.05:
        return reading(how, now, f"A daily cycle this size means part of the demand is time-sensitive (products and "
                       f"people in use), not only round-the-clock training. The peak falls in {zone(hi[0])}. "
                       "This chart describes how capacity is used rather than whether the thesis holds.", "mixed")
    return reading(how, now, "Little daily cycle: usage looks like round-the-clock batch work.", "mixed")


def zone(hour):
    """Which working day an hour (UTC) falls in."""
    if 13 <= hour <= 22:
        return "the US working day"
    if 7 <= hour <= 12:
        return "the European working day"
    return "the US evening and Asian morning"


def prices_reading(site):
    how = ("List and spot prices by provider and tier, per GPU-hour or per PFLOP-hour (dense BF16) so newer "
           "chips can be compared with older ones. The gap between spot and on-demand is the discount for "
           "interruptible capacity.")
    rows = site.get("prices", {}).get("rows", [])
    disc = []
    for r in rows:
        od, sp = r["usd"].get("nebius_on_demand"), r["usd"].get("nebius_spot")
        if od and sp:
            disc.append((r["gpu"], 1 - sp / od))
    cheap = []
    for r in rows:
        vals = {k: v for k, v in (r.get("usd_per_pflop") or {}).items() if v}
        if vals:
            k = min(vals, key=vals.get)
            cheap.append((r["gpu"], vals[k], k))
    if not disc and not cheap:
        return none(how, "No price rows yet.")
    now = ""
    if disc:
        now += "Nebius spot discount to on-demand: " + ", ".join(f"{g} {pct(d)}" for g, d in disc) + ". "
    if cheap:
        g, v, k = min(cheap, key=lambda x: x[1])
        now += f"Cheapest compute per PFLOP-hour: {g} at ${v:.2f} ({k.replace('_', ' ')})."
    deep = [g for g, d in disc if d > 1 - LOOSE]
    if deep:
        return reading(how, now.strip(), f"Discounts above 65% ({', '.join(deep)}) mean a lot of idle capacity is "
                       "on offer; on-demand list prices are not what the marginal buyer pays.", "against")
    return reading(how, now.strip(), "Discounts are moderate: list prices are holding as a reference.", "mixed")


# --- Facts -----------------------------------------------------------------

def capex_reading(site):
    how = ("Quarterly capital spending by Microsoft, Alphabet, Amazon, Meta and Oracle, $B, from SEC filings. "
           "This is the demand that ends up as GPU orders and neocloud leases. The line is year-on-year growth "
           "of the five-company total.")
    q = [r for r in site["markets"]["facts"].get("capex", []) if r.get("complete")]
    if len(q) < 2:
        return none(how, "SEC data not collected yet.")
    last, prev = q[-1], q[-2]
    qoq = last["total"] / prev["total"] - 1
    now = f"{last['quarter']}: {money(last['total'])}, {signed_pct(qoq)} on the quarter"
    if last.get("yoy") is not None:
        now += f" and {signed_pct(last['yoy'])} on a year ago"
    top = max(last["by_company"].items(), key=lambda kv: kv[1])
    now += f". Largest spender: {top[0]} at {money(top[1])}."
    if qoq > 0 and (last.get("yoy") or 0) > 0:
        return reading(how, now, "Capex is still accelerating, so end demand for compute is growing. This leg of the "
                       "thesis holds; the \"AI is a bubble\" break condition (capex falling quarter on quarter) is not met.", "supports")
    if qoq < 0:
        return reading(how, now, "Capex fell on the quarter. One quarter can be timing, but two would confirm the "
                       "bubble narrative's first condition.", "against")
    return reading(how, now, "Capex is flat; demand growth is pausing.", "mixed")


def latest(rows, ticker, field):
    for r in reversed([r for r in rows if r["ticker"] == ticker]):
        if r.get(field) is not None:
            return r[field], r["quarter"]
    return None, None


def funding_reading(site):
    how = ("Left: each neocloud's debt, cash and deferred revenue (mostly customer prepayments) at quarter end, $B. "
           "Prepayments growing faster than debt means customers, not lenders, are paying for the build. "
           "Right: quarterly interest expense against operating income; interest above operating income means "
           "the business does not yet cover its borrowing costs from operations.")
    rows = site["markets"]["facts"].get("funding", [])
    if not rows:
        return none(how, "No funding data yet.")
    parts, uncovered, prepaid = [], [], []
    for t in sorted({r["ticker"] for r in rows}):
        debt, dq = latest(rows, t, "debt")
        dr, _ = latest(rows, t, "deferred_revenue")
        ie, iq = latest(rows, t, "interest_expense")
        oi, oq = latest(rows, t, "operating_income")
        bits = []
        if debt is not None:
            bits.append(f"debt {money(debt)} (at {dq})")
        if dr is not None:
            bits.append(f"prepayments {money(dr)}")
        if ie is not None and oi is not None and iq == oq:
            bits.append(f"interest {money(ie)} vs operating income {money(oi)}")
            if ie > oi:
                uncovered.append(t)
        if debt and dr and dr >= debt * 0.5:
            prepaid.append(t)
        if bits:
            parts.append(f"{t}: " + ", ".join(bits))
    now = "; ".join(parts) + "."
    means = []
    if prepaid:
        means.append(f"{', '.join(prepaid)} {'is' if len(prepaid) == 1 else 'are'} largely customer-funded "
                     "(prepayments at least half of debt)")
    if uncovered:
        means.append(f"{', '.join(uncovered)} {'does' if len(uncovered) == 1 else 'do'} not cover interest from "
                     f"operating income, so {'it depends' if len(uncovered) == 1 else 'they depend'} on refinancing staying open")
    text = ("; ".join(means) + ". " if means else "") + "This is the funding risk the thesis flags as binding."
    tone = "mixed" if prepaid and uncovered else "against" if uncovered else "supports" if prepaid else "mixed"
    return reading(how, now, text[0].upper() + text[1:], tone)


def deals_reading(site):
    how = ("One dot per disclosed contract, $M of revenue per MW per year. Higher means customers pay more for the same "
           "power, which is pricing power. Short contracts usually price higher than multi-year ones.")
    deals = site["markets"]["facts"].get("deals", [])
    if not deals:
        return none(how, "No deals logged yet.")
    deals = sorted(deals, key=lambda d: d["date"])
    last = deals[-1]
    med = statistics.median(d["usd_m_per_mw_year"] for d in deals)
    now = (f"Latest: {last['neocloud']} at ${last['usd_m_per_mw_year']:.0f}M per MW ({last['date']}). "
           f"Median of {len(deals)} deals: ${med:.0f}M. Range ${min(d['usd_m_per_mw_year'] for d in deals):.0f}M "
           f"to ${max(d['usd_m_per_mw_year'] for d in deals):.0f}M.")
    if last["usd_m_per_mw_year"] >= DEAL_FLOOR:
        return reading(how, now, "New deals are still pricing at or above $25M per MW, the level the bull case needs. "
                       "Contract pricing has not cracked even while spot loosened.", "supports")
    return reading(how, now, "The latest deal priced below $25M per MW; if more follow, pricing power is fading.", "against")


def capacity_reading(site):
    how = ("Capacity each company says it has contracted against what is live, in GW. The gap is the build still to "
           "deliver: it is revenue in waiting, and also the money and power still to be found.")
    cap = site["markets"]["facts"].get("capacity", [])
    both = [c for c in cap if c.get("contracted_gw") and c.get("live_gw")]
    if not cap:
        return none(how, "No capacity logged yet.")
    parts = [f"{c['company']}: {c['live_gw']:.1f} of {c['contracted_gw']:.1f} GW live ({pct(c['live_gw'] / c['contracted_gw'])})"
             for c in both]
    other = [c["company"] for c in cap if c not in both]
    now = "; ".join(parts) + ("." if parts else "")
    if other:
        now += f" Only one side disclosed for {', '.join(other)}."
    return reading(how, now.strip(), "Most contracted capacity is not built yet. Demand is booked; delivery and its "
                   "funding are where the thesis can still fail.", "mixed")


def sites_reading(site):
    how = ("Dated site delays, cancellations and financing gaps. Each one moves revenue later or puts it at risk; "
           "a cluster of them means power and money, not demand, are the constraint.")
    s = site["markets"]["facts"].get("sites", [])
    if not s:
        return none(how, "No site events logged.")
    gen = site.get("generated", "")[:10] or dt.date.today().isoformat()
    cutoff = (dt.date.fromisoformat(gen) - dt.timedelta(days=60)).isoformat()
    recent = [x for x in s if x["date"] >= cutoff]
    counts = {}
    for x in recent:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    now = (f"{len(recent)} events in the last 60 days: " + ", ".join(f"{n} {k}" for k, n in counts.items()) + ". "
           f"Latest: {s[-1]['company']}, {s[-1]['detail'][0].lower() + s[-1]['detail'][1:]}.")
    tone = "against" if counts.get("cancelled") or len(recent) >= 3 else "mixed"
    return reading(how, now, "Delivery is slipping on power and financing. That pushes revenue out rather than "
                   "removing it, unless sites are cancelled outright.", tone)


def tsmc_reading(site):
    how = ("TSMC's monthly revenue, NT$ billion, with a 3-month average. TSMC makes almost every AI accelerator, so "
           "this is an early read on how many chips are being shipped, about a quarter ahead of neocloud capacity.")
    t = site["markets"]["facts"].get("tsmc", [])
    if len(t) < 4:
        return none(how, "Not enough months yet.")
    last, first = t[-1], t[0]
    avg_now, avg_prev = t[-1].get("avg3"), t[-4].get("avg3")
    now = f"{last['month']}: NT${last['ntd_billion']:.0f}B"
    if avg_now and avg_prev:
        now += f"; 3-month average {signed_pct(avg_now / avg_prev - 1)} on the prior three months"
    now += f"; {signed_pct(last['ntd_billion'] / first['ntd_billion'] - 1)} since {first['month']}."
    if avg_now and avg_prev and avg_now > avg_prev:
        return reading(how, now, "Chip output is still rising, so supply keeps arriving. Good for demand, but it is "
                       "also the new capacity that can loosen spot prices if buyers do not keep up.", "supports")
    return reading(how, now, "Chip shipments have stalled; watch for a demand slowdown upstream.", "against")


# --- Speculation -----------------------------------------------------------

def revisions_reading(site):
    how = ("Each bar is a guided range, drawn as a share of the first guide's midpoint so items of different size "
           "share an axis. Bars moving right are raises; left are cuts; a shorter bar is a narrower range.")
    rv = site["markets"]["speculation"].get("revisions", [])
    if not rv:
        return none(how, "No revisions logged.")
    parts, ups, downs = [], 0, 0
    for r in rv:
        p = r["points"]
        if len(p) < 2:
            continue
        a, b = (p[0]["low"] + p[0]["high"]) / 2, (p[-1]["low"] + p[-1]["high"]) / 2
        ch = b / a - 1
        ups += ch > 0.005
        downs += ch < -0.005
        parts.append(f"{r['label']} {signed_pct(ch, 1)} at the midpoint")
    now = "; ".join(parts) + "."
    means = ("Revenue guides are being trimmed while capex guides rise: companies are spending more to deliver "
             "later. That is the timing problem, not a demand problem." if downs and ups else
             "Guides are moving up: management sees demand holding." if ups and not downs else
             "Guides are moving down." if downs else "Guides are unchanged.")
    return reading(how, now, means, "mixed" if ups and downs else "supports" if ups else "against" if downs else "mixed")


def targets_reading(site):
    how = ("Published analyst price targets (dots) against the latest close (bar). A close far below the targets "
           "means the market does not believe the analysts' forecasts, or the targets are stale.")
    sp = site["markets"]["speculation"]
    t, close = sp.get("targets", []), sp.get("target_prices", {})
    parts = []
    for sym, c in close.items():
        v = [x["usd"] for x in t if x["symbol"] == sym]
        if v:
            med = statistics.median(v)
            parts.append((sym, c["close"], med, min(v), max(v)))
    if not parts:
        return none(how, "No targets logged.")
    now = "; ".join(f"{s}: close ${c:.0f} vs median target ${m:.0f} (range ${lo:.0f}-${hi:.0f}), "
                    f"{signed_pct(m / c - 1)} implied" for s, c, m, lo, hi in parts) + "."
    wide = [s for s, c, m, lo, hi in parts if hi / lo > 2]
    means = "Analysts still see large upside, so the gap is a perception gap rather than a consensus downgrade."
    if wide:
        means += f" The spread of targets for {', '.join(wide)} is very wide (more than 2x), which shows real disagreement."
    return reading(how, now, means, "mixed")


def implied_reading(site):
    how = ("The move options traders priced in before earnings (±) against what the stock actually did. A move far "
           "outside the implied range means the result surprised; the direction says which way.")
    m = site["markets"]["speculation"].get("implied_moves", [])
    if not m:
        return none(how, "No earnings logged.")
    parts = []
    for x in m:
        s = f"{x['symbol']} {x['event']}: actual {x['actual_pct']:+.0f}%"
        if x.get("implied_pct"):
            s += f" vs ±{x['implied_pct']:.0f}% implied"
        parts.append(s)
    now = "; ".join(parts) + "."
    outside = [x["symbol"] for x in m if x.get("implied_pct") and abs(x["actual_pct"]) > x["implied_pct"]]
    signs = {x["actual_pct"] > 0 for x in m}
    if len(signs) > 1:
        means = ("Results moved these stocks in opposite directions, so investors are telling companies apart on "
                 "delivery and funding rather than trading the group as one bet on demand.")
    else:
        means = "Results moved the group the same way, so the market is trading the sector as a whole."
    if outside:
        means += f" {', '.join(outside)} moved more than options priced in, a genuine surprise."
    return reading(how, now, means, "mixed")


# --- Perception ------------------------------------------------------------

def basket_reading(site):
    how = ("Top: share prices indexed to 100 at the start date, with an equal-weight neocloud basket. Bottom: B300 "
           "spot as a share of on-demand and deal prices per MW, on the same time axis. When prices fall while the "
           "bottom panel holds, the market is pricing fear rather than the fundamentals shown here.")
    series = {s["symbol"]: s["points"] for s in site["markets"]["perception"].get("basket", {}).get("series", [])}
    b = series.get("Neocloud basket")
    if not b or len(b) < 25:
        return none(how, "Not enough share-price history yet.")
    last = b[-1][1]
    peak = max(b, key=lambda p: p[1])
    month = b[-22][1]
    now = (f"The basket is at {last:.0f} ({b[-1][0]}), {signed_pct(last / month - 1)} over the last month and "
           f"{signed_pct(last / peak[1] - 1)} from its {peak[0]} peak.")
    nv = series.get("NVDA")
    if nv:
        now += f" Nvidia on the same index: {nv[-1][1]:.0f}."
    deals = site["markets"]["perception"].get("deal_points", [])
    if last < month and deals and deals[-1][1] >= DEAL_FLOOR:
        return reading(how, now, "Shares are falling while contract prices hold: the sell-off is about funding and "
                       "Nvidia, not about contract pricing. Spot softening in November is the one fundamental that "
                       "agrees with the price action.", "mixed")
    if last >= month:
        return reading(how, now, "Shares are recovering alongside the fundamentals.", "supports")
    return reading(how, now, "Shares and fundamentals are both weakening.", "against")


def attention_reading(site):
    how = ("Share of global online news that mentions each term, from GDELT. Spikes in \"AI bubble\" coverage "
           "often come near local lows in sentiment; rising neocloud coverage without a price rise shows attention "
           "without conviction.")
    a = site["markets"]["perception"].get("attention", [])
    if not a or not any(s.get("points") for s in a):
        return none(how, "No data yet: GDELT is rate-limiting GitHub's servers, so this series is empty for now.")
    parts = []
    for s in a:
        p = s["points"]
        if len(p) > 14:
            r = statistics.mean(v for _, v in p[-7:]) / max(statistics.mean(v for _, v in p[-37:-7]), 1e-9) - 1
            parts.append(f"{s.get('term', s.get('name', '?'))} {signed_pct(r)} vs the prior month")
    now = ("Last 7 days against the prior 30: " + ", ".join(parts) + ".") if parts else "Too few points to compare."
    return reading(how, now, "Attention tells you about mood, not fundamentals; read it against the share prices.", "mixed")


def shorts_reading(site):
    how = ("FINRA short-sale volume as a share of all volume, 5-day window. Above about 50% means a large share of "
           "trading is short selling (it includes market-maker hedging, so read changes rather than levels).")
    s = site["markets"]["perception"].get("short_share", [])
    if not s:
        return none(how, "No short-volume data yet.")
    parts, rising = [], 0
    for x in s:
        p = x["points"]
        if len(p) < 2:
            continue
        ch = p[-1][1] - p[0][1]
        rising += ch > 0.03
        parts.append(f"{x['symbol']} {pct(p[-1][1])} ({ch * 100:+.0f} pts since {p[0][0]})")
    now = "; ".join(parts) + "."
    if rising:
        return reading(how, now, "Short pressure is building in some names; bets against the trade are growing.", "against")
    return reading(how, now, "Short share is flat or falling across the group: the sell-off is not being driven by "
                   "new short selling, more by holders selling.", "mixed")


def spread_reading(site):
    how = ("ICE BofA US high-yield option-adjusted spread, %: the extra yield lenders demand from riskier companies. "
           "Neoclouds borrow at high-yield-like rates, so a widening spread raises their cost of funding. Under "
           "about 3.5% is calm; above 5% is stress.")
    cs = site["markets"]["perception"].get("credit_spread", [])
    p = cs[0]["points"] if cs else []
    if len(p) < 30:
        return none(how, "Not enough spread history yet.")
    last = p[-1][1]
    month = p[-22][1] if len(p) > 22 else p[0][1]
    lo = min(v for _, v in p)
    hi = max(v for _, v in p)
    now = f"{last:.2f}% on {p[-1][0]} ({last - month:+.2f} pts over a month; 1-year range {lo:.2f}-{hi:.2f}%)."
    if last >= 5:
        return reading(how, now, "Credit markets are stressed: refinancing for neoclouds gets expensive or shuts.", "against")
    if last - month >= 0.4:
        return reading(how, now, "Spreads are widening quickly; funding is getting dearer.", "against")
    return reading(how, now, "Credit markets are calm. The funding risk is specific to neoclouds and Nvidia, not a "
                   "general credit squeeze.", "supports")


def narratives_reading(site):
    how = ("Each narrative is hand-scored 1-5 on evidence and on how much it is moving prices. Top left (thin "
           "evidence, big price impact) is where perception has run ahead of facts; bottom right is evidence the "
           "market is ignoring. The table below lists what would confirm or break each one.")
    n = site["markets"]["perception"].get("narratives", [])
    if not n:
        return none(how, "No narratives logged.")
    ahead = [x["narrative"] for x in n if x["evidence_score"] <= 2 and x["price_impact_score"] >= 4]
    leaning = [x["narrative"] for x in n if x["status"].startswith("leaning break")]
    now = f"{len(n)} narratives tracked. Running ahead of the evidence: {', '.join(ahead) or 'none'}."
    if leaning:
        now += f" Leaning towards breaking: {', '.join(leaning)}."
    return reading(how, now, "The bearish stories moving prices most have the thinnest evidence, which is what a "
                   "perception-driven sell-off looks like.", "supports" if ahead else "mixed")


READERS = {
    "tiles": tiles_reading,
    "scarcity": scarcity_reading,
    "regional": regional_reading,
    "atcap": atcap_reading,
    "shape": shape_reading,
    "prices": prices_reading,
    "capex": capex_reading,
    "funding": funding_reading,
    "deals": deals_reading,
    "capacity": capacity_reading,
    "sites": sites_reading,
    "tsmc": tsmc_reading,
    "revisions": revisions_reading,
    "targets": targets_reading,
    "implied": implied_reading,
    "basket": basket_reading,
    "attention": attention_reading,
    "shorts": shorts_reading,
    "spread": spread_reading,
    "narratives": narratives_reading,
}


def readings(site):
    """One reading per chart. A chart whose reader fails shows its how-to-read text only."""
    out = {}
    for key, fn in READERS.items():
        try:
            out[key] = fn(site)
        except Exception as e:  # a bad row should not break the whole page
            out[key] = {"how": "", "now": f"Reading unavailable ({type(e).__name__}).", "means": "", "tone": "none"}
    return out
