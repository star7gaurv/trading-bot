# Phase 13: The Conscious Brain (God-Tier Architecture)

**Status**: 🟢 OPERATIONAL — autonomous brain running on cron, exploring 3-month windows × multiple architectures
**Last verified**: 2026-05-18

## What Is Actually Running

The brain is a closed-loop hypothesis engine. No human input needed between alerts.

```
generate (6h cycle) → queue.jsonl → run (10min cycle) → log.jsonl → scan (daily) → Telegram alert
```

Cron entries (`crontab -l`):
- `*/10 * * * *` — run 1 hypothesis per cycle (accelerated from 30min on 2026-05-18)
- `0 */6 * * *` — generate 4 safe + 6 aggressive hypotheses, queue them
- `0 7 * * *` — daily promotion-candidate scan
- `0 8 * * *` — daily digest to Telegram (added 2026-05-18)

## Pillars

- `[x]` **1. Omni-Timeframe (The Eyes)** — REAL in `FinBuddyFreqAI_v23.py`
  - 5m base + 15m/1h/4h informatives via `include_timeframes`
  - `label_period_candles=72` (~6h horizon on 5m)

- `[x]` **2. Liquidity / Order Block Awareness (The Map)** — REAL in v23 (corrected 2026-05-18)
  - `populate_indicators` lines 716-739: supply/demand zone detection (impulsive-move + last-opposing-candle)
  - `populate_entry_trend` lines 789, 810: veto longs under bearish OB, veto shorts above bullish OB

- `[x]` **3. Real-Time Dynamic Stoploss (The Shield)** — REAL in v23 `custom_stoploss` lines 152-161
  - Volume-spike emergency exit if volume > 500% within 10min of entry

- `[x]` **4. Self-Evolution Pipeline (The Brain)** — REAL — scripts/brain/* (corrected 2026-05-18)
  - `hypothesis_gen.py`: SAFE band (perturb around current best) + AGGRESSIVE band (50% guided around top-3 results, 50% random sweep)
  - `runner.py`: spawns isolated docker-compose backtest with env overrides, parses metrics
  - `experiment_log.py`: append-only JSONL log + queue
  - `scan` (daily): finds configs that beat baseline on bull+bear → Telegram with Apply button
  - **Missing**: full auto-apply (currently scan only proposes; Apply button still routes through human approval)

## Current Results (2026-05-18)

| Metric | Value |
|---|---|
| Experiments completed | 19 |
| Hypotheses queued | 125 |
| Failed | 5 |
| Best profit_pct | **-0.106%** (basically break-even, single window) |
| Best WR | 52.9% (same config, bear_2025Q1, 5m, v23) |
| Positive-profit runs | 0 |
| Architectures tested | v23 only (v22 seeds not yet auto-queued) |

## Windows Brain Evaluates

| Name | Range | Regime |
|---|---|---|
| bull_2024Q1 | 2024-01-01 → 2024-04-01 | BTC +60% — strong bull |
| bull_2024Q2 | 2024-04-01 → 2024-07-01 | mid-2024 chop |
| bear_2025Q1 | 2025-01-01 → 2025-04-01 | BTC -28% — bear |

## Promotion Criteria for v23 → live swap

NOT YET — brain has produced zero positive-profit runs. Criteria proposed (2026-05-18):
1. ≥3 v23 configs with `profit_pct > 0` on BOTH bull AND bear windows
2. Best v23 PF ≥ 1.2
3. Validated on 3rd window

When met, scan will send Telegram alert with config hash + Apply button.

## Where the Brain Code Lives

```
scripts/brain/
├── brain_cli.py         — operator interface (status/best/run/generate/scan)
├── hypothesis_gen.py    — safe + aggressive variant generation
├── runner.py            — docker-compose backtest spawner + metrics parser
├── experiment_log.py    — JSONL store
├── digest.py            — daily Telegram digest (added 2026-05-18)
├── promote.py           — Apply/skip handlers (callback_data routes here)
└── README.md            — operator cheatsheet
```

State files:
- `finbuddy_memory/experiments/queue.jsonl` — pending hypotheses
- `finbuddy_memory/experiments/log.jsonl` — completed results

Logs (gitignored):
- `~/.finbuddy/logs/brain_run.log`
- `~/.finbuddy/logs/brain_gen.log`
- `~/.finbuddy/logs/brain_scan.log`
- `~/.finbuddy/logs/brain_digest.log`
