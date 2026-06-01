# Phase 1 — FreqAI as the Brain

> FreqAI is the primary signal intelligence. Trains on rolling market data, produces ML-powered long/short signals on Binance Futures USDT-M.

**Official Docs:** https://www.freqtrade.io/en/stable/freqai/
**Last Updated:** 2026-06-01

---

## Status as of 2026-06-01

| Sub-task | Status |
|---|---|
| 1.1 Build FreqAI Strategy | ✅ LIVE — v23 (`FinBuddyFreqAI_v23.py`) — LightGBMRegressor, z-scored target |
| 1.2 LLM Confirmation Layer | ✅ Built (v5) — **retired in v23**, v23 uses raw LightGBMRegressor only |
| 1.3 Walk-Forward OOS | 🟡 ACTIVE — daily 22:00 UTC + deep every 4 days. **BROKEN 5 days (cpu-shares bug) — FIXED 2026-06-01.** First real result tonight. |
| 1.4 Dry-run live | ✅ LIVE — +43.14 USDT, 475 trades, WR 37.9% |
| 1.5 Brain auto-promotion | ✅ WIRED — scan → Telegram Apply → promote.py → up -d. 1 promotion fired (LT=3.25, reverted due to deadlock, now safe with 2.5σ cap). |

---

## Live Config (2026-06-01)

| Item | Value |
|---|---|
| Strategy file | `freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py` |
| FreqAI identifier | `finbuddy_v23_promoted_1779997908` |
| Model | LightGBMRegressor — predicts z-scored `&-future_return` (N(0,1)) |
| Base timeframe | 15m |
| Informative TFs | 30m, 1h, 4h, 1d |
| Pairs | **26** (trimmed 2026-05-24) |
| Max open trades | 8 |
| Wallet | 1000 USDT dry-run |
| live_retrain_hours | 12 |
| Leverage | Confidence-based tiers 1×/2×/3× |
| Features | ~530: OHLCV × lags + 3 funding-rate + 3 OI (btc_ls_ratio) + macro + regime |
| DI / SVM | DI_threshold=1.0, SVM nu=0.05 |
| Stoploss | ATR-based entry-anchored, K_TP=2.25, K_SL=2.0 |

**Live env vars (`freqtrade/.env`):**
```
FREQAI_K_TP=2.25
FREQAI_K_SL=2.0
FREQAI_LONG_THRESHOLD=1.5
FREQAI_SHORT_THRESHOLD=-1.5
FREQAI_STABILITY_N=1
FREQAI_DAILY_LOSS_LIMIT=10
FINBUDDY_RECENT_WR=0.4
```

---

## Live Performance (2026-06-01)

| Metric | Value | Target |
|---|---|---|
| Closed trades | 475 | — |
| Win rate | 37.9% | > 50% ❌ |
| Total P&L | +43.14 USDT | — |
| Since last identifier (2026-05-28) | 25 trades, WR 44% | — |

---

## Key Strategy Mechanics

### Entry
- `predicted_return > dynamic_long_threshold` → LONG
- `predicted_return < dynamic_short_threshold` → SHORT
- `dynamic_long_threshold = min(LONG_THRESHOLD × combined_mult, MAX_EFFECTIVE_THRESHOLD=2.5)`
- `combined_mult = clip(regime_mult × wr_adj, upper=2.0)`
- **NEW 2026-06-01**: Hard cap at 2.5σ on final threshold — prevents any LT from creating impossible entry bar
- Regime multipliers: CRASH/BEAR raises long threshold; BULL/EUPHORIA raises short threshold
- WR feedback: `wr_adj = 1.0 - ((recent_wr - 0.55) × 2.0)` clamped [0.5, 2.0]
- Stability filter: N consecutive candles past threshold (N=STABILITY_N=1)
- EMA-50 trend filter + hard regime block (BEAR/CRASH blocks longs, BULL/EUPHORIA blocks shorts)
- Per-pair prediction std normalization: scales threshold by pair's rolling std vs global 0.95

### Stop-Loss / Exit
- Initial stop: K_SL × entry-time ATR (entry-anchored, not recomputed)
- Trail: locks profit once unrealized > K_TP × entry ATR
- Time limit: 12 candles (= 3h on 15m TF, matches label_period_candles=12)
- Volume shield: emergency exit if volume > 500% within first 10 candles

### Per-Pair-Per-Regime Gate
- `pair_regime_stats.json` — rolling 30d WR/PF per (pair, regime)
- Blocks combos where n≥5 AND WR<40% AND PF<0.7
- Currently blocked: OP/BEAR, LINK/NEUTRAL, DOT/NEUTRAL, AVAX/NEUTRAL

### Daily Circuit Breaker
- `custom_stake_amount()`: reads `FREQAI_DAILY_LOSS_LIMIT=10` from env
- Blocks new entries when today's UTC closed P&L < -10 USDT

---

## Walk-Forward OOS

**Configuration:**
- Daily: `walkforward_daily.sh` — 22:00 UTC, 1 fold (4mo train + 1mo test), sequential (1 worker)
- Deep: `walkforward_deep.sh` — 18:30 UTC every 4 days, 7 folds, 18mo window (6mo train + 1mo test + 2mo slide), 1 worker

**CRITICAL BUG FIXED 2026-06-01:** `--cpu-shares` flag in shell scripts was passed to `docker-compose run` which rejects it → all folds crashed with "unknown flag: --cpu-shares" → WF returned 0 folds for 5 consecutive days (May 27–31). Fixed by removing the flag from `walk_forward.py`.

**Gate criteria for Phase 10:**
- WR > 50%, Sharpe > 0.5, Max Drawdown < 20%, Profit Factor > 1.2

**WF history:**
- May 24 run: 1 fold, 0 trades in test window (model not generating signals at LT=1.5 in bear test)
- May 27–31 runs: 0 folds (cpu-shares crash bug — now fixed)
- June 1+ runs: expected to produce real results

---

## Brain Auto-Promotion

**Pipeline:**
```
brain run (*/10 cron, flock, two-tier scout) → analyst (30min past every 6h) → scan (07:00 daily)
  → if winner: pending.json + Telegram Apply/Skip button
  → user taps Apply → telegram_listener → promote.py --apply
  → backup config.json, write .env, bump identifier, docker-compose up -d
```

**Promotion criteria (updated 2026-06-01):**
- ≥2 bull AND ≥1 bear z-scored experiments with same config_hash
- avg_profit > 0 AND min_profit > -0.3 per leg
- WR ≥ 50% in at least 1 bull run AND 1 bear run
- bear_2026Q1 REQUIRED gate: if tested, must have WR ≥ 50%
- profit improvement ≥ +0.1pp vs live_baseline

**Brain state (2026-06-01):**
- 380 completed (102 z-scored), 261 queued
- Queue now alternates bear/bull at runner level (permanent root fix)
- **Best config**: lt=3.25, st=-3.0, k_sl=2.0, k_tp=2.25 → 2 bull + 1 bear passing; promotion Telegram sent
- **Pending**: bear_2026Q1 validation for this config (bear_2025Q1 = WR 61.4%; need bear_2026Q1 WR≥50%)
- LT=3.25 deadlock ELIMINATED by MAX_EFFECTIVE_THRESHOLD=2.5 cap

---

## Phase 1 "Complete" Definition

- [x] FreqAI live in dry-run on Binance Futures USDT-M (✅ since 2026-05-19)
- [x] Long + Short signals with regime awareness (✅)
- [x] Brain → live promotion pipeline wired end-to-end (✅)
- [x] Walk-forward producing real results (🟡 bug fixed 2026-06-01, first results tonight)
- [ ] Brain promotes first z-scored config with WR ≥ 50% (candidate found, pending bear_2026Q1)
- [ ] 60-day dry-run track record with PF > 1.2 OR walk-forward PASS
- [ ] Phase 10 gate met → real capital deployment

---

## AI Models Used

| Class | Role | Status |
|---|---|---|
| `LightGBMRegressor` | v23 live model — predicts z-scored `&-future_return` | ✅ Active |
| `LightGBMClassifier` | v22 model (retired) | 🗄️ History only |
| `FinBuddyLLMModel` v5 | LLM confirmation wrapper (retired in v23) | 🗄️ History only |

---

## Retired / Dead Things

| Thing | Status |
|---|---|
| `FinBuddyFreqAI.py` (bare-name, v22) | History only |
| `FinBuddyLLMModel.py` (v5) | Retired in v23 |
| Per-pair median offset | Removed 2026-05-22 |
| OB veto conditions | Removed 2026-05-22 |
| `%-recent_wr` feature | Removed 2026-05-20 |
| `class_weight=balanced` | No-op for LightGBMRegressor |
| Brain parallel pair-group split | Reverted 2026-05-24 |
| `--cpu-shares` in WF | Removed 2026-06-01 — docker-compose run does not support it |

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
