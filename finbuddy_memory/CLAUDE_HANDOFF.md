# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-24 UTC (CPU optimization + pair trim 37→26 + watchdog fix)  
**Branch:** `master`  
**Latest commits:** `019fad5` watchdog 8h→14h | `bb4fa96` pair trim 37→26 + CPU fixes | `8bede56` P0-P2 fixes

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, z-scored target) |
| FreqAI identifier | `finbuddy_v23_no_median_1779447827` |
| Model features | ~530 (3 funding-rate + macro + regime + OHLCV lags; `%-recent_wr` removed) |
| **Pairs** | **26** (trimmed from 37 on 2026-05-24 — removed 11 zero/negative-edge pairs) |
| Leverage | Confidence-based tiers 1×/2×/3× (FALLBACK = LOW = 1×) |
| Regime | NEUTRAL (as of 2026-05-24) |
| Wallet | **1000 USDT** dry-run |
| Live P&L | 356 trades, +86.19 USDT, WR 38.2%, PF 1.31 |
| Bot status | ✅ Up, restarted 2026-05-24 18:02 UTC after pair trim + cache flush |
| live_retrain_hours | **12** (was 4 — changed 2026-05-24) |
| Per-pair-per-regime gate | ✅ Active. Stale entries for removed pairs cleared. |
| DI / SVM | DI_threshold=1.0, use_SVM_to_remove_outliers=true |
| Daily circuit breaker | ✅ ACTIVE — FREQAI_DAILY_LOSS_LIMIT=10 |
| Load average | ~0.5–1.5 (was 7.38 before CPU optimization) |

**26 active pairs:** 1000PEPE, ADA, APT, ARB, AVAX, BTC, DOT, ENA, ETH, FET, FIL, LDO, LINK, LTC, NEAR, ONDO, OP, POL, RENDER, SOL, SUI, TAO, TON, UNI, WIF, XRP  
**Watch list (review June 7):** AVAX, ADA — borderline edge

**Live env vars (in `freqtrade/.env` AND `docker-compose.yml` environment block):**
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

⚠️ **IMPORTANT:** `docker-compose.yml` has an explicit `environment:` block — every new `.env` var MUST also be added there, or the container never sees it. `docker-compose restart` does NOT reload `.env` — always use `docker-compose up -d freqtrade`.

---

## 🏗️ Phase 14 — Path to 10 USDT/Day (Active)

Full task file: `finbuddy_memory/tasks/phase-14-10usdt-daily.md`

| Task | Status |
|---|---|
| P0.1 Brain parallel split → **REVERTED to single-group** | ✅ Reverted 2026-05-24 — parallel caused 3.5 vCPU sustained |
| P0.2 WF fold timeout 4.5h → 6h | ✅ Done `8bede56` |
| P1 Daily circuit breaker 10 USDT | ✅ Done |
| P2.1 Brain WR gate ≥50% | ✅ Done |
| P2.2 SEED short_threshold -1.5 → -0.8 | ✅ Done |
| P2.3 Combined multiplier cap 2.0× | ✅ Done |
| CPU optimization (cron, executor removal, nice WF) | ✅ Done 2026-05-24 |
| Pair trim 37→26 (11 zero-edge pairs removed) | ✅ Done 2026-05-24 |
| P3.1 Open Interest Delta feature | 🟡 PARTIAL — script + cron exist, parquet builds at 01:30 UTC tonight |
| P3.2 Leverage tier tuning | ⬜ NEXT |
| P4 Phase 10 prep scripts | ⬜ Deferred |

---

## 🧠 Brain State

| Item | Value |
|---|---|
| Execution mode | **Single-group** — all 26 pairs in one backtest per experiment (~51 min) |
| Cron | `*/30 * * * *` with `flock -n` (was */10 without lock — caused CPU starvation) |
| Legacy experiments | 268+ — ALL excluded (raw-% target, incompatible with z-score) |
| Z-scored experiments | Accumulating on 26-pair universe |
| Queue pending | ~200+ |
| Promotions fired | 0 |
| SEED thresholds | long=1.5, short=-0.8 |
| Windows | bull_2024Q1/Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1 |
| WR gate | ≥1 bull + ≥1 bear run must have WR ≥ 50% |
| First promotion needs | ≥2 bull + ≥2 bear z-scored passing all gates |

---

## 📊 Walk-Forward State

| Run | Schedule | Folds | Timeout/fold | Workers | Status |
|---|---|---|---|---|---|
| Daily | 22:00 UTC | **1** (was 3) | 6h | 1 (sequential) | ✅ Armed |
| Deep | 03:00 UTC every 4 days | 21 | 6h | 1 (nice -n 19 ionice -c 3) | ✅ Armed — subconscious mode |

**Daily WF change (2026-05-24):** Reduced to 1 fold — regression detector only. Completes by ~03:30 UTC. Deep WF every 4 days is the source of truth for promotion decisions.  
**Deep WF (2026-05-24):** Wrapped in `nice -n 19 ionice -c 3` — absorbs idle CPU without blocking brain or live bot.

**Gate for Phase 10:** WR > 50%, Sharpe > 0.5, DD < 20%, PF > 1.2 across ≥3 folds (deep WF).

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
| `FinBuddyFreqAI.py` (bare-name v22) | History only — live is `FinBuddyFreqAI_v23.py` |
| `FinBuddyLLMModel.py` (v5) | Retired in v23 |
| Per-pair median offset | Removed 2026-05-22 — z-score already centers predictions |
| OB veto conditions | Removed 2026-05-22 — reversal logic incompatible with trend ML |
| `%-recent_wr` feature | Removed 2026-05-20 — training-serving skew |
| `class_weight=balanced` | No-op for regressor — removed |
| `scripts/run_promotion.sh` | Removed from cron 2026-05-19 |
| `executor_wrapper.sh` + `executor.py` + `freqtrade_bridge.py` | **Deleted 2026-05-24** — legacy Phase 7, dead weight |
| OpenClaw container | **Killed 2026-05-24** — was abandoned, was burning 4.2% CPU |
| N8N pipeline | Permanently disabled |
| Phase 6 TradingView | Abandoned |
| Brain parallel pair-group split | **Reverted 2026-05-24** — doubled CPU, caused load avg 7.38 |
| REMOVED PAIRS | DASH, ZEC, BCH, DOGE, AAVE, TRX, 1000SHIB, BNB, INJ, HBAR, ATOM — do NOT re-add without 3+ weeks clean data |

---

## ⬜ Open Strategic Issues — Deferred

1. **P3.1 Open Interest delta** — `scripts/build_historical_oi.py` exists + cron at 01:30 UTC. Parquet builds tonight. After parquet exists: add 3 OI features to strategy, bump identifier, flush models, restart. See `phase-14-10usdt-daily.md`.
2. **P3.2 Leverage tier tuning** — MED_CONF 1.5→1.7, HIGH_CONF 2.0→2.5 in `.env` + `docker-compose.yml`.
3. **P4 Phase 10 prep** — `dry_run_report.py`, `kill_switch.sh`, `futures_live_config.json`. Deferred until WR ≥ 50% sustained.
4. **AVAX/ADA watch** — 2-week probation until June 7. If still negative edge, remove.

---

## ⏭️ Next Actions (priority order)

1. **Tonight 01:30 UTC** — `build_historical_oi.py` runs and creates `oi_history.parquet`. Once done: add OI features to strategy (P3.1).
2. **Tonight 22:00 UTC** — daily WF fires (1 fold, 26 pairs). Check result tomorrow morning:
   ```bash
   cat walkforward_results/$(ls -t walkforward_results/ | head -1)/summary.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('PASS' if d.get('pass') else 'FAIL', d.get('verdict',''))"
   ```
3. **Brain monitoring** — brain now on 26 pairs, single-group, */30. First good result → promotion path.
4. **June 7** — review AVAX/ADA watch list. Remove if still negative edge.

Phase 10 (live capital) still BLOCKED until WF passes all 4 gates OR 6-month dry-run track record.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub + session history
- [[CONTEXT]] — live context (auto-updated every 4h by sync_context.py)
- [[CLAUDE]] — deep project background
- [[tasks/TASKS.md]] — master phase index
- [[tasks/phase-14-10usdt-daily.md]] — current active roadmap ← READ THIS
- [[tasks/phase-1-freqai-brain.md]] — strategy details + live config
- [[tasks/pair_addition_runbook]] — 9-step pair-addition recipe
- `scripts/brain/README.md` — brain operator cheatsheet
