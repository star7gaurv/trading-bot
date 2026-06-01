# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-06-01 UTC (4 root-cause bugs fixed: WF cpu-shares crash, queue drift, LT deadlock, promotion unblocked)
**Branch:** `master`
**Latest commits:** `4162899` 4-bug fix | `a4d1a68` auto-sync | `b1c94c2` memory

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, z-scored target) |
| FreqAI identifier | `finbuddy_v23_promoted_1779997908` |
| Model features | ~530 (3 funding-rate + 3 OI incl. btc_ls_ratio + macro + regime + OHLCV lags) |
| **Pairs** | **26** (trimmed 2026-05-24 — removed 11 zero/negative-edge pairs) |
| Leverage | Confidence-based tiers 1×/2×/3× (FALLBACK = LOW = 1×) |
| Regime | **BEAR (80% confidence)** |
| Wallet | **1000 USDT** dry-run |
| Bot status | ✅ Up (restarted 2026-06-01 08:48 UTC for strategy threshold cap) |
| Per-pair-per-regime gate | ✅ Active. 3 blocks: OP/BEAR, LINK/NEUTRAL, DOT/NEUTRAL, AVAX/NEUTRAL |
| DI / SVM | DI_threshold=1.0, use_SVM_to_remove_outliers=true, svm_nu=0.05 |
| Daily circuit breaker | ✅ ACTIVE — FREQAI_DAILY_LOSS_LIMIT=10 |
| MAX_EFFECTIVE_THRESHOLD | **2.5σ** — hard cap on dynamic threshold (NEW 2026-06-01) |

**26 active pairs:** 1000PEPE, ADA, APT, ARB, AVAX, BTC, DOT, ENA, ETH, FET, FIL, LDO, LINK, LTC, NEAR, ONDO, OP, POL, RENDER, SOL, SUI, TAO, TON, UNI, WIF, XRP

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

⚠️ **IMPORTANT:** `docker-compose.yml` has an explicit `environment:` block — every new `.env` var MUST also be added there, or the container never sees it. `docker-compose restart` does NOT reload `.env` — always use `docker-compose up -d freqtrade`.

---

## 📊 Live Performance (2026-06-01)

| Metric | Value | Target |
|---|---|---|
| Closed trades | 475 | — |
| Win rate | 37.9% | > 50% ❌ |
| Total P&L | +43.14 USDT | — |
| Current strategy WR (since 2026-05-28) | 44% (25 trades) | > 50% ❌ |

---

## 🧠 Brain State (2026-06-01)

| Item | Value |
|---|---|
| Execution mode | **Single-group** — all 26 pairs in one backtest (~38 min) |
| Cron | `*/10 * * * *` with `flock -n /tmp/finbuddy_brain_run.lock` |
| Completed experiments | **380** total (102 z-scored, 278 legacy raw-%) |
| Failed | **115** |
| Scout-failed | **259** |
| Queue pending | **261** |
| Z-score profitable | **12** |
| Promotions fired | **1** (2026-05-28, now reverted to LT=1.5; applied.jsonl cleared 2026-06-01) |
| SEED thresholds | ±1.5 |
| Windows | bull_2024Q1, bull_2024Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1 |
| **Queue interleaving** | ✅ FIXED 2026-06-01 — `next_alternating()` in runner.py enforces bear/bull alternation |
| **Promotion gates** | MIN_BULL=**2**, MIN_BEAR=1, BEAR_2026Q1_REQUIRED (WR≥50%) |
| **Promotion candidate** | lt=3.25, st=-3.0, k_sl=2.0, k_tp=2.25 (avg_profit=0.282%, Sharpe=3.82, 226 trades) |
| **Gate blocking promotion** | bear_2026Q1 never tested for this config — brain will test it next (alternating ensures bear next) |
| Best z-scored configs | lt=4.0 WR=69.2% Sharpe=7.38 (bear_2025Q1) / lt=3.25 WR=61.4% Sharpe=5.99 (bear_2025Q1) |

**Key fixes shipped 2026-06-01 (commit `4162899`):**
1. **WF cpu-shares crash** — `docker-compose run` rejects `--cpu-shares`; removed from walk_forward.py. WF was silently failing all folds for 5 days.
2. **Queue bear/bull drift** — added `next_alternating()` + `last_completed_window_type()` to experiment_log.py; runner.py now picks opposite type of last completed run. Permanent fix.
3. **LT=3.25 deadlock** — added `MAX_EFFECTIVE_THRESHOLD=2.5` cap to `_compute_dynamic_thresholds()`. Previous `clip(upper=2.0)` capped the multiplier only; LT=3.25×2.0=6.5σ was still impossible. Now any promoted LT is safe.
4. **Promotion unblocked** — cleared `applied.jsonl` (was marking best config as "already live" when live bot had been reset to LT=1.5). Brain scan immediately found candidate; Telegram sent.

---

## 📊 Walk-Forward State (2026-06-01)

| Run | Schedule | Folds | Window | Workers |
|---|---|---|---|---|
| Daily | 22:00 UTC | 1 | 4mo train + 1mo test | 1 (sequential) |
| Deep | 18:30 UTC every 4 days | 7 | 18mo (train=6mo, test=1mo, slide=2mo) | 1 |

**CRITICAL: WF has been returning 0 folds since 2026-05-27.** Root cause: `--cpu-shares 512/256` passed to `docker-compose run` which rejects the flag → fold crashes with "unknown flag: --cpu-shares". Fixed today (2026-06-01). Tonight's WF at 22:00 UTC will be the first real result in 5 days.

**Gate for Phase 10:** WR > 50%, Sharpe > 0.5, DD < 20%, PF > 1.2 across ≥3 deep WF folds.

---

## 📞 Telegram

| Bot | Token prefix | What |
|---|---|---|
| FreqTrade native | `8557119080:` | Trade events + daily summary |
| Brain | `8051489946:` | Brain digest + promotion Apply/Skip buttons |

Listener: `*/2 * * * * flock -n /tmp/finbuddy_telegram_listener.lock telegram_listener.py`

---

## 🗓️ Live Crontab (verified 2026-06-01)

```
0 * * * *        auto_commit.sh                         # vault git commit
*/15 * * * *     fetch_all_external.py                  # Phase 2 external data
0 */4 * * *      hmm_regime_detector.py                 # Phase 3 HMM
*/15 * * * *     memory_writer.py && git_commit.sh      # Phase 4 memory
*/30 * * * *     watchdog.py                            # CPU+container+training alerts (CRIT≥6.0, WARN≥4.0)
*/15 * * * *     trade_postmortem.py                    # closed-trade ledger
0 8 * * *        daily_summary.py                       # morning Telegram digest
0 8 * * *        digest.py                              # brain daily digest
0 */4 * * *      sync_context.py                        # context refresh
*/30 * * * *     walkforward_notify.py (flock)          # WF PASS/FAIL Telegram
30 4 * * *       download_data_daily.sh                 # forward-increment data
*/10 * * * *     brain_cli.py run --max 1 (flock)       # brain: one experiment every 10min
0 */6 * * *      brain_cli.py generate --safe 3 --aggr 6 # brain hypothesis gen (36/day)
30 */6 * * *     brain_cli.py analyse                   # brain self-diagnose + prune
0 7 * * *        brain_cli.py scan                      # promotion scan → Telegram
*/2 * * * *      telegram_listener.py (flock)           # Apply/Skip handler
0 4 * * *        brain_cleanup.py                       # daily pruning
0 4 * * *        auto_promote.py                        # WF Sharpe vs baseline alert
*/30 * * * *     pair_regime_performance.py --quiet     # per-pair gate rolling update
15 1 * * *       build_historical_macro.py
20 1 * * *       build_historical_regime.py
25 1 * * *       build_historical_funding.py
30 1 * * *       build_historical_oi.py
0 22 * * *       walkforward_daily.sh                   # daily WF (1 fold, ~3.5h)
30 18 */4 * *    walkforward_deep.sh                    # deep WF (7 folds, 18mo, ~35h)
```

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
| `executor_wrapper.sh` + `executor.py` | **Deleted 2026-05-24** |
| OpenClaw container | **Killed 2026-05-24** |
| N8N pipeline | Permanently disabled |
| Phase 6 TradingView | Abandoned |
| REMOVED PAIRS | DASH, ZEC, BCH, DOGE, AAVE, TRX, 1000SHIB, BNB, INJ, HBAR, ATOM |
| `--cpu-shares` in WF scripts | Removed 2026-06-01 — docker-compose run does not support this flag |

---

## ⬜ Open Strategic Issues — Deferred

1. **Promotion candidate bear_2026Q1 validation** — Brain's next experiment will be a bear window (queue fixed). If lt=3.25 config passes bear_2026Q1 WR≥50%, promotion fires automatically at 07:00 UTC.
2. **WF tonight 22:00 UTC** — First real fold result in 5 days. Watch for trades in test window.
3. **Per-pair prediction percentile thresholds** — already implemented in `_compute_dynamic_thresholds()`. Scales effective threshold by pair's own prediction std. No further action needed.
4. **HMM confidence-gated stake sizing** — `custom_stake_amount()` already reads `current.json`. Wire `confidence` field into stake multiplier. ~1h effort.
5. **Phase 10 (live capital)** — BLOCKED until WF passes all 4 gates OR 6-month dry-run track record.
6. **Historical parquets** — market_cap_change_24h, news_sentiment, btc_dominance need historical parquets before they can be model features.

---

## ⏭️ Next Actions (priority order)

1. **Tonight 22:00 UTC** — Watch daily WF result. Should produce ≥1 fold with real trades now that cpu-shares bug is fixed.
   ```bash
   cat $(ls -t walkforward_results/*/summary.json | head -1)
   ```
2. **Brain next experiment** — Will be a bear window (bear_2025Q1 at lt=3.25). If it passes → cross-window auto-queue fires → promotion bar met. Watch:
   ```bash
   tail -20 ~/.finbuddy/logs/brain_run.log
   ```
3. **If Telegram "APPLY REQUIRED" arrives** — The promotion candidate (lt=3.25, k_tp=2.25, k_sl=2.0) has avg_profit=0.282%, Sharpe=3.82. LT=3.25 deadlock is now impossible (2.5σ cap). SAFE TO APPLY.
4. **Deep WF** — Next run 2026-06-03 18:30 UTC (4-day cycle). Will be the first complete 7-fold run with cpu-shares fix.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub + session history
- [[CONTEXT]] — live context (auto-updated every 4h by sync_context.py)
- [[CLAUDE]] — deep project background
- [[tasks/TASKS.md]] — master phase index
- [[tasks/phase-1-freqai-brain.md]] — strategy details + live config
- `scripts/brain/README.md` — brain operator cheatsheet
