# Compute dashboard

Tracks global AI compute demand and pricing: GPU rental prices, cloud list and spot prices,
supplier revenue, hyperscaler capex and power. Free, redistributable sources only.

Plan: https://claude.ai/artifact/TEGfvuSfz1y1vB25FYuVD4

## Collectors

| Collector | Source | Auth | Output |
| --- | --- | --- | --- |
| `collectors/azure.py` | [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | none | `data/tidy/cloud_prices.csv` |
| `collectors/nebius.py` | [Nebius spot price API](https://docs.nebius.com/signup-billing/spot-prices) | none | `data/tidy/cloud_prices.csv`, `data/tidy/nebius_spot_hourly.csv` (hourly, rolling 30-day backfill), `data/tidy/nebius_spot_15min.csv` (15-minute, last 7 days, appended so it grows) |

Coming next: AWS on-demand and spot, Google Cloud, Vast.ai, OpenRouter, SEC EDGAR, TSMC.
Keys for the keyed sources: see [docs/API_KEYS.md](docs/API_KEYS.md).

Each collector keeps the untouched API response in `data/raw/<source>/<date>.json.gz`, so a parser
fix can be replayed over history, and writes normalised rows to `data/tidy/`.

### `cloud_prices.csv`

| Column | Meaning |
| --- | --- |
| `date` | Snapshot date (UTC) |
| `source` | `azure`, `nebius`, later `aws`, `gcp` |
| `region` | Cloud region |
| `sku` | Instance or VM size |
| `gpu_model` | H100, H200, A100, MI300X, B200, GB200, GB300 |
| `gpus` | GPUs per instance |
| `tier` | `on_demand`, `spot`, `low_priority`, `reserved_1y`, `reserved_3y`, `reserved_5y` |
| `usd_per_vm_hour` | Linux list price; reservations spread evenly over the term |
| `usd_per_gpu_hour` | `usd_per_vm_hour / gpus` |

## Dashboard

`site/index.html` is a static page that draws everything from `site/data.json`, which
`analysis/build_site.py` rebuilds after each daily run. The workflow then publishes `site/` to
GitHub Pages: https://pyzron02.github.io/compute-dashboard/ (enable once under
Settings → Pages → Source: GitHub Actions). Chart.js 4.4.1 is vendored in `site/vendor/` (MIT).

Hand-maintained inputs, each row with its source URL:
`data/manual/list_prices.csv` (Nebius on-demand), `data/manual/gpu_specs.csv` (dense BF16
throughput from Epoch AI), `data/manual/events.csv` (chart annotations).

The page also shows how often each GPU's spot price sits at its on-demand cap (within 3%),
and the hour-of-day and weekday shape of spot prices with the daily and weekly trend divided out.

## Weekly digest

`analysis/digest.py` writes `reports/weekly/<date>.md`: the week's biggest moves, Azure list
changes, patterns, logged events (as context, not causes), data health and sources. The workflow
runs it on Mondays at 06:45 UTC and posts it as a GitHub issue labelled `digest`
(run by hand with the `digest` box ticked in Actions).

Preview locally: `python -m analysis.build_site && python -m http.server -d site`.

## Running

```
python -m unittest -v          # no dependencies beyond the standard library
python -m collectors.azure     # writes today's snapshot under data/
```

GitHub Actions runs every collector daily at 06:15 UTC and commits the new data
(`.github/workflows/collect.yml`). Trigger a run by hand from the Actions tab.
