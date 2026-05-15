# Phase 13: The Conscious Brain (God-Tier Architecture)

**Status**: ⬜ PENDING
**Goal**: Transform FinBuddy into an Omni-Timeframe, Liquidity-Aware, Self-Evolving Intelligence with an 80% Win Rate.

## Sub-Tasks

- `[ ]` **1. Omni-Timeframe Architecture (The Eyes)**
  - `[ ]` Shift base timeframe in `config.json` from `1h` to `5m`.
  - `[ ]` Add `["15m", "1h", "4h"]` to `include_timeframes` in FreqAI config.
  - `[ ]` Scale `label_period_candles` from `6` to `72` (maintaining a 6-hour prediction horizon on a 5m base).
  - `[ ]` Update `FinBuddyFreqAI_v23.py` to correctly fetch informative pairs and ingest the new timeframes without memory exhaustion.

- `[ ]` **2. Liquidity & Order Block Awareness (The Map)**
  - `[ ]` Inject Smart Money Concepts (Volume Profile / Order Blocks) into feature engineering.
  - `[ ]` Implement veto logic: Block shorts directly above historical Bullish Order Blocks.
  - `[ ]` Implement veto logic: Block longs directly below historical Bearish Order Blocks.

- `[ ]` **3. Real-Time Dynamic Stoploss (The Shield)**
  - `[ ]` Build tick-volatility hook: monitor volume spikes immediately post-entry.
  - `[ ]` If volume spikes > 500% against the trade within 10 minutes, trigger an emergency market exit before the `K_SL` ATR stop is hit.

- `[ ]` **4. True Self-Evolution Pipeline (The Brain)**
  - `[ ]` Automate `karpathy/run_loop.py` into a nightly cron (2:00 AM).
  - `[ ]` Script the AI to read losing trades, write a new `FinBuddyFreqAI` variant, and trigger `autobacktest_v23.py`.
  - `[ ]` Implement auto-promotion if the new variant beats the live Sharpe ratio.

---
*This file tracks the exact execution steps for Phase 13.*
