# Directional (Live) — Futures Long/Short

The flagship module: perpetual futures on Binance USDT-M, isolated margin, both long and short.
Currently running in dry-run mode (simulated fills against real live prices — no real capital at
risk yet). This page covers the module as a whole; see the linked pages for depth on each piece.

## Why futures, not spot

Spot trading is structurally long-only. The project's early backtests (192 combinations) proved
this is an architectural ceiling, not a tuning problem: no long-only strategy clears a Sharpe of
0.5 in a market that falls 47.55% over the test window, no matter how good the entry signal is —
and the signal itself measured healthy (79-81% win rate on signal-driven exits) even in that
losing test. Futures gives both directions, making the strategy market-agnostic by construction.
Full evolution: [Backtest & Architecture History](../strategy/backtest-history.md).

## The moving parts

| Piece | What it does | Detail |
|---|---|---|
| Entry/exit logic | Regression prediction vs. dynamic thresholds, regime gate, technical filters, per-pair-per-regime gate | [Strategy & Brain](../strategy.md) |
| Feature engineering | 545 features per pair — technical, cross-sectional, momentum, funding, macro | [Feature Engineering](../data/features.md) |
| Regime classification | 5-state (CRASH/BEAR/NEUTRAL/BULL/EUPHORIA), price-action rule | [Regime Detection](../data/regime-detection.md) |
| Position sizing & risk | Regime-scaled stake, cluster caps, funding-crowding guard, circuit breakers | [Risk Engine](../strategy/risk-engine.md) |
| Human override | Force-exit and pause/resume from the dashboard or Telegram | [Manual Trade Control](../strategy/manual-control.md) |
| Autonomous safety | Pauses new entries when the system's own measured edge is non-positive | [The Brain § edge gate](../brain.md#the-edge-gate) |
| Continuous improvement | Hypothesis generation → backtest → promotion, all automated | [The Brain](../brain.md) |

## Leverage and margin

Isolated margin — a losing position's downside is capped at its own margin, never spilling into
the rest of the account. Leverage is confidence-scaled rather than fixed: the strategy's
`leverage()` callback compares how far the centered prediction clears its entry threshold against
three tiers (1x / 2x / 3x), so a marginal signal gets minimal leverage and a strong one gets more —
always capped by whatever the exchange allows for that pair. See
[Risk Engine](../strategy/risk-engine.md) for how stake size is layered on top of this
independently.

## Whitelist

25 pairs currently (trimmed from an original 37, and from 26 after Binance delisted TON's
perpetual contract in June 2026). Pair selection has been narrowed twice based on measured
per-pair performance, not held fixed since launch.

## What's actually been measured

A same-market, same-code, apples-to-apples comparison (2026-09-07, re-run after fixing a bug that
had been silently suppressing long entries in every backtest — see below) tested four candidates on
the real last-90-days market:

| Candidate | Trades | Win rate | Profit factor |
|---|---|---|---|
| Live `.env` config | 180 | 50.6% | 0.64 |
| Brain's own default seed | 273 | 40.3% | 0.57 |
| Analyst's best-bull tuning | 106 | 50.9% | 0.64 |
| Analyst's best-bear tuning | 105 | 49.5% | 0.63 |

None clears the promotion bar (profit factor 1.2, win rate 50%, Sharpe 0.5 — see
[The Brain](../brain.md) for the full gate). This isn't a measurement artifact — the numbers held
after a real bug was found and fixed: `confirm_trade_entry()`'s macro/funding gates were reading
*today's* live market snapshot even during historical backtests, silently vetoing longs based on
data that had nothing to do with the simulated date. Fixing that bug changed *which* trades a
backtest produces (longs went from entirely absent to genuinely represented), not the conclusion.

## Currently paused by the edge gate

!!! danger "New entries paused"
    `edge_monitor.py` pauses new entries whenever the live model's own measured 30-day prediction
    quality or the walk-forward pass/fail history says the current configuration has no measured
    edge. As of the last check the walk-forward fail streak stood at 200+ consecutive runs. Open
    positions still exit normally through their own logic — only new risk is blocked. See
    [The Brain § edge gate](../brain.md#the-edge-gate) for the full reasoning and history, and the
    live `finbuddy_memory/analytics/edge_state.json` for the current reading.

## Known, deliberately unresolved gaps

- A possible timeframe mismatch in the relative-strength features — see
  [Feature Engineering](../data/features.md#cross-sectional--relative-strength) — flagged, not
  fixed, because correcting it changes what an already-trained feature means and needs its own
  retrain and A/B test rather than a hot patch.
- An unexplained pattern from the same 2026-09-07 investigation: every tested config produced zero
  long entries in a 90-day window that included a genuine bull regime, across roughly 240 combined
  trades. Not yet root-caused — could be a real signal that shorts are currently favored, or a
  suppression bug similar to two prior ones this project has found and fixed. Worth investigating
  next if this module is picked back up.

## Reference

[`CortexaAI_v23.py` full source reference](../reference/strategies/CortexaAI_v23.md) — every
method, auto-generated from the strategy file's own docstrings.
