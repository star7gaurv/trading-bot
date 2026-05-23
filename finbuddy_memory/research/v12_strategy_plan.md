# v12 Strategy Plan — Root-Cause Fixes (DRAFT for Review)

**Created:** 2026-05-04 by Claude Code
**Status:** ⛔ SUPERSEDED (2026-05-18) — historical reference only

> Strategy iterated v12 → v13 → v15 → v17 → v19 → v22 since this plan. Asymmetric barriers (the root-cause fix proposed here) shipped in v19; current live is v22. Brain (Phase 13) now owns variant exploration. See [[strategies/graveyard]] for full lifecycle.
**Trigger:** R4 grid (90 combos, bull window 2024-01-01 → 2025-01-01) failing.
Empirical stats across 28 completed combos as of 25/90 rows:

| Metric | Value | Target | Verdict |
|---|---|---|---|
| Avg Win Rate | 47.0% | >50% | ❌ |
| Avg Trades / yr | 2,249 | <500 | ❌ over-trading |
| Avg Profit Factor | 0.68 | >1.2 | ❌ |
| Max Profit Factor | 0.76 | >1.2 | ❌ |
| Best Sharpe so far | -7.06 | >0.5 | ❌ |

**No combo will PASS.** R4 verdict: DO NOT PROMOTE. v12 needs root-cause fixes, not parameter tuning.

---

## Four Confirmed Bugs (100% verified, line-cited)

### Bug #1 — Label-Stop Geometry Mismatch
- **File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py`
- **Evidence:**
  - L313: `k_sl = 1.0` in `set_freqai_targets()` (label assumes -1×ATR stop)
  - L143: `-2.0 * atr_pct` in `custom_stoploss()` (trade actually uses -2×ATR stop)
- **Impact:** Model trains on a stop that never fires. Every "S" label in training represents a path the live trade would have survived. Training signal does not match execution reality.
- **Fix:** Set `k_sl = 2.0` in `set_freqai_targets()` to match the actual initial stop.

### Bug #2 — Hold Class Dropped (Model Cannot Abstain)
- **File:** `FinBuddyFreqAI.py`
- **Evidence:**
  - L357-360: `np.where(labels == 1.0, "L", np.where(labels == -1.0, "S", None))` — class-0 (time-barrier flat) becomes `None`, FreqAI drops these rows from training.
- **Impact:** Model only learns L vs S. On every candle it must pick a direction. There is no "skip this setup" output. Result: 2,000–4,000 trades/year is structurally inevitable, not a tuning problem.
- **Fix:** Encode class-0 as `"H"` (hold) and keep it in training. Entry rules require `proba_L > threshold` AND `proba_H < 0.4`.

### Bug #3 — FreqAI Sees Only 15m Data
- **File:** `freqtrade/user_data/config.json`
- **Evidence:**
  - `freqai.feature_parameters.include_timeframes: ["15m"]` — confirmed read from live config.
  - `informative_pairs()` in strategy returns 1h, 4h, 1d but those flow only into TA gates (`ema_50_1h`, `btc_4h_below_ema50`), never into FreqAI's training features.
- **Impact:** LightGBM is blind to higher-timeframe context. It can see RSI(15m) but not the 4h trend its trade lives inside.
- **Fix:** `include_timeframes: ["15m", "1h", "4h"]`. FreqAI will auto-build features at all three resolutions.

### Bug #4 — Trailing Stop Caps Winners, Losers Run Full Distance
- **File:** `FinBuddyFreqAI.py`
- **Evidence:**
  - L143: initial stop = -2.0 × ATR (loser exit)
  - L131-139: trailing arms at `current_profit > atr_pct` and locks at +1.5 × ATR (winner exit)
- **Impact:** Realized R:R ≈ 0.75:1, not 2:1. Even at WR=50.7% (run 25), Sharpe is -7.06 because winners are cut at +1.5×ATR but losers ride to -2×ATR. Math: `0.507 × 1.5 - 0.493 × 2.0 = -0.226 ATR/trade`, structurally negative.
- **Fix:** One of two changes:
  - Option A: Trail at +2.5 × ATR (loose enough to let winners run further than losers fall).
  - Option B: Initial stop -1.5 × ATR + trail at +2.0 × ATR. Tighter loser cut, looser winner.
  - **Recommend Option B** — also re-aligns with Bug #1 fix if `k_sl` is set to 1.5 instead of 2.0.

---

## Implementation Order (v12)

1. **Bug #1 + #4 together** (label/stop alignment). Set `k_sl = 1.5` in label, initial stop `-1.5 × ATR`, trail `+2.0 × ATR`. One coherent geometry.
2. **Bug #2** (hold class). Single-file change in `set_freqai_targets()` + entry rule update.
3. **Bug #3** (multi-TF features). Single-line config change.
4. Re-run R5 grid on bull window with fixed v12. Sweep `k_tp` (1.5, 2.0, 2.5) and `train_period_days` (30, 60). Drop the threshold sweep — with hold class working, `proba_threshold > 0.50` is sufficient.

## Out of Scope for v12 (deferred)

- Switching primary timeframe to 1h (architectural — 15m + multi-TF features may already fix the S/N issue without a rewrite).
- Meta-labeling (López de Prado AFML ch.4) — only if v12 still fails after the four fixes.
- Larger pair set, funding-rate features, order-book features.

## Acceptance Criteria for v12 → Promotion

Same as v11: bull-window walk-forward must pass:
- Sharpe > 0.5
- Win Rate > 50%
- Max Drawdown < 20%
- Profit Factor > 1.2
- Trade count < 500/year (new — over-trading is itself a failure mode)

---

*End of v12 plan. No code written yet — awaiting Gaurav review on this file before any strategy edits.*

---
*← [[FINBUDDY_PROJECT_MEMORY]]*
