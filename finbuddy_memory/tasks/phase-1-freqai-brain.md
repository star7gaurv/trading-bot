# Phase 1 — FreqAI as the Brain

> FreqAI is the primary signal intelligence. Trains on rolling market data, produces ML-powered long/short signals on Binance Futures USDT-M.

**Official Docs:** https://www.freqtrade.io/en/stable/freqai/  
**Last Updated:** 2026-05-23

---

## Status as of 2026-05-23

| Sub-task | Status |
|---|---|
| 1.1 Build FreqAI Strategy | ✅ LIVE — v23 (`FinBuddyFreqAI_v23.py`) — LightGBMRegressor, z-scored target |
| 1.2 LLM Confirmation Layer | ✅ Built (v5) — **retired in v23**, v23 uses raw LightGBMRegressor only |
| 1.3 Walk-Forward OOS | 🟡 ACTIVE — daily 22:00 UTC + deep every 4 days. Folds were timing out until 2026-05-23 fix. First real results tonight. |
| 1.4 Dry-run live | ✅ LIVE — +97 USDT, 334 trades, WR 38.6%, PF 1.37 since ~2026-04-04 |
| 1.5 Brain auto-promotion | ✅ WIRED — scan → Telegram Apply → promote.py → up -d. No promotion yet (restarting with z-scored target). |

---

## Live Config (2026-05-23)

| Item | Value |
|---|---|
| Strategy file | `freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py` |
| FreqAI identifier | `finbuddy_v23_no_median_1779447827` |
| Model | LightGBMRegressor — predicts z-scored `&-future_return` (N(0,1)) |
| Base timeframe | 15m |
| Informative TFs | 30m, 1h, 4h, 1d |
| Pairs | 37, Binance Futures USDT-M perpetual, isolated margin |
| Max open trades | 8 |
| Wallet | 1000 USDT dry-run |
| Leverage | Confidence-based tiers 1×/2×/3× by `predicted_return / threshold` ratio |
| Features | ~530: OHLCV × lags × corr-pairs + 3 funding-rate + macro + regime + fear_greed + btc_strength |
| DI / SVM | DI_threshold=1.0, use_SVM_to_remove_outliers=true |
| Stoploss | ATR-based, K_TP=2.0, K_SL=2.0, entry-anchored (not recomputed each candle) |

**Live env vars (`freqtrade/.env`):**
```
FREQAI_K_TP=2.0
FREQAI_K_SL=2.0
FREQAI_LONG_THRESHOLD=0.5
FREQAI_SHORT_THRESHOLD=-0.5
FREQAI_STABILITY_N=1
FREQAI_DAILY_LOSS_LIMIT=10
FREQAI_LEV_LOW_CONF_RATIO=1.0
FREQAI_LEV_MED_CONF_RATIO=1.5
FREQAI_LEV_HIGH_CONF_RATIO=2.0
FREQAI_LEV_LOW=1.0
FREQAI_LEV_MED=2.0
FREQAI_LEV_HIGH=3.0
FINBUDDY_RECENT_WR=0.42
```

---

## Live Performance (2026-05-23)

| Metric | Value | Target |
|---|---|---|
| Closed trades | 334 | — |
| Win rate | 38.6% | > 50% ❌ |
| Profit factor | 1.37 | > 1.2 ✅ |
| Total P&L | +97 USDT | — |
| Max drawdown | ~3.2% | < 15% ✅ |
| Avg daily P&L | ~3.3 USDT | 10 USDT ❌ |
| LONG WR | ~57% (68 trades) | ✅ strong |
| SHORT WR | ~34% (249 trades) | ❌ needs improvement |

---

## Key Strategy Mechanics

### Entry
- `predicted_return > dynamic_long_threshold` → LONG
- `predicted_return < dynamic_short_threshold` → SHORT
- `dynamic_long_threshold = LONG_THRESHOLD × regime_mult × wr_adj` (capped at 2.0× combined)
- `dynamic_short_threshold = -(SHORT_THRESHOLD × regime_mult × wr_adj)` (capped at 2.0× combined)
- Regime multipliers: CRASH/BEAR raises long threshold; BULL/EUPHORIA raises short threshold
- WR feedback: `wr_adj = 1.0 - ((recent_wr - 0.55) × 2.0)` clamped [0.5, 2.0]
- Stability filter: N consecutive candles past threshold (N=FREQAI_STABILITY_N=1)
- EMA-50 trend filter: longs require `close > ema_50`, shorts require `close < ema_50`

### Stop-Loss / Exit
- Initial stop: K_SL × entry-time ATR (cached via `trade.set_custom_data`, not recomputed)
- Trail: locks profit once unrealized > K_TP × ATR
- Time limit: 24 candles (= 6h on 15m TF)
- Volume shield: emergency exit if volume > 500% within first 10 candles

### Per-Pair-Per-Regime Gate
- `pair_regime_stats.json` — rolling 30d WR/PF per (pair, regime)
- Blocks combos where n≥5 AND WR<40% AND PF<0.7
- Currently blocked: OP/BEAR, LINK/NEUTRAL, AAVE/NEUTRAL, ZEC/NEUTRAL

### Daily Circuit Breaker (added 2026-05-23)
- `custom_stake_amount()`: reads `FREQAI_DAILY_LOSS_LIMIT=10` from env
- Blocks new entries when today's UTC closed P&L < -10 USDT
- Prevents -26 USDT loss days (May 14 was -26.53 USDT)

---

## Walk-Forward OOS

**Configuration:**
- Daily: `walkforward_daily.sh` — 22:00 UTC, 9mo window (train=6mo, test=1mo, slide=1mo), 3 folds, 2 workers, **6h fold timeout** (fixed 2026-05-23)
- Deep: `walkforward_deep.sh` — 03:00 UTC every 4 days, 27mo window, 21 folds, 2 workers

**Gate criteria for Phase 10:**
- WR > 50%
- Sharpe > 0.5
- Max Drawdown < 20%
- Profit Factor > 1.2

**History:**
- All folds were producing empty `[]` results until 2026-05-23 (fold timeout 4.5h, training needs 5.5-6h)
- fold_03 was actively backtesting when killed — only 30 min from finishing
- Fix: timeout 16200 → 21600 (6h). First real fold results expected tonight 22:00 UTC.

---

## Brain Auto-Promotion

**Pipeline:**
```
brain run (*/10 cron) → analyst (30min past every 6h) → scan (07:00 daily)
  → if winner: pending.json + Telegram Apply/Skip button
  → user taps Apply → telegram_listener → promote.py --apply
  → backup config.json, write .env, bump identifier, docker-compose up -d
```

**Promotion criteria (updated 2026-05-23):**
- ≥2 bull AND ≥2 bear z-scored experiments with same config_hash
- avg_profit > 0 AND min_profit > -0.3 per leg
- **WR ≥ 50% in at least 1 bull run AND 1 bear run** (new gate, 2026-05-23)
- profit improvement ≥ +0.1pp vs live_baseline

**Brain state:**
- 268+ legacy experiments — all excluded (raw-% target, wrong label semantics)
- Fresh z-scored experiments: started accumulating with correct parallel split fix
- SEED: long_threshold=1.5, short_threshold=-0.8 (guides brain to fix SHORT WR)
- Windows: bull_2024Q1, bull_2024Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1

---

## Phase 1 "Complete" Definition

- [x] FreqAI live in dry-run on Binance Futures USDT-M (✅ since 2026-05-19)
- [x] Long + Short signals with regime awareness (✅)
- [x] Brain → live promotion pipeline wired end-to-end (✅)
- [x] Walk-forward producing real results (🟡 fix shipped, first results tonight)
- [ ] Brain promotes first z-scored config with WR ≥ 50%
- [ ] 60-day dry-run track record with PF > 1.2 OR walk-forward PASS
- [ ] Phase 10 gate met → real capital deployment

Either path unlocks Phase 10.

---

## AI Models Used

| Class | Role | Status |
|---|---|---|
| `LightGBMRegressor` | v23 live model — predicts z-scored `&-future_return` | ✅ Active |
| `LightGBMClassifier` | v22 model (retired) | 🗄️ History only |
| `FinBuddyLLMModel` v5 | LLM confirmation wrapper (retired in v23) | 🗄️ History only |
| `XGBoostClassifier` | Available, not used | — |
| `PyTorchMLPRegressor` | Available for future | — |

---

## Retired / Dead Things

| Thing | Status |
|---|---|
| `FinBuddyFreqAI.py` (bare-name, v22) | History only — live is `FinBuddyFreqAI_v23.py` |
| `FinBuddyLLMModel.py` (v5) | Retired in v23 |
| Per-pair median offset | Removed 2026-05-22 (z-score already centers predictions) |
| OB veto conditions | Removed 2026-05-22 (reversal logic incompatible with trend ML) |
| `%-recent_wr` feature | Removed 2026-05-20 (training-serving skew) |
| `class_weight=balanced` | No-op for LightGBMRegressor — removed |

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
