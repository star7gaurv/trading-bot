# External Data Feeds

Five external market/sentiment sources feed the model, refreshed every 15 minutes by
`fetch_all_external.py` and its per-source fetchers under `freqtrade/user_data/scripts/`:

| Source | What it provides | Used as |
|---|---|---|
| [Alternative.me](https://alternative.me/crypto/fear-and-greed-index/) | Fear & Greed Index | `%-fear_greed` feature, and a live entry gate (blocks longs under extreme fear, shorts under extreme greed) |
| CoinGecko | Market cap, dominance | Context for `combined_context.json` |
| CryptoPanic | News sentiment | `%-news_sentiment` feature |
| DefiLlama | DeFi TVL | Context data |
| Google Trends | Search interest in "bitcoin," "buy bitcoin," "bitcoin crash" | Context data |

Each writes to `freqtrade/user_data/data/external/` as the live, current snapshot, and is merged
into `combined_context.json` (also refreshed every 15 minutes) — the single file several parts of
the live strategy read for "what's the market mood right now."

## Live snapshot vs. historical series — a distinction that matters

A live-only snapshot is invisible to any backtest by construction — there's no history to look up.
Every feature that actually matters to the live model has a matching historical-parquet builder
(`build_historical_macro.py` for Fear & Greed and BTC/ETH relative strength, `build_historical_funding.py`
for perpetual funding rates, `build_historical_oi*.py` for open interest) so backtests see the same
kind of context the live model was trained and serves on, not a constant placeholder value.

This distinction is also exactly what caused a real, fixed bug: `confirm_trade_entry()`'s macro
safety gate and funding-crowding guard both read the *live* snapshot unconditionally, even during
historical backtests — meaning a backtest's result depended on whatever the market happened to be
doing at the moment the backtest was *launched*, not the date being simulated. See
[Directional](../modules/directional.md#whats-actually-been-measured) for the full finding and
fix. The pattern to watch for in any new external-data integration: does this get a historical
series, or only a live snapshot — and if only a snapshot, is every place that reads it correctly
gated to live/dry-run runmode only?
