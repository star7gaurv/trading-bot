# Phase 13: The Conscious Brain

**Status**: 🟢 OPERATIONAL — brain runs every 10m, parallel pair-group split unblocked experiments  
**Last Updated**: 2026-05-23

---

## What Is Actually Running

The brain is a closed-loop hypothesis engine. No human input needed between alerts.

```
generate (6h cycle) → queue.jsonl → run (10min cycle) → log.jsonl → analyse (6h cycle)
  → scan (daily 07:00) → Telegram Apply/Skip → promote.py --apply → docker-compose up -d
```

### Cron entries
```
*/10 * * * *   brain_cli.py run --max 1         # one experiment per fire
0 */6 * * *    brain_cli.py generate             # 4 safe + 6 aggressive hypotheses
30 */6 * * *   brain_cli.py analyse              # self-diagnose + prune dead patterns
0 7 * * *      brain_cli.py scan                 # promotion-candidate scan → Telegram
0 8 * * *      brain_digest.py                   # daily digest to Telegram
0 22 * * *     walkforward_daily.sh              # daily WF (3 folds, 6h timeout, ~10h)
0 3 */4 * *    walkforward_deep.sh              # deep WF (21 folds, 6h timeout, ~38.5h)
0 4 * * *      auto_promote.py                   # WF Sharpe vs baseline alert
*/30 * * * *   walkforward_notify.py             # PASS/FAIL Telegram on new WF summary
```

---

## Brain Pillars

- **[x] 1. Omni-Timeframe (The Eyes)** — LIVE in `FinBuddyFreqAI_v23.py`
  - 15m base + 30m/1h/4h/1d informatives via `include_timeframes`
  - `label_period_candles=24` (~6h horizon on 15m)

- **[x] 2. Self-Evolution Pipeline (The Brain)** — LIVE in `scripts/brain/`
  - `hypothesis_gen.py`: SAFE band (perturb around current best) + AGGRESSIVE band
  - `runner.py`: **parallel pair-group split** — 37 pairs → 2 groups of ~18-19, ThreadPoolExecutor(max_workers=2)
  - `experiment_log.py`: append-only JSONL log + queue
  - `promote.py`: Apply/skip handlers + WR gate (≥50% required)
  - `auto_promote.py`: WF Sharpe vs baseline notification

- **[x] 3. Dynamic Stoploss (The Shield)** — LIVE in `custom_stoploss`
  - ATR-based initial stop, entry-anchored (not recomputed — fixed 2026-05-19)
  - Volume-spike emergency exit if volume > 500% within first 10 candles of entry

- **[x] 4. Per-Pair-Per-Regime Gate** — LIVE
  - `pair_regime_stats.json` tracks rolling 30d WR/PF per (pair, regime)
  - Blocks combos with n≥5, WR<40%, PF<0.7

- **[~] 5. Order Block Veto** — **REMOVED 2026-05-22**
  - Was blocking 100% of longs and 95% of shorts (reversal logic incompatible with trend-following ML)
  - Removed from `populate_entry_trend` in commit `b44aebe`

---

## Brain State (2026-05-23)

| Metric | Value |
|---|---|
| Legacy experiments (raw-% target) | 268+ — ALL excluded from promotion |
| Z-scored experiments completed | Starting to accumulate after parallel split fix |
| Pending in queue | ~200 |
| Promotions | 0 (brain restarting fresh with z-scored target) |
| Oldest pending | ~38h (accumulated during 100% timeout period) |

**Why 268 legacy experiments are excluded:**  
Old experiments used raw-percentage target (e.g. `&-future_return` in percent, not z-scored).  
Current strategy uses z-scored N(0,1) predictions. Thresholds are incompatible (0.5 vs old ±3.0).  
`find_candidates()` filters to `target_version="zscore"` only.

**Why experiments were failing (fixed 2026-05-23):**  
37-pair sequential backtest = ~74 min > `BACKTEST_TIMEOUT_S=3900` (65 min).  
Every experiment timed out and was logged as FAILED.  
Fix: parallel pair-group split — each group ~38 min, both run simultaneously.

---

## Windows Brain Evaluates

| Name | Range | Market | Added |
|---|---|---|---|
| bull_2024Q1 | 2024-01-01 → 2024-04-01 | BTC +60% bull | Original |
| bull_2024Q2 | 2024-04-01 → 2024-07-01 | Mid-2024 chop | Original |
| bear_2025Q1 | 2025-01-01 → 2025-04-01 | BTC -28% bear | Original |
| bull_2025Q4 | 2025-10-01 → 2026-01-01 | Late-2025 bull | Added 2026-05-22 (was invisible) |
| bear_2026Q1 | 2026-01-01 → 2026-04-01 | 2026 bear | Added 2026-05-22 (was invisible) |

**Why the 2025 windows were invisible before:** Their names `recent_2025Q4`/`recent_2026Q1` had no "bull"/"bear" substring — `promote.py`'s substring classifier couldn't classify them and dropped them. Renamed and fixed 2026-05-22 (commit `3deeafc` Fix 1).

---

## Promotion Criteria (as of 2026-05-23)

```python
# in promote.py find_candidates()
# 1. Must have ≥2 bull runs AND ≥2 bear runs with same config_hash
# 2. avg_profit > 0 AND min_profit > -0.3 per leg
# 3. profit improvement ≥ +0.1pp vs live_baseline
# 4. WR gate (NEW 2026-05-23): ≥1 bull run AND ≥1 bear run with WR ≥ 50%
```

First promotion requires all 4 conditions met across ≥2 bull + ≥2 bear z-scored experiments.

---

## Brain Code Structure

```
scripts/brain/
├── brain_cli.py         — operator interface (status/best/run/generate/analyse/scan/requeue)
├── hypothesis_gen.py    — SEED + safe + aggressive variant generation
│                          SEED: long=1.5, short=-0.8 (asymmetric — guides brain to fix SHORT WR)
├── runner.py            — docker-compose backtest spawner + PARALLEL PAIR-GROUP SPLIT
│   ├── _load_brain_pairs()           — loads pair_whitelist from brain config
│   ├── _create_pair_group_config()   — writes temp config with pair subset
│   ├── _parse_raw_trades_from_zip()  — extracts trade list from FreqTrade result zip
│   ├── _compute_metrics_from_raw_trades() — WR/PF/Sharpe/profit from raw trades
│   ├── _build_env_args()             — builds docker env overrides
│   ├── _run_hypothesis_group()       — runs one docker backtest for pair subset
│   └── run_hypothesis()              — splits into 2 groups, runs parallel, merges results
├── experiment_log.py    — JSONL store (queue + log)
├── analyst.py           — pattern analysis + pruning
├── digest.py            — daily Telegram digest
├── promote.py           — Apply/skip handlers, find_candidates() with WR gate
└── README.md            — operator cheatsheet
```

**State files:**
- `finbuddy_memory/experiments/queue.jsonl` — pending hypotheses
- `finbuddy_memory/experiments/log.jsonl` — completed results
- `finbuddy_memory/promotions/live_baseline.json` — current live config for comparison
- `finbuddy_memory/promotions/pending.json` — candidate waiting for Apply/Skip

**Logs:**
- `~/.finbuddy/logs/brain_run.log` — most important, shows completed/FAILED per experiment
- `~/.finbuddy/logs/brain_gen.log`
- `~/.finbuddy/logs/brain_scan.log`
- `~/.finbuddy/logs/brain_analyst.log`

---

## Hypothesis Generation

**SEED (starting point):**
```python
SEED_CONFIG_V23 = {
    "arch": "v23",
    "strategy": "FinBuddyFreqAI_v23",
    "freqaimodel": "LightGBMRegressor",
    "long_threshold": 1.5,
    "short_threshold": -0.8,   # was -1.5 — tighter bar to fix SHORT WR (updated 2026-05-23)
    "k_sl": 2.0, "k_tp": 2.0,
    "stability_n": 2,
    "label_period_candles": 24,
    "filter_di": True, "filter_svm": True,
    "feature_set": "all",
}
```

**Generation modes:**
- SAFE: perturb ±1 step on one param around current best config
- AGGRESSIVE: 50% guided around top-3 results, 50% random parameter sweep

---

## Known Bugs Fixed (history)

| Bug | Fixed | Commit |
|---|---|---|
| Brain windows invisible (no bull/bear substring) | 2026-05-22 | `3deeafc` |
| SEED thresholds ±3.0 unreachable for N(0,1) | 2026-05-22 | `3deeafc` |
| 268 legacy raw-% experiments contaminating promotion | 2026-05-22 | `3deeafc` |
| filter_di/filter_svm never passed to docker | 2026-05-22 | `3deeafc` |
| Config hash non-deterministic | 2026-05-22 | `3deeafc` |
| OB veto blocking 100% longs / 95% shorts | 2026-05-22 | `b44aebe` |
| Brain stoploss -0.08 vs live -0.04 | 2026-05-22 | `edc9435` |
| promote.py using docker-compose restart (didn't reload .env) | 2026-05-22 | `edc9435` |
| Brain experiments 100% timeout (37 pairs > 65-min limit) | 2026-05-23 | `8bede56` |
| Brain promotion not checking WR | 2026-05-23 | `8bede56` |
| SEED short_threshold too loose (-1.5) | 2026-05-23 | `8bede56` |

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
