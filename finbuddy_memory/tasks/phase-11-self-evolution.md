# Phase 11: Self-Evolution (In-Strategy Memory Integration)

**Status**: ✅ COMPLETE (verified 2026-05-18)
**Last verified**: 2026-05-18

> **Scope note**: Phase 11 is the *in-strategy* dynamic adjustments (RS gates, regime sizing, memory reads). The *autonomous hypothesis engine* — generating and testing new strategy variants — is **Phase 13** (`phase-13-conscious-brain.md`). Don't confuse the two.

**Goal**: Strategy reads live memory (regime, macro context, recent WR) and adjusts behavior per-candle/per-trade instead of hardcoded parameters.

## Sub-Tasks

- `[x]` **1. Relative Strength (RS) Metrics**
  - `[x]` Fetch 1H BTC data in `FinBuddyFreqAI.py`.
  - `[x]` Compute `rs_raw = close / btc_close`.
  - `[x]` Create dynamic threshold gates (`is_strong_vs_btc`) to filter poor signals.

- `[x]` **2. Memory Integration**
  - `[x]` Ensure `_get_current_regime` correctly reads from `finbuddy_memory/regimes/current.json`.
  - `[x]` Ensure `_get_combined_context` reads from external fetched data.

- `[x]` **3. Dynamic Regime Thresholds**
  - `[x]` Replace hardcoded regime blocks with intelligent multiplier-based stake sizing.
  - `[x]` Adjust `custom_stake_amount` based on live HMM regime multipliers.

---
*This file tracks the exact execution steps for Phase 11.*
