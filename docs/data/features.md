# Feature Engineering

The live model currently trains on **545 features** per pair (confirmed from a live training log,
2026-09-10). What follows is what actually goes into that count and where each category comes
from — the strategy's `feature_engineering_expand_all`, `feature_engineering_expand_basic`, and
`feature_engineering_standard` methods in `CortexaAI_v23.py` are the ground truth; this page is the
map to it.

## Technical (per pair, expanded across FreqAI's own indicator/timeframe/shift grid)

Standard price-action indicators (RSI, EMA, Bollinger Bands, ATR) computed across multiple lookback
periods and multiple informative timeframes (`4h`, `1d` in addition to the base timeframe) — FreqAI
automatically multiplies each base indicator across every configured period and shift, which is
most of where 545 comes from.

## Cross-sectional / relative strength

`%-rel_strength_btc_14/28/56` — how strongly a pair is moving relative to BTC over three lookback
windows, computed on 15-minute BTC data. Positive means outperforming BTC (a structural strength
signal for longs); negative means underperforming (a weakness signal for shorts). Confirmed via a
weekly feature-importance report to rank consistently among the model's most-used features.

!!! warning "Known, unfixed issue"
    This feature may carry a timeframe mismatch introduced by the 2026-06-21 switch from 15-minute
    to 1-hour base candles — the lookback window (`14`/`28`/`56`) is applied as a raw candle count
    on the pair's own dataframe, but the BTC comparison series is always loaded at 15 minutes
    regardless of the pair's active timeframe. Flagged 2026-09-07, not yet fixed — correcting it
    changes what an already-trained feature means and needs its own retrain and A/B test.

## Multi-day BTC momentum (added 2026-09-10)

`%-btc_mom_3d/7d/14d` — continuous, real-time-scaled market momentum at three horizons, computed
on a fixed 15-minute-candle window regardless of the pair's active timeframe (correctly avoiding
the mismatch above). Added specifically because the only prior market-wide trend signal was a
single discrete regime bucket updating on a 2-4-week-lagging rule — see
[Regime Detection](regime-detection.md) for the full reasoning.

## Funding rate (3 features)

`%-funding_rate`, `%-funding_rate_z30d`, `%-funding_rate_chg` — from BTC perpetual funding data,
refreshed daily. Added 2026-05-19 as, per this project's own research at the time, the
second-strongest published signal for short-horizon perp moves after order flow itself.

## Macro / sentiment

`%-fear_greed`, `%-btc_strength` (BTC 7-day return minus ETH 7-day return), `%-news_sentiment`,
`%-regime_numeric` (the discrete regime encoded -2 to +2) — see
[External Data Feeds](external-feeds.md) for where each comes from.

## What was tried and dropped

`%-recent_wr` (the model's own recent win rate, fed back as a feature) was removed 2026-05-20 after
a training-serving skew was found: the live value read ~0.34 while every backtest and walk-forward
process defaulted it to a constant 0.50, since those processes never see the live `.env`. A feature
with mismatched training and serving distributions is worse than no feature at all — dropped
cleanly rather than patched.

## What's been tested and found to carry no signal

A 2026-08-31 investigation (three planned tracks: a trend-volatility entry mode, several unused
external data fields already being fetched but not yet wired in, and order-flow/CVD features)
came back NO-GO on all three against a pre-agreed kill condition. Earlier rounds found the same for
open-interest deltas, raw kline-derived order flow, and cross-sectional momentum (the last showed a
*negative* information coefficient — a shared-beta artifact, not real signal). The consistent
finding across all of this project's feature research: **the model's genuine edge is in its exit
timing, not in any entry-side feature tried so far** — see
[Strategy & Brain](../strategy.md#exit-the-genuine-edge-lives-here).
