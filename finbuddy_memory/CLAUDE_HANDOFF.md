# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-20 20:00 UTC (end of a 13-commit, 3-audit-round day)
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor) |
| FreqAI identifier | `finbuddy_v23_sym_1779274506` |
| Model features | ~530 (3 funding-rate features added; `%-recent_wr` removed for train-serve skew) |
| Pairs | 25, futures USDT-M isolated, max 8 trades |
| **Leverage** | **Confidence-based tiers 1×/2×/3×** (commit `60d4fb4`, FALLBACK fixed to LOW per `5f37ab8`) |
| Regime | ⚪ NEUTRAL |
| Wallet | **1000 USDT** (reverted from 10000 in `2f01b56`) — current balance ~1110 |
| Live P&L | 296 trades, +$110.78 dry-run |
| Bot status | ✅ Up since 2026-05-20 ~19:55 UTC after threshold reload via `docker-compose up -d` |
| Per-pair-per-regime gate | ✅ Active |
| DI / SVM | DI_threshold=1.0, use_SVM_to_remove_outliers=true |
| `dry_run_wallet` | 1000 (live), 10000 (brain + WF — explicit env override per run) |

**Live env vars (in `freqtrade/.env`):**
```
FREQAI_K_TP=2.0
FREQAI_K_SL=2.0
FREQAI_LONG_THRESHOLD=2.0        # was 3.25 — loosened to restore trade volume
FREQAI_SHORT_THRESHOLD=-2.0      # was -2.75
FREQAI_STABILITY_N=1             # was 2
FINBUDDY_RECENT_WR=0.34
FREQAI_LEV_LOW_CONF_RATIO=1.0
FREQAI_LEV_MED_CONF_RATIO=1.5
FREQAI_LEV_HIGH_CONF_RATIO=2.0
FREQAI_LEV_LOW=1.0
FREQAI_LEV_MED=2.0
FREQAI_LEV_HIGH=3.0
```

---

## 🐛 13 Commits Shipped 2026-05-19 → 2026-05-20

### Round 1 — initial unblock + new feature
- `4702549` — Stop-ratchet + time-limit (cache entry_atr_pct via set_custom_data; 72→24 candles)
- `3eafab8` — Brain gates loosened + `requeue` CLI + baseline file
- `d7bd60e` — Funding-rate feature (3 cols, 7,333 events backfilled to 2019-09)
- `7c8bf52` — Live bot 6h dead recovery (flushed root cache) + auto_promote None rendering fix
- `d6c883d` — Daily WF cron (22:00 UTC) + auto_promote (04:00 UTC)
- `f9a8a2b` — WF per-fold timeout 3600s → 7200s

### Round 2 — structural symmetry + bias patch
- `b4b02b7` — 5 bugs + 3 cleanups: WF env-var drift, asymmetric RSI gate, longs-only funding gate, recent_wr feature drift, DI/SVM not in live config; stale timeframe attr, class_weight no-op, wallet 1000→10000
- `a187ab9` — Per-pair median offset for prediction long-bias (patch, not proper z-score)
- `60d4fb4` — Confidence-based leverage tiers (1x/2x/3x by ratio)
- `5fcf290` — WF timeout 7200s → 10800s (DI+SVM made each fold need 3h)
- `2f01b56` — Revert wallet 10000 → 1000

### Round 3 — config drift + races
- `5f37ab8` — 5 bugs: brain backtest config drifted from live (5 pairs vs 25!), cluster-cap race, leverage FALLBACK 2x→1x, gate order, regime read race
- Plus cron `%` escape fix for pair_performance (was silently broken 11 days)
- Plus `.env` reload requires `docker-compose up -d` not `restart` (memory note)

---

## 🧠 Brain (Autonomous Hypothesis Engine) — Active

| Cron | What |
|---|---|
| `*/10 * * * *` | One brain experiment per fire |
| `0 */6 * * *` | Generate 4 safe + 6 aggressive hypotheses |
| `30 */6 * * *` | Analyse + prune dead patterns |
| `0 7 * * *` | Daily promotion-candidate scan |
| `0 8 * * *` | Daily digest, daily_summary, pair_performance |
| `0 22 * * *` | **Daily walk-forward** (12mo rolling, ~18h with 25 pairs) |
| `0 3 1 * *` | Monthly heavy walk-forward (27mo) |
| `0 4 * * *` | `auto_promote.py` — WF Sharpe vs baseline Telegram |
| `25 1 * * *` | **Funding-rate parquet refresh** |
| `15 1 * * *` | Historical macro builder |
| `20 1 * * *` | Historical regime builder |

**Brain state (2026-05-20 evening):**
- 265+ completed experiments, ~26 queued
- 16 configs have ≥2 bull + ≥2 bear samples — but ALL have bull_avg ≤ 0 OR bull_sharpe ≤ 0 (the deferred long-bias root cause)
- Best `e0e1bf338410` profit=+0.192% WR=48.1% Sharpe=1.42 was on bear_2025Q1 only and from the 5-pair brain era (now legacy after `5f37ab8` aligned the universe)
- **Pre-2026-05-20 results marked legacy** via `live_baseline.json::config_aligned_at`

---

## 📞 Telegram

| Bot | Token prefix | What |
|---|---|---|
| FreqTrade native | `8557119080:` | Trade events |
| Brain | `8051489946:` | Digest + promotion candidates with Apply/Skip buttons |

Listener: `*/2 * * * * flock -n /tmp/finbuddy_telegram_listener.lock telegram_listener.py`

---

## 🚨 Known Dead/Stale Things — DO NOT RESURRECT

| Thing | Status |
|---|---|
| `FinBuddyFreqAI.py` (bare-name v22) | History only — never activate. **ALWAYS `grep '"strategy"' config.json` before editing strategy file.** |
| `FinBuddyLLMModel.py` (v5) | v23 dropped LLM wrapper |
| `scripts/run_promotion.sh` | Removed from cron 2026-05-19 (legacy CSV path) |
| `walk_forward.py` v22 re-runs | v22 catastrophe; never re-run |
| N8N pipeline | Permanently disabled |
| OpenClaw proxy | Abandoned |
| Phase 6 TradingView | Abandoned (paid plan required) |
| Manual threshold tuning | Brain owns this |

---

## ⚠️ Open Strategic Issues — Deferred to Future Sessions

1. **Target z-scoring at train time** — proper fix for prediction long-bias. The per-pair median offset in `a187ab9` is a runtime patch; properly normalize `&-future_return` in `set_freqai_targets`. ~Half-day project.
2. **Open Interest delta** as a new feature — second-best published signal after funding rate. Build script analogous to `build_historical_funding.py`.
3. **Pair expansion to 37 pairs** — full 9-step runbook at `finbuddy_memory/tasks/pair_addition_runbook.md`. Gated on tonight's WF result.
4. **Brain analyst occasionally queues already-pruned TFs** — minor cycle waste, not blocking.
5. **Cluster cap counting both directions** — confirmed intentional 2026-05-20 (direction-agnostic, conservative).

---

## ⏭️ Next Actions (in priority order)

1. **Tonight 22:00 UTC** — daily WF cron tries to fire. Currently the manual WF (PID 3095719, started 13:21 UTC) is occupying the flock — daily cron will skip. Manual run IS the test.
2. **Tomorrow ~07:00 UTC** — manual WF completes. Check `walkforward_results/<latest>/summary.json` for aggregate Sharpe/WR/PF. Should be the FIRST WF that tested the live config (Bug A) + symmetric gates (Bug B/C) + DI/SVM (Bug E) + per-pair median offset (a187ab9). Expected: meaningful improvement vs 2026-05-09 baseline (-5.12 / 47% / 0.73).
3. **Tomorrow 08:00 UTC** — first `pair_performance` Telegram with correct data since 2026-05-09 (cron `%` escape fixed today).
4. **After WF lands favorably**: execute pair-expansion runbook (12 pairs across 5 new clusters → 37 total). See `tasks/pair_addition_runbook.md`.
5. **Then**: target z-scoring fix (the proper long-bias resolution).
6. **Eventually**: Open Interest delta feature.

Phase 10 (live capital) still BLOCKED until WF passes all 4 gates OR 6-month dry-run track record. v23 has been live ~2 days; track record clock is ticking.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub
- [[CONTEXT]] — live context injected into AI prompts
- [[../CLAUDE]] — deep project background
- [[tasks/pair_addition_runbook]] — 9-step pair-addition mechanical recipe (NEW 2026-05-20)
- `scripts/brain/README.md` — brain operator cheatsheet
