# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-27 UTC (5 improvements: WF 0-trade fix, brain queue rate, analyst 0-trade pruning, scout BEAR calibration, n_estimators aligned)  
**Branch:** `master`  
**Latest commits:** `2c69b63` 5 improvements | `b3eb3a7` bear-configs + resort | `2c6c0b2` regime-seeding | `5639d98` 4 bug fixes

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, z-scored target) |
| FreqAI identifier | `finbuddy_v23_no_median_1779447827` |
| Model features | ~530 (3 funding-rate + 3 OI incl. btc_ls_ratio + macro + regime + OHLCV lags) |
| **Pairs** | **26** (trimmed from 37 on 2026-05-24 — removed 11 zero/negative-edge pairs) |
| Leverage | Confidence-based tiers 1×/2×/3× (FALLBACK = LOW = 1×) |
| Regime | **BEAR (80% confidence)** since 2026-05-26 |
| Wallet | **1000 USDT** dry-run |
| Bot status | ✅ Up |
| live_retrain_hours | **12** |
| Per-pair-per-regime gate | ✅ Active. 3 blocks: OP/BEAR, LINK/NEUTRAL, UNI/BEAR |
| DI / SVM | DI_threshold=1.0, use_SVM_to_remove_outliers=true |
| Daily circuit breaker | ✅ ACTIVE — FREQAI_DAILY_LOSS_LIMIT=10 |

**26 active pairs:** 1000PEPE, ADA, APT, ARB, AVAX, BTC, DOT, ENA, ETH, FET, FIL, LDO, LINK, LTC, NEAR, ONDO, OP, POL, RENDER, SOL, SUI, TAO, TON, UNI, WIF, XRP

**Live env vars (in `freqtrade/.env` AND `docker-compose.yml` environment block):**
```
FREQAI_K_TP=2.0
FREQAI_K_SL=2.0
FREQAI_LONG_THRESHOLD=1.2
FREQAI_SHORT_THRESHOLD=-0.8
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

## 🧠 Brain State (2026-05-27)

| Item | Value |
|---|---|
| Execution mode | **Single-group** — all 26 pairs in one backtest per experiment (~38 min) |
| Cron | `*/15 * * * *` with `flock -n /tmp/finbuddy_brain_run.lock` |
| Completed experiments | **339** (all z-scored; 268 legacy raw-% excluded from promotion) |
| Failed experiments | **108** |
| Queue pending | **140** (66 bear-window entries at front after regime-sort) |
| Promotions fired | **0** |
| SEED thresholds | long=1.5, short=-0.8 |
| Windows | bull_2024Q1, bull_2024Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1 |
| WR gate | ≥1 bull + ≥1 bear run must have WR ≥ 50% |
| First promotion needs | ≥2 bull + ≥2 bear z-scored passing all gates |
| Queue sort | `prioritize_regime_windows()` auto-fires after every experiment (runner.py) |
| Best config found | lt=3.25, st=-3.0, K_SL=2.0, K_TP=2.0, N=1 → WR 88.9%, Sharpe 1.38 |
| **PROBLEM** | lt≥3.0 configs produce 0 trades on bear_2026Q1 (recent bear, lower amplitude) |
| **Fix** | 16 new configs with lt=2.0-2.5 specifically on bear_2025Q1 + bear_2026Q1 at queue front |

**Brain hypothesis space (2026-05-27):**
- `num_leaves`: [15, 31, 63, 127] — varied ✅
- `learning_rate`: [0.01, 0.03, 0.05] — varied ✅
- `n_estimators`: 100 (was 200; A/B gate in progress)
- Two-tier scout active: ~15-min 6-pair pre-filter before full run
- `btc_ls_ratio` feature: IMPLEMENTED in strategy (line ~1008)
- `FREQAI_DISABLE_PAIR_REGIME_GATE=1` added to all brain+WF docker runs (prevents live rolling stats from contaminating backtests)

**New brain tools (2026-05-27):**
```bash
# Regime-targeted seeding — finds top-N configs, cross-seeds missing windows, sorts queue
python3 scripts/brain/brain_cli.py seed-regime --dry-run   # preview
python3 scripts/brain/brain_cli.py seed-regime             # apply

# Manual requeue — force cross-window coverage for specific configs
python3 scripts/brain/brain_cli.py requeue <hash> [<hash> ...] [--target 2]
```

---

## 📊 Walk-Forward State (2026-05-27)

| Run | Schedule | Folds | Window | Workers | CPU |
|---|---|---|---|---|---|
| Daily | 22:00 UTC | **1** | 4mo train + 1mo test | 1 (sequential) | 512 shares |
| Deep | 18:30 UTC every 4 days | **7** | **18mo** (train=6mo, test=1mo, slide=2mo) | 1 | **256 shares** |

**Daily WF:** Regression detector only. Completes by ~03:30 UTC.  
**Deep WF:** Reduced 2026-05-26 from 27mo/21 folds → 18mo/7 folds. Covers 2024 bull + 2025 bear + recovery. Still sufficient for promotion decisions. ~35h per run.  
**Gate for Phase 10:** WR > 50%, Sharpe > 0.5, DD < 20%, PF > 1.2 across ≥3 folds (deep WF).  
**CPU shares:** Docker-native cgroup weights (256/512 vs 1024 default) — replaces `nice`/`ionice` which DON'T propagate into containers.

---

## 📞 Telegram

| Bot | Token prefix | What |
|---|---|---|
| FreqTrade native | `8557119080:` | Trade events + daily summary |
| Brain | `8051489946:` | Brain digest + promotion Apply/Skip buttons |

Listener: `*/2 * * * * flock -n /tmp/finbuddy_telegram_listener.lock telegram_listener.py`

---

## 🗓️ Live Crontab (verified 2026-05-27)

```
0 * * * *        auto_commit.sh                         # vault git commit
*/15 * * * *     fetch_all_external.py                  # Phase 2 external data
0 */4 * * *      hmm_regime_detector.py                 # Phase 3 HMM
*/15 * * * *     memory_writer.py && git_commit.sh      # Phase 4 memory
*/30 * * * *     watchdog.py                            # CPU+container+training alerts
*/15 * * * *     trade_postmortem.py                    # closed-trade ledger
0 8 * * *        daily_summary.py                       # morning Telegram digest
0 8 * * *        digest.py                              # brain digest
0 */4 * * *      sync_context.py                        # context refresh
*/30 * * * *     walkforward_notify.py (flock)          # WF PASS/FAIL Telegram
30 4 * * *       download_data_daily.sh                 # forward-increment data
*/15 * * * *     brain_cli.py run --max 1 (flock)       # brain: one experiment
0 */6 * * *      brain_cli.py generate --safe 1 --aggr 1 # brain hypothesis gen
30 */6 * * *     brain_cli.py analyse                   # brain self-diagnose + prune
0 7 * * *        brain_cli.py scan                      # promotion scan → Telegram
*/2 * * * *      telegram_listener.py (flock)           # Apply/Skip handler
0 4 * * *        brain_cleanup.py + auto_promote.py     # WF Sharpe vs baseline
*/30 * * * *     pair_regime_performance.py --quiet     # per-pair gate rolling update
15 1 * * *       build_historical_macro.py
20 1 * * *       build_historical_regime.py
25 1 * * *       build_historical_funding.py
30 1 * * *       build_historical_oi.py
0 22 * * *       walkforward_daily.sh                   # daily WF (1 fold, ~3.5h)
30 18 */4 * *    walkforward_deep.sh                    # deep WF (7 folds, 18mo, ~35h)
0 4 * * *        auto_promote.py                        # WF Sharpe alert
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
| `executor_wrapper.sh` + `executor.py` + `freqtrade_bridge.py` | **Deleted 2026-05-24** |
| OpenClaw container | **Killed 2026-05-24** |
| N8N pipeline | Permanently disabled |
| Phase 6 TradingView | Abandoned |
| Brain parallel pair-group split | **Reverted 2026-05-24** — doubled CPU |
| REMOVED PAIRS | DASH, ZEC, BCH, DOGE, AAVE, TRX, 1000SHIB, BNB, INJ, HBAR, ATOM — do NOT re-add without 3+ weeks clean data |

---

## ⬜ Open Strategic Issues — Deferred

1. **AVAX/ADA watch** — 2-week probation until June 7. If still negative edge, remove.
2. **Per-pair prediction percentile thresholds** — scales effective threshold by pair's own prediction std. `_compute_dynamic_thresholds()` in strategy. 2-3h effort, no retrain.
3. **HMM confidence-gated stake sizing** — `custom_stake_amount()` already reads `current.json`. Wire `confidence` field into stake multiplier. 1h effort.
4. **Phase 10 (live capital)** — BLOCKED until WF passes all 4 gates OR 6-month dry-run track record.
5. **Historical parquets for live-only features** — market_cap_change_24h, news_sentiment, btc_dominance need historical parquets before they can be model features (currently constant in training = harmful if added).

---

## ⚙️ Changes from 2026-05-27 Improvement Session (commit `2c69b63`)

| Fix | What changed |
|---|---|
| WF 0-trade root cause | `walk_forward.py` no longer forwards `FINBUDDY_RECENT_WR` to WF containers — overrides with neutral 0.55 so effective threshold stays at base level |
| Brain generate rate | Crontab: `--safe 1 --aggr 1` → `--safe 3 --aggr 6` (8 → 36 hypotheses/day; prevents queue starvation) |
| Analyst 0-trade pruning | `analyst.py` Phase 0.5: reads log for (lt, bear_window) combos with <5 trades → blacklists + prunes from queue automatically |
| Regime-aware scout | `runner.py` BEAR pool: FET + LDO replace BNB + LINK — better bear signal representation |
| n_estimators aligned | `config.json` n=200→100; `hypothesis_gen.py` stamps n_estimators=100 in every new experiment config; `runner.py` adds n_estimators to lgbm_keys |

---

## ⏭️ Next Actions (priority order)

1. **Brain promotion path** — 66 bear-window experiments at queue front. Expect first bear pass within 1-2 days as lt=2.0-2.5 configs run on bear windows.
2. **Monitor brain tonight** — check if experiments complete without FAILED status:
   ```bash
   tail -f ~/.finbuddy/logs/brain_run.log
   ```
3. **WF tonight 22:00 UTC** — daily WF fires (1 fold). Check by morning:
   ```bash
   ls -t walkforward_results/ | head -1 | xargs -I{} cat walkforward_results/{}/summary.json
   ```
4. **n_estimators A/B gate** — Day 2: compare n=100 vs n=200 cohort Sharpe.
5. **June 7** — AVAX/ADA watch list review.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub + session history
- [[CONTEXT]] — live context (auto-updated every 4h by sync_context.py)
- [[CLAUDE]] — deep project background
- [[tasks/TASKS.md]] — master phase index
- [[tasks/phase-1-freqai-brain.md]] — strategy details + live config
- [[tasks/pair_addition_runbook]] — 9-step pair-addition recipe
- `scripts/brain/README.md` — brain operator cheatsheet
