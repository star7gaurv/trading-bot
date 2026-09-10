# Directional (Live)

The flagship module — long/short perpetual futures on Binance, driven by the FreqAI regression
model described in [Strategy & Brain](../strategy.md). Currently live in dry-run mode.

!!! danger "Currently paused by the edge gate"
    As of the last verified check, `edge_monitor.py` had new entries paused. This is not a bug —
    walk-forward has failed its pass bar (profit factor above 1.2, win rate above 50%, Sharpe above
    0.5) for 200+ consecutive runs, and the live model's own measured prediction quality has been
    at or near zero since the 2026-08-25 regime flip. Open positions still exit normally; only new
    risk is blocked. See [The Brain](../brain.md#the-edge-gate) for why this exists, and the live
    `finbuddy_memory/analytics/edge_state.json` for the current reading.

## What's actually been measured

A same-market, same-code, apples-to-apples comparison (2026-09-07 investigation, re-run after
fixing a bug that had been silently suppressing long entries in every backtest — see below) tested
four candidates on the real last-90-days market:

| Candidate | Trades | Win rate | Profit factor |
|---|---|---|---|
| Live `.env` config | 180 | 50.6% | 0.64 |
| Brain's own default seed | 273 | 40.3% | 0.57 |
| Analyst's best-bull tuning | 106 | 50.9% | 0.64 |
| Analyst's best-bear tuning | 105 | 49.5% | 0.63 |

None clears the promotion bar. This isn't a measurement artifact — the numbers held after a real
bug was found and fixed (`confirm_trade_entry`'s macro/funding gates were reading *today's* live
market snapshot even during historical backtests, silently vetoing longs based on data that had
nothing to do with the simulated date). Fixing that bug changed *which* trades a backtest
produces, not the conclusion.

## Known, deliberately unresolved gaps

- A possible timeframe mismatch in `%-rel_strength_btc_14/28/56` between the pair's own candle
  interval and the always-15-minute BTC reference series, introduced by the 2026-06-21 1h
  timeframe switch. Flagged, not yet fixed — correcting it changes what an already-trained feature
  means and needs its own retrain and A/B test, not a hot patch.
- An observation from the same investigation: every tested config produced zero long entries in a
  90-day window that included a genuine bull regime, across ~240 combined trades. Not yet
  root-caused — could be a real signal that shorts are currently favored, or a suppression bug
  similar to two prior ones this project has found. Next thing to look at if picking this module
  back up.

## Related

- [Strategy](../strategy.md) — full entry/exit/risk logic
- [The Brain](../brain.md) — how new configurations get tested and promoted
- [`CortexaAI_v23.py` reference](../reference/strategies/CortexaAI_v23.md)
