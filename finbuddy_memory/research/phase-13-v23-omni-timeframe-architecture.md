# The v23 Pivot — Omni-Timeframe & MLOps (Phase 13)

**Date:** 2026-05-15
**Context:** This document outlines the architectural shift from the v21/v22 1-hour ML strategy to the v23 Omni-Timeframe (5m base) strategy.

## Why v21/v22 Failed
The v21 campaign attempted to solve a low Win Rate by slapping a "dumb" 4H macro trend gate (EMA50) over a 1H Machine Learning model. 

The backtest campaign ran on 2026-05-15 and completely failed (`0/18 PASS`, `WR 21%`). FreqAI was identifying valid 1H shorts, but the 4H trend was technically still bullish, so the gate blocked the good trades. Conversely, it let through bad trades because the 4H trend is a lagging indicator. The 1H model generated signals that conflicted massively with the static 4H gate. 

## How we fixed it (The Omni-Timeframe Shift)
We cannot restrict the AI with static rules; the AI must *learn* the rules. We shifted the entire architecture to **Phase 13: The Conscious Brain**:

1. **5-Minute Base:** The bot now evaluates the market every 5 minutes (`timeframe="5m"`), allowing it to snipe localized entries.
2. **Peripheral Vision:** FreqAI now natively ingests the `15m`, `1h`, and `4h` timeframes simultaneously (`include_timeframes`). The ML model processes these as features, learning the correlations between macro trends and micro pullbacks itself rather than being constrained by hardcoded Python `if/else` statements.
3. **Liquidity Vetoes:** We added 24-hour Order Block detection (Liquidity Pools). The bot strictly vetoes shorts at the bottom (Support) and longs at the top (Resistance) based on rolling 288-candle (`5m`) highs and lows.
4. **Volatility Shield:** A tick-volatility hook exits a trade immediately if volume spikes >500% against the position in the first 10 minutes, bypassing the slow ATR stoploss entirely.

## What the MLOps Loop does
We built a true Self-Evolution pipeline in `scripts/karpathy/run_loop.py`. 

Installed via cron (running at 2:00 AM nightly), this script:
1. Reads the results of the `v23` autobacktest CSV.
2. Evaluates if a "God-Tier" parameter set was found (`WR > 60%`, `Sharpe > 1.0`).
3. If true, automatically edits the live `docker-compose.yml` to inject the winning TP/SL multipliers and ML thresholds.
4. Restarts the Freqtrade Docker container to immediately begin trading with the evolved intelligence.

FinBuddy now evolves autonomously without human intervention.
