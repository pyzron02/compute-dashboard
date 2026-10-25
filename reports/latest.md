# Compute price report

Generated 2026-10-25 11:32 UTC from `data/`. Prices are USD per GPU-hour, Linux, medians across regions unless stated.

## 1. Price levels by provider and tier

Azure snapshot 2026-10-25; Nebius spot snapshot 2026-10-25; Nebius on-demand from its pricing page.

| GPU | Azure on-demand | Azure 3-yr reserved | Azure spot | Nebius on-demand | Nebius spot | Azure ÷ Nebius on-demand |
| --- | --- | --- | --- | --- | --- | --- |
| GB200 | $33.53 | $14.75 | $33.53 |  |  |  |
| B300 |  |  |  | $9.50 | $2.50 |  |
| B200 |  |  |  | $8.50 | $3.20 |  |
| H200 | $13.25 | $6.60 | $13.25 | $5.40 | $1.50 | 2.5x |
| H100 | $11.06 | $5.49 | $2.45 | $4.50 | $0.79 | 2.5x |
| MI300X | $7.50 | $3.29 | $1.39 |  |  |  |
| A100 | $4.92 | $1.80 | $0.97 |  |  |  |
| RTX PRO 6000 |  |  |  |  | $0.79 |  |

## 2. Spot discount

A spot price close to the on-demand price means the provider has little idle capacity of that GPU.

| Provider | GPU | Spot as % of on-demand |
| --- | --- | --- |
| Azure | GB200 | 100% |
| Azure | H200 | 100% |
| Azure | H100 | 22% |
| Azure | MI300X | 18% |
| Azure | A100 | 20% |
| Nebius | B300 | 26% |
| Nebius | B200 | 38% |
| Nebius | H200 | 28% |
| Nebius | H100 | 18% |

## 3. Nebius spot prices over time

Hourly average spot price, median across regions.

| GPU | Latest median spot | 7-day change | 30-day change | 30-day low | 30-day high | Regions now (low to high) |
| --- | --- | --- | --- | --- | --- | --- |
| B300 | $2.65 | -46% | -38% | $0.99 | $9.49 | 3 ($0.99 to $3.34) |
| B200 | $3.05 | +77% | -23% | $0.99 | $6.62 | 2 ($1.95 to $4.15) |
| H200 | $1.40 | -15% | -43% | $0.79 | $4.50 | 3 ($1.33 to $5.39) |
| H100 | $0.79 | +0% | -63% | $0.79 | $2.15 | 1 ($0.79 to $0.79) |
| RTX PRO 6000 | $0.82 | -8% | -14% | $0.79 | $1.38 | 3 ($0.79 to $0.84) |

Prices held one fixed rate until 2026-10-08, when market-based spot pricing appears to start. Changes measured across that date mix the old fixed rate with market prices.

## 4. Azure over time

2 daily snapshot(s) so far. Day-over-day and weekly changes appear once a week of history exists.

## Sources

| Series | Origin | Collector | Cadence | Stored in |
| --- | --- | --- | --- | --- |
| Azure GPU VM list prices (on-demand, spot, low priority, 1/3/5-year reserved) | [Azure Retail Prices API, prices.azure.com/api/retail/prices (public, no key)](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | `collectors/azure.py` | Daily snapshot at 06:15 UTC | `data/tidy/cloud_prices.csv (source=azure)` |
| Nebius spot GPU prices, current and hourly history | [Nebius billing API, api.nebius.cloud/billing/v1alpha1/spot-price (public, no key)](https://docs.nebius.com/signup-billing/spot-prices) | `collectors/nebius.py` | Daily snapshot plus hourly averages backfilled 30 days | `data/tidy/cloud_prices.csv (source=nebius), data/tidy/nebius_spot_hourly.csv` |
| Nebius on-demand list prices | [Nebius pricing page, entered by hand](https://nebius.com/prices) | `data/manual/list_prices.csv` | Manual, when the page changes | `data/manual/list_prices.csv` |
