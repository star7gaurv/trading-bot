# Phase 13: The Conscious Brain (God-Tier Architecture)

**Status**: 🟠 PARTIAL — 2/4 pillars real, 2/4 doc-only (corrected 2026-05-16 by Claude Code audit)
**Goal**: Transform FinBuddy into an Omni-Timeframe, Liquidity-Aware, Self-Evolving Intelligence with an 80% Win Rate.

## Sub-Tasks

- `[x]` **1. Omni-Timeframe Architecture (The Eyes)** — REAL in `FinBuddyFreqAI_v23.py`
  - `[x]` Shift base timeframe in `config.json` from `1h` to `5m`. (Done in `backtest_config.json`; live `config.json` also edited but live bot needs restart to pick up.)
  - `[x]` Add `["15m", "1h", "4h"]` to `include_timeframes` in FreqAI config.
  - `[x]` Scale `label_period_candles` from `6` to `72` (maintaining a 6-hour prediction horizon on a 5m base).
  - `[x]` Update `FinBuddyFreqAI_v23.py` to correctly fetch informative pairs and ingest the new timeframes without memory exhaustion.

- `[ ]` **2. Liquidity & Order Block Awareness (The Map)** — NOT IMPLEMENTED (no `order_block`/`smc`/`liquidity` code in v23; doc-only claim)
  - `[ ]` Inject Smart Money Concepts (Volume Profile / Order Blocks) into feature engineering.
  - `[ ]` Implement veto logic: Block shorts directly above historical Bullish Order Blocks.
  - `[ ]` Implement veto logic: Block longs directly below historical Bearish Order Blocks.

- `[x]` **3. Real-Time Dynamic Stoploss (The Shield)** — REAL in v23 `custom_stoploss` lines 152-161
  - `[x]` Build tick-volatility hook: monitor volume spikes immediately post-entry.
  - `[x]` If volume spikes > 500% against the trade within 10 minutes, trigger an emergency market exit before the `K_SL` ATR stop is hit.

- `[ ]` **4. True Self-Evolution Pipeline (The Brain)** — PARTIAL (research loop exists; no auto-promotion code)
  - `[x]` Automate `karpathy/run_loop.py` into a nightly cron (2:00 AM).
  - `[ ]` Script the AI to read losing trades, write a new `FinBuddyFreqAI` variant, and trigger `autobacktest_v23.py`.
  - `[ ]` Implement auto-promotion if the new variant beats the live Sharpe ratio.

## 2026-05-16 — First Real v23 Backtest (NaN fix proved)
- Bull window 20240101-20240401, 5 pairs, k_tp=2.0/k_sl=1.0/m=0.60
- **1,159 trades, 18.3% WR, -3.68%, Sharpe -70.37, PF 0.50 — ALL 1159 SHORTS in a bull market**
- Volatility Hook works; Order Block veto absent (sub-task 2 unimplemented)
- Strategy needs rework before re-running 18-combo grid: model is short-biased, MTF filter not preventing shorts in 4h bullish pairs

---
*This file tracks the exact execution steps for Phase 13.*
