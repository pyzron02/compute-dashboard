# Compute dashboard

Tracks global AI compute demand and pricing: GPU rental prices, cloud list and spot prices,
supplier revenue, hyperscaler capex and power. Free, redistributable sources only.

Plan: https://claude.ai/artifact/TEGfvuSfz1y1vB25FYuVD4

## Collectors

| Collector | Source | Auth | Output |
| --- | --- | --- | --- |
| `collectors/azure.py` | [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | none | `data/tidy/cloud_prices.csv` |
| `collectors/nebius.py` | [Nebius spot price API](https://docs.nebius.com/signup-billing/spot-prices) | none | `data/tidy/cloud_prices.csv`, `data/tidy/nebius_spot_hourly.csv` (hourly, rolling 30-day backfill) |

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

## Running

```
python -m unittest -v          # no dependencies beyond the standard library
python -m collectors.azure     # writes today's snapshot under data/
```

GitHub Actions runs every collector daily at 06:15 UTC and commits the new data
(`.github/workflows/collect.yml`). Trigger a run by hand from the Actions tab.
