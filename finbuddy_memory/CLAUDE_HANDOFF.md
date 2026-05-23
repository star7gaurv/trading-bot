# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-23 UTC (P0–P2 fixes — commits `8bede56` + `aba9e4d`)  
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, z-scored target) |
| FreqAI identifier | `finbuddy_v23_no_median_1779447827` |
| Model features | ~530 (3 funding-rate + macro + regime + OHLCV lags; `%-recent_wr` removed) |
| Pairs | **37**, futures USDT-M isolated, max 8 trades |
| Leverage | Confidence-based tiers 1×/2×/3× (FALLBACK = LOW = 1×) |
| Regime | BEAR (as of 2026-05-23) |
| Wallet | **1000 USDT** dry-run |
| Live P&L | 334 trades, +97 USDT, WR 38.6%, PF 1.37 |
| Bot status | ✅ Up, restarted 2026-05-23 after P1 circuit breaker + P2.3 multiplier cap |
| Per-pair-per-regime gate | ✅ Active. Blocked: OP/BEAR, LINK/NEUTRAL, AAVE/NEUTRAL, ZEC/NEUTRAL |
| DI / SVM | DI_threshold=1.0, use_SVM_to_remove_outliers=true |
| Daily circuit breaker | ✅ ACTIVE — FREQAI_DAILY_LOSS_LIMIT=10 (blocks new trades when today P&L < -10 USDT) |

**Live env vars (in `freqtrade/.env` AND `docker-compose.yml` environment block):**
```
FREQAI_K_TP=2.0
FREQAI_K_SL=2.0
FREQAI_LONG_THRESHOLD=0.5
FREQAI_SHORT_THRESHOLD=-0.5
FREQAI_STABILITY_N=1
FREQAI_DAILY_LOSS_LIMIT=10        ← NEW 2026-05-23
FREQAI_LEV_LOW_CONF_RATIO=1.0
FREQAI_LEV_MED_CONF_RATIO=1.5
FREQAI_LEV_HIGH_CONF_RATIO=2.0
FREQAI_LEV_LOW=1.0
FREQAI_LEV_MED=2.0
FREQAI_LEV_HIGH=3.0
FINBUDDY_RECENT_WR=0.42
```

⚠️ **IMPORTANT:** `docker-compose.yml` has an explicit `environment:` block — every new `.env` var MUST also be added there, or the container never sees it. `docker-compose restart` does NOT reload `.env` — always use `docker-compose up -d freqtrade`.

---

## 🏗️ Phase 14 — Path to 10 USDT/Day (Active)

Full task file: `finbuddy_memory/tasks/phase-14-10usdt-daily.md`

| Task | Status |
|---|---|
| P0.1 Brain parallel pair-group split | ✅ Done `8bede56` |
| P0.2 WF fold timeout 4.5h → 6h | ✅ Done `8bede56` |
| P1 Daily circuit breaker 10 USDT | ✅ Done `8bede56` + `aba9e4d` |
| P2.1 Brain WR gate ≥50% | ✅ Done `8bede56` |
| P2.2 SEED short_threshold -1.5 → -0.8 | ✅ Done `8bede56` |
| P2.3 Combined multiplier cap 2.0× | ✅ Done `8bede56` |
| P3.1 Open Interest Delta feature | ⬜ NEXT |
| P3.2 Leverage tier tuning | ⬜ NEXT |
| P4 Phase 10 prep scripts | ⬜ Deferred |

---

## 🧠 Brain State

| Item | Value |
|---|---|
| Legacy experiments | 268+ — ALL excluded (raw-% target, incompatible with z-score) |
| Z-scored experiments | Starting to accumulate — parallel split fix deployed 2026-05-23 |
| Queue pending | ~200 |
| Promotions fired | 0 |
| SEED thresholds | long=1.5, short=-0.8 |
| Windows | bull_2024Q1/Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1 |
| WR gate | ≥1 bull + ≥1 bear run must have WR ≥ 50% |
| First promotion needs | ≥2 bull + ≥2 bear z-scored passing all gates |

**Why experiments were 100% failing (now fixed):** 37-pair sequential backtest ~74 min > 65-min timeout. Fixed by parallel pair-group split (2 groups × ~18-19 pairs, each ~38 min, run simultaneously).

---

## 📊 Walk-Forward State

| Run | Schedule | Folds | Timeout/fold | Status |
|---|---|---|---|---|
| Daily | 22:00 UTC | 3 | 6h (fixed 2026-05-23) | ✅ Armed — first real results tonight |
| Deep | 03:00 UTC every 4 days | 21 | 6h | ✅ Armed |

**Why folds were empty (now fixed):** timeout was 4.5h; 37-pair training needs 5.5-6h. fold_03 was backtesting when killed — 30 min from done. Fixed: timeout 16200 → 21600.

**Gate for Phase 10:** WR > 50%, Sharpe > 0.5, DD < 20%, PF > 1.2 across ≥3 folds.

---

## 📞 Telegram

| Bot | Token prefix | What |
|---|---|---|
| FreqTrade native | `8557119080:` | Trade events + daily summary |
| Brain | `8051489946:` | Brain digest + promotion Apply/Skip buttons |

Listener: `*/2 * * * * flock -n /tmp/finbuddy_telegram_listener.lock telegram_listener.py`

---

## 🚨 Known Dead/Stale Things — DO NOT RESURRECT

| Thing | Status |
|---|---|
| `FinBuddyFreqAI.py` (bare-name v22) | History only — live is `FinBuddyFreqAI_v23.py`. Always `grep '"strategy"' config.json` first. |
| `FinBuddyLLMModel.py` (v5) | Retired in v23 |
| Per-pair median offset | Removed 2026-05-22 — z-score already centers predictions |
| OB veto conditions | Removed 2026-05-22 — reversal logic incompatible with trend ML |
| `%-recent_wr` feature | Removed 2026-05-20 — training-serving skew |
| `class_weight=balanced` | No-op for regressor — removed |
| `scripts/run_promotion.sh` | Removed from cron 2026-05-19 |
| N8N pipeline | Permanently disabled |
| OpenClaw proxy | Abandoned |
| Phase 6 TradingView | Abandoned |
| Manual threshold tuning in `.env` | Brain owns LONG_THRESHOLD / SHORT_THRESHOLD |

---

## ⬜ Open Strategic Issues — Deferred

1. **P3.1 Open Interest delta** — `scripts/build_historical_oi.py` + add 3 features to strategy + bump identifier + flush models. See `phase-14-10usdt-daily.md`.
2. **P3.2 Leverage tier tuning** — MED_CONF 1.5→1.7, HIGH_CONF 2.0→2.5 in `.env` + `docker-compose.yml`. See `phase-14-10usdt-daily.md`.
3. **P4 Phase 10 prep** — `dry_run_report.py`, `kill_switch.sh`, `futures_live_config.json`. Deferred until WR ≥ 50% sustained.
4. **Brain analyst occasionally queues already-pruned TFs** — minor cycle waste, not blocking.

---

## ⏭️ Next Actions (priority order)

1. **Tonight 22:00 UTC** — daily WF fires with 6h timeout. Check tomorrow morning:
   ```bash
   cat walkforward_results/$(ls -t walkforward_results/ | head -1)/summary.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('PASS' if d.get('pass') else 'FAIL', d.get('verdict',''))"
   ```
2. **Check brain log tomorrow** — first `[brain] completed ...` entry (not FAILED) confirms parallel split working:
   ```bash
   grep -E "completed|FAILED" ~/.finbuddy/logs/brain_run.log | tail -20
   ```
3. **When brain accumulates 30+ z-scored experiments** — check if WR ≥ 50% in any bull+bear pair
4. **P3.1 next** — Open Interest Delta feature (bump identifier + flush models required after)
5. **P3.2 after** — Leverage tier tuning

Phase 10 (live capital) still BLOCKED until WF passes all 4 gates OR 6-month track record. v23 live since 2026-05-19; track record clock at ~4 days.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub + session history
- [[CONTEXT]] — live context injected into AI prompts
- [[CLAUDE]] — deep project background
- [[tasks/TASKS.md]] — master phase index
- [[tasks/phase-14-10usdt-daily.md]] — current active roadmap ← READ THIS
- [[tasks/phase-13-conscious-brain.md]] — brain architecture + bug history
- [[tasks/phase-1-freqai-brain.md]] — strategy details + live config
- [[tasks/pair_addition_runbook]] — 9-step pair-addition recipe
- `scripts/brain/README.md` — brain operator cheatsheet
