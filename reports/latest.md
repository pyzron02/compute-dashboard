# Compute price report

Generated 2026-11-10 14:54 UTC from `data/`. Prices are USD per GPU-hour, Linux, medians across regions unless stated.

## 1. Price levels by provider and tier

Azure snapshot 2026-11-10; Nebius spot snapshot 2026-11-10; Nebius on-demand from its pricing page.

| GPU | Azure on-demand | Azure 3-yr reserved | Azure spot | Nebius on-demand | Nebius spot | Azure ÷ Nebius on-demand |
| --- | --- | --- | --- | --- | --- | --- |
| GB200 | $33.53 | $14.75 | $33.53 |  |  |  |
| B300 |  |  |  | $9.50 | $7.80 |  |
| B200 |  |  |  | $8.50 | $2.35 |  |
| H200 | $13.25 | $6.60 | $13.25 | $5.40 | $0.79 | 2.5x |
| H100 | $11.06 | $5.49 | $2.45 | $4.50 | $1.50 | 2.5x |
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
| Nebius | B300 | 82% |
| Nebius | B200 | 28% |
| Nebius | H200 | 15% |
| Nebius | H100 | 33% |

## 3. Nebius spot prices over time

Hourly average spot price, median across regions.

| GPU | Latest median spot | 7-day change | 30-day change | 30-day low | 30-day high | Regions now (low to high) |
| --- | --- | --- | --- | --- | --- | --- |
| B300 | $8.10 | -15% | +82% | $0.99 | $9.49 | 3 ($5.35 to $12.05) |
| B200 | $2.42 | -55% | +23% | $0.99 | $8.65 | 2 ($2.00 to $2.85) |
| H200 | $0.84 | -66% | -37% | $0.79 | $5.39 | 3 ($0.84 to $1.85) |
| H100 | $1.28 | +28% | +62% | $0.79 | $2.15 | 1 ($1.28 to $1.28) |
| RTX PRO 6000 | $0.80 | -33% | -15% | $0.79 | $1.65 | 3 ($0.79 to $0.84) |

Prices held one fixed rate until 2026-10-08, when market-based spot pricing appears to start. Changes measured across that date mix the old fixed rate with market prices.

## 4. Azure over time

15 daily snapshot(s) so far. Day-over-day and weekly changes appear once a week of history exists.

## Sources

| Series | Origin | Collector | Cadence | Stored in |
| --- | --- | --- | --- | --- |
| Azure GPU VM list prices (on-demand, spot, low priority, 1/3/5-year reserved) | [Azure Retail Prices API, prices.azure.com/api/retail/prices (public, no key)](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | `collectors/azure.py` | Daily snapshot at 06:15 UTC | `data/tidy/cloud_prices.csv (source=azure)` |
| Nebius spot GPU prices, current and hourly history | [Nebius billing API, api.nebius.cloud/billing/v1alpha1/spot-price (public, no key)](https://docs.nebius.com/signup-billing/spot-prices) | `collectors/nebius.py` | Daily snapshot plus hourly averages backfilled 30 days | `data/tidy/cloud_prices.csv (source=nebius), data/tidy/nebius_spot_hourly.csv` |
| Nebius on-demand list prices | [Nebius pricing page, entered by hand](https://nebius.com/prices) | `data/manual/list_prices.csv` | Manual, when the page changes | `data/manual/list_prices.csv` |
