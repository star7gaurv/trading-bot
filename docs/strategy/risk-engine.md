# Risk Engine & Position Sizing

Every trade the live strategy opens goes through position sizing and safety checks that are
separate from the entry decision itself — the model decides *whether* to trade; a distinct layer
decides *how much* and whether anything else should stop it first.

## Regime-scaled stake sizing

`custom_stake_amount()` in `CortexaAI_v23.py` starts from FreqTrade's proposed stake and scales it
through `RiskEngine.stake_multiplier(regime)` (`freqtrade/user_data/scripts/risk_engine.py`) — a
regime that currently favors this direction gets full size; a hostile or transitional regime gets
reduced size. Layered on top: the HMM's own confidence score also scales stake directly (formula:
confidence 0.3 → 0.65× stake, confidence 0.9 → 0.95×, confidence 1.0 → full size) — a regime that's
just flipped is inherently less trustworthy than one that's been stable for a while, and stake
size now reflects that instead of treating every regime read as equally certain.

## Correlation cluster cap

Pairs are grouped into clusters (`MEGA_CAP`, `L2`, `MEME`, `AI`, `DEFI`, `L1_ALT`, `INFRA`) —
coins that tend to move together. `confirm_trade_entry()` blocks a new entry once a non-`ALTCOIN`
cluster already has 2 open positions, regardless of how good any individual signal looks. Without
this, a strong signal correlated across several coins in the same cluster (a common failure mode —
one real move driving several "independent"-looking entries) could concentrate risk far beyond
what position-count alone suggests.

## Funding-rate crowding guard

Blocks longs when BTC's perpetual funding rate is strongly positive (longs already crowded — the
trade is paying a premium to be on the popular side) and blocks shorts when funding is strongly
negative, symmetrically. Reads a 15-minute-cached snapshot of the live rate, live/dry-run only —
see [The Directional Module](../modules/directional.md) for why every live-only external read in
this codebase now has to be runmode-gated after a 2026-09-07 investigation found this exact
pattern silently corrupting historical backtests.

## Re-entry cooldown

A `(pair, side)` combination that just stopped out can't re-enter for `FREQAI_REENTRY_COOLDOWN_CANDLES`
(default 8) candles. Added after a real, observed failure mode: a choppy, counter-trend day
repeatedly re-entering and re-stopping the same losing side within hours.

## Per-pair-per-regime gate

Independent of what the model currently predicts, `pair_regime_stats.json` tracks each
`(pair, regime)` combination's own rolling 30-day win rate and profit factor, and blocks entries on
any combination performing badly enough (win rate under 40% and profit factor under 0.7, with at
least 5 trades to judge from) — a pair that's genuinely losing in a specific regime stays blocked
even if the model's signal looks fine, until its own recent record improves.

## Circuit breakers — increasing severity

| Layer | Trigger | Effect |
|---|---|---|
| Daily loss limit | Today's realized P&L crosses `-FREQAI_DAILY_LOSS_LIMIT` | Blocks new entries only |
| Daily flatten | Losses reach 1.5× the daily limit | Force-closes every open position |
| Manual override | A human watching a bad trade taps Close | Force-exits that one trade immediately — see [Manual Trade Control](manual-control.md) |
| Edge gate | Live model prediction quality or walk-forward pass/fail says no measured edge | Blocks all new entries until either recovers — see [The Brain](../brain.md#the-edge-gate) |

Each layer is independent and stacks — a config can be paused by the edge gate *and* separately
hit its daily loss limit on the same day, and either alone is sufficient to block new risk. None of
them touch exit logic; an open position always gets to leave through its own normal path.
