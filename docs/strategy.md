# The Live Strategy

`CortexaAI_v23.py` (`freqtrade/user_data/strategies/`) is the directional long/short strategy
running live in dry-run mode. This page explains how it actually decides to enter and exit a
trade. For the exact current function-by-function source, see its
[reference page](reference/strategies/CortexaAI_v23.md).

## The core idea: regression, not classification

FreqAI's `LightGBMRegressor` predicts a single continuous number per candle: a z-scored version of
"what will this pair's return be over the next `label_period_candles` candles?" — not a
buy/sell/hold class. This was a deliberate architectural choice (see `CLAUDE.md`'s "v23 Conscious
Brain" session): an earlier classifier version produced a majority class under any asymmetric
take-profit/stop-loss ratio, biasing the model toward always predicting one direction. Regression
has no classes, so there's no imbalance to correct for.

## Entry: four gates, all must agree

A long only fires when **all** of these are true for `STABILITY_N` consecutive candles:

1. **The prediction clears a dynamic threshold.** The raw prediction is centered against a
   trailing rolling median (to remove training-serving drift without erasing the model's genuine
   directional lean), then compared against a threshold that itself adapts per candle — tighter in
   a regime that disfavors that direction, looser when the recent win rate has been good, and
   (as of 2026-07-08) never *easier* than the nominal `.env` value, only ever tighter.
2. **The regime allows it.** A hard gate blocks longs entirely in CRASH/BEAR and shorts entirely in
   BULL/EUPHORIA. NEUTRAL allows both.
3. **Technicals agree.** Price above its 50-EMA, RSI below 68, not already at the top of its
   Bollinger range, with expanding volatility.
4. **The pair isn't currently blocked.** A per-pair-per-regime gate independently tracks each
   (pair, regime) combination's rolling 30-day win rate and profit factor, and blocks entries on
   any combination that's been losing badly enough, regardless of what the model currently says.

## Exit: the genuine edge lives here

The single most important finding from this project's own diagnostic history (see `CLAUDE.md`'s
"Turnaround" session, 2026-06-17): **the exit signal is where the real edge is** — historically
88–96% win rate on signal-driven exits — while entries have repeatedly measured close to a coin
flip. `custom_exit()` closes a trade when the model's prediction flips against the position, when
price hits its ATR-based stop or trail-lock, or when the trade has run for `label_period_candles`
candles without resolving (the model was never trained to have an opinion past its own prediction
horizon).

## Position sizing and leverage

Leverage is confidence-scaled: the further the centered prediction clears its threshold, the
higher the tier (1x/2x/3x), capped by the exchange's own per-pair maximum. Stake size responds to
regime and to the HMM's own confidence score — a regime that's just transitioned gets a smaller
stake than one that's been stable.

## Circuit breakers

Three independent, stacked safety mechanisms, each addressing a different historical failure mode
this project actually hit:

- **Daily loss limit** — blocks new entries once today's realized P&L crosses a threshold.
- **Daily flatten** — force-closes every open position if losses reach 1.5× that limit, because the
  entry-block alone still let losses compound through positions opened just before the limit hit.
- **Edge gate** (`edge_monitor.py`, 2026-09-07) — the newest and most structural: pauses *all* new
  entries whenever the live model's own measured 30-day prediction quality or the walk-forward
  pass/fail history says the current configuration has no edge, independent of any single day's
  P&L. See [Strategy & Brain](brain.md#the-edge-gate) for why this exists.

None of these touch exit logic — an open position always gets to exit through its normal path.
