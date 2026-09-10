# Pairs Trading (Paper — reversion gate active)

Market-neutral statistical arbitrage: find two historically correlated coins whose price spread
has stretched unusually far apart, go long the cheap one and short the expensive one, and profit
when the spread reverts to its normal relationship. Paper-only.

!!! danger "New positions currently paused"
    As of 2026-09-10, `_reversion_gate()` in `scanner.py` is blocking new entries. Existing
    positions (currently zero) still manage and close normally. See below for why, and
    `finbuddy_memory/pairs_trading/gate_state.json` for the live reading.

## The mechanism

`scripts/pairs_trading/scanner.py` runs hourly over every pair combination in the whitelist,
computing a correlation, an OLS hedge ratio, a current spread z-score, and a mean-reversion
half-life for each. It opens a position when the spread is stretched (|z| ≥ 2.0), the pair is
genuinely correlated (correlation ≥ 0.85), and the historical half-life suggests it would actually
revert within a tradeable window (2 hours to 3 days). It closes on reversion (a win), on further
divergence past 4σ (a stop), or after 14 days regardless.

## Why it's currently gated off

Two separate findings, from a 2026-09-10 investigation:

**The market's statistical foundation has broken down right now.** Tested live against the current
25-pair whitelist: 41 of 300 pair combinations show a genuine stretch (clear the z-score bar), but
only 1 clears the correlation bar, and none clear both. The market's been trending since late
August — correlations this strategy depends on genuinely aren't holding, and the scanner is
correctly declining to trade on a broken premise.

**But the module was losing money even when it *was* trading.** Of 215 historical closed
positions, only 5 (2.3%) ever actually mean-reverted the way the strategy assumes — the other 206
(96%) hit the 4σ divergence stop instead, and 4 more lost heavily riding out the full 14-day time
stop. Lifetime: 23.3% win rate, profit factor 0.55, -53.67 USDT net. A 2026-07-08 tightening of
the half-life filter (from 480 hours down to 72) did not fix this — losses continued afterward
too.

This has the same shape as the directional strategy's own historical diagnosis: a mechanism whose
core hypothesis rarely plays out, with the stop-loss doing essentially all the work. The
`_reversion_gate()` added 2026-09-10 mirrors `edge_monitor.py`'s philosophy exactly — it blocks new
risk whenever the module's own measured record says its premise isn't holding (reversion rate
below 15%, or profit factor below 1.0, once at least 30 trades exist to judge from) — so a future
market where correlations recover doesn't just quietly resume the same losing pattern.

## What this doesn't decide

The gate pauses new risk. It does not decide whether this module gets a genuinely different
cointegration test (something that predicts *whether* reversion will happen, not just that a
spread is currently stretched) or gets retired outright — that call is still open.

## Reference

[`scripts/pairs_trading` reference](../reference/scripts/pairs_trading/scanner.md) · cron: hourly at `:20`
