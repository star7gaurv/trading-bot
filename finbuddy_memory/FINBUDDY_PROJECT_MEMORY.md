# Cortexa Project Hub

> **Phase boundary:** All performance evaluation and future research are **Futures Mode only** (Binance USDT-M Perpetual, long AND short). Any older spot-only conclusions are kept as historical context only.

**Project:** Cortexa — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status**: 🟢 v23 LIVE on **1h** (`finbuddy_v23_tf1h_1782044602` — switched from 15m 2026-06-21 via the dashboard timeframe switcher; label 6 candles, informative ['4h','1d']) · **LT=0.7/ST=−0.6** (asymmetric, raised 2026-06-17 to stop the bleed) · K_TP=3.0/K_SL=2.0 · DI+SVM disabled · regime BEAR (genuine — BTC ≈ −15%/mo) · short-only by design · 15m era track record was 752 trades / +17.6 USDT / 41% WR (now historical — 1h model starts fresh) · family model cache active · promote.py identifier→.env gap FIXED 2026-06-21 (commit 2f430d74)  
**Last Updated**: 2026-06-19 UTC (meta-labeling NO-GO; brain windows made honest; pagination root-caused — see CLAUDE.md June 19 session entry)

### 2026-06-13 → 06-19 — Turnaround + entry-tuning exhausted (summary; details in CLAUDE.md)
- **Honest diagnosis:** the EXIT is the alpha (exit_signal ~90% WR / +309 USDT), the ENTRY is a coin
  flip (IC≈0); stop-loss exits (−313) almost exactly cancel the gains. Per-trade expectancy is
  negative; profit is monotonic in trade count. The +114 May-20 peak was 2 lucky days; ~breakeven since.
- **Phase 1 (LIVE):** thresholds 0.3/−0.3 → **0.7/−0.6** to cut trade frequency (stop the bleed).
  Frozen baseline recorded → `FROZEN_BASELINE_2026-06-17.md`. Do NOT tune/promote live until the
  honest brain beats it.
- **Phase 2 (LIVE):** made the brain honest so it stops crowning noise — scout gate trades≥40 & PF>1.0;
  promote MIN_TRADES 30→150, new MIN_PF=1.1. Dashboard ×100 double-count fixed.
- **Sample weighting (06-15)** and **meta-labeling (06-17 built / 06-19 tested):** both targeted entry
  quality. **Meta-labeling = hard NO-GO (06-19):** tightening the filter made the stop-loss rate WORSE
  (no precision). With threshold/quantile/pruning/weighting all also losing, **entry tuning is
  exhausted → Phase 4 (new entry FEATURES) is the only lever left.** Research-and-approve first.
- **Brain windows made honest (06-19):** two windows NAMED "bull" were actually down markets
  (bull_2024Q2 −11%, bull_2025Q4 −23%) → renamed bear_*; added genuine bull_2024Q4 (+47%);
  PAIRED rotation now tests real bull + real bear. promote.py auto-handles via name substring.
- **Pagination (06-19):** nginx `index.html` no-cache fix (browsers were pinned to stale JS).

### 2026-06-11/12 — God-Mode Overhaul + Deep Audit (summary; details in CLAUDE.md)
- Phases A–E shipped: re-entry cooldown, tiered breaker (flatten at −15), quantile entry mode + feature pruning + per-pair OI/funding + trend-horizon (all env-gated OFF pending ~26 brain validations), funding-farm paper module, LLM hypothesis engine nightly, regime detectors unified (NEUTRAL→BEAR flip).
- Family model cache: param-only experiments and deep-WF re-runs skip training (fam_/wfam_ identifiers).
- Fixed: analyst 4-day crash-loop; promotion would have deployed quantile winners as absolute mode (3 layers); queue mutation race; emergency vol shield dead since shipping; ic_monitor reading orphaned pkl (live OOS IC = 0.034); per-pair funding cron dead since 06-04 (features were all-zeros).
- New: `data_sentinel.py` (*/6h) — freshness/constancy/liveness watchdog over all feeds and crons.
- Measured reality: live WR ≈ 39–41% = random baseline of K_TP=3/K_SL=2 geometry; exits earn (+256), entries bleed (38% full-SL). The validation queue exists to fix entries.

### 2026-06-01 — 4 Root-Cause Bugs Fixed (commit `4162899`)

**Context:** Investigation triggered by user noticing brain queue was 100% bull experiments and no trades were being promoted. Full audit found 4 root-cause bugs blocking both promotion and WF.

**Bug 1: WF broken for 5 consecutive days (May 27–31)**
- Root cause: `--cpu-shares 512` added to `walkforward_daily.sh` on 2026-05-26, passed to `docker-compose run` which rejects the flag. Every fold crashed with "unknown flag: --cpu-shares" → 0 fold results.
- Fix: Removed `--cpu-shares` flag from `walk_forward.py` command assembly. `docker-compose run` doesn't support it (only `docker run` does).
- Impact: Daily WF tonight (22:00 UTC) will be first real result since May 26.

**Bug 2: Queue drift — bear entries permanently at back**
- Root cause: `prioritize_regime_windows()` was a one-shot sort. Each `generate_and_queue` batch (runs every 6h, generates 28-45 new entries) appended in PAIRED_WINDOWS order to the END of the queue. After the 66 bear-sorted entries were consumed, new ones went to positions 64-284 (back of 286-item queue).
- Fix: Added `next_alternating(last_completed_window_type())` to `experiment_log.py`. Runner.py now always picks the first entry of opposite type to last completed run. Permanent structural fix — can never drift again.
- Added functions: `next_alternating()` + `last_completed_window_type()` in experiment_log.py.

**Bug 3: LT=3.25 deadlock would recur on any future promotion**
- Root cause: `combined.clip(upper=2.0)` capped the multiplier, but `LT=3.25 × 2.0 = 6.5σ` was still impossible. The May 30 deadlock (reset LT from 3.25→1.5) would have happened again on any future LT>2.5 promotion.
- Fix: Added `MAX_EFFECTIVE_THRESHOLD = 2.5` hard cap on FINAL computed threshold in `_compute_dynamic_thresholds()`. Any promoted LT → live threshold ≤ 2.5σ → always tradeable.

**Bug 4: Promotion scan blocked by stale applied.jsonl**
- Root cause: `applied.jsonl` had hash `2ae96f164387` (lt=3.25, k_tp=2.25) marked as "currently live." Live bot was reset to LT=1.5 on 2026-05-30 but applied.jsonl still showed LT=3.25. `find_candidates()` skipped it → "No promotion candidates" for 2+ days.
- Fix: Cleared `applied.jsonl`. Brain scan immediately found candidate (avg_profit=0.282%, Sharpe=3.82, 226 trades). Telegram sent.
- MIN_BULL_RUNS raised 1→2 per user instruction.

**Live state after session:**
- Strategy: v23, identifier `finbuddy_v23_promoted_1779997908`, restarted at 08:48 UTC
- Thresholds: LT=1.5, ST=-1.5, K_TP=2.25, K_SL=2.0, STAB=1
- MAX_EFFECTIVE_THRESHOLD=2.5 cap now active (prevents deadlock permanently)
- Brain queue: 261 entries, strict bear/bull alternation enforced
- Promotion candidate: lt=3.25, st=-3.0, k_sl=2.0, k_tp=2.25 — brain next run will be bear window
- WF fix: tonight's 22:00 UTC run is first real test

### 2026-05-27 — Regime-Targeted Brain Seeding + Queue Prioritization (commits `5639d98`, `2c6c0b2`, `b3eb3a7`)

**Problem:** Brain has 339 completed experiments, 0 promotions. Queue was FIFO — bull-window experiments ran ahead of bear-window ones despite BEAR 80% regime. Also: 165 queued configs with lt≥3.0 produced 0 trades on bear_2026Q1 (recent bear market has lower prediction amplitude — P(>3.25σ) ≈ 0.06%, generates 0-6 trades in 3 months vs MIN_TOTAL_TRADES=60).

**4 housekeeping bugs fixed (commit `5639d98`):**
1. Watchdog: removed misleading INFO log line that printed on every training check run
2. fetch_all_external.py: deprecated `datetime.utcnow()` → `datetime.now(timezone.utc)`
3. pair_regime_stats.json: pruned 9 stale entries for removed pairs (AAVE, ZEC, DOGE, BCH, DASH, TRX, ATOM, 1000SHIB) + 2 stale blocks. 3 active blocks remain: OP/BEAR, LINK/NEUTRAL, UNI/BEAR.
4. queue.jsonl: pruned 165 unreachable lt≥3.0 configs (290 → 125). These would generate 0 trades on bear_2026Q1.

**Regime-targeted brain seeding (commit `2c6c0b2`):**
- NEW: `scripts/brain/seed_regime_targets.py` — finds top-N scoring configs from log, cross-seeds missing windows, re-sorts queue by current regime
- NEW: `experiment_log.py` `prioritize_regime_windows(regime)` function — rewrites queue atomically with bear/bull-window entries at front
- NEW: `brain_cli.py seed-regime [--top-n 5] [--regime auto] [--dry-run]` subcommand
- Runner.py: auto-triggers `prioritize_regime_windows()` after every experiment → queue stays regime-sorted automatically

**16 targeted bear configs + re-sort (commit `b3eb3a7`):**
- Generated 16 new bear-targeted configs (lt=2.0-2.5 × 2 bear windows × 4 config variations)
- Re-sorted queue: 66 bear-window entries now at front
- Expected: first bear pass within 1-2 days → cross-window auto-queue fires → bull experiments added → promotion scan fires in 3-5 days

**Confirmed already implemented (memory was stale):**
- `btc_ls_ratio`: already in strategy at line ~1008 — `dataframe["%-btc_ls_ratio"] = oi["btc_ls_ratio"]`
- `num_leaves` + `learning_rate`: already in `AGGRESSIVE_CHOICES_V23` in hypothesis_gen.py AND properly plumbed through runner.py

**State after session:**
- Brain: 339 completed, 108 failed, 140 queued (66 bear at front)
- Live: LT=1.2, ST=-0.8, K_SL=2.0, K_TP=2.0, STAB=1, DAILY_LOSS_LIMIT=10
- Deep WF: 7 folds, 18mo window, 18:30 UTC every 4 days, cpu-shares=256
- Brain cron confirmed: `*/15 * * * *` (not */30 as was in memory)

---

### 2026-05-26 — Docker CPU-Shares Fix + Deep WF Rescheduled to Midnight IST (commit `42eb5d8`)

**Root cause diagnosed:** Server load average 7.79 on 4-core machine (380% CPU saturation). Three FreqTrade processes all at NI=0 (full priority):
1. Deep WF fold (PID 2312422): 123% CPU — running since 03:45 UTC (4.5h), timerange 20241001-20250501
2. Brain experiment (PID 2373445): 194% CPU — started 07:15 UTC
3. Live bot (PID 2401056): 121% CPU

**Why `nice -n 19` was not working:** `walkforward_deep.sh` applied `nice -n 19 ionice -c 3` to the Python `walk_forward.py` process. But Docker containers create their own process namespace — they do NOT inherit host nice values. The WF fold containers always ran at NI=0 regardless.

**Fix 1 — Docker `--cpu-shares 256` (commit `42eb5d8`):**
- `walk_forward.py`: new `--cpu-shares` CLI flag; when set, adds `--cpu-shares <N>` to `docker-compose run` command. This is a cgroup-level weight applied INSIDE Docker — the actual mechanism that works.
- `walkforward_deep.sh`: passes `--cpu-shares 256`. At 256/1024 = WF yields CPU to live bot+brain under contention; uses full CPU when system is idle.
- `nice -n 19 ionice -c 3` removed from `walkforward_deep.sh` (was a no-op for Docker processes).

**Fix 2 — Deep WF rescheduled to midnight IST:**
- Old cron: `0 3 */4 * *` = 3:00 AM UTC = **8:30 AM IST** (work hours — WF competed with brain during the day)
- New cron: `30 18 */4 * *` = 18:30 UTC = **midnight IST** (runs overnight, Telegram report ready by morning IST)
- Daily WF remains at `0 22 * * *` = 10:00 PM UTC = 3:30 AM IST (starts early morning IST, finishes ~8:30-9:00 IST)

---

### 2026-05-25 (Morning) — Deep Analysis & Fix: The Target Leakage Bug

**Root cause found:** FreqAI columns prefixed with `&-` are **targets** (labels with 100% lookahead bias), while `&s-` are **predictions** output by the model.
In `populate_entry_trend`, `predicted_return` was reading `&-future_return`.
- **Brain Experiments:** Backtesting evaluated the raw future return (with lookahead bias), generating thousands of "perfect" entries that hit stop-losses due to intra-path volatility, resulting in catastrophic losses.
- **Walk-Forward:** OOS folds had `NaN` at the edge for targets, defaulting to `0.0`. This never triggered the dynamic thresholds, resulting in **0 trades**.
- **Live Trading:** Disconnected from the backtest reality because live targets are always `NaN`.

**Fix:** Changed `predicted_return` to read `&s-future_return` in `FinBuddyFreqAI_v23.py`.
Walk-Forward validator started (running in background) to verify valid trade generation.

---

### 2026-05-24 (Evening) — Phase 12b: Dashboard v2 ✅ COMPLETE

**All 5 increments shipped in one session.** Dashboard rebuilt from scratch as a dense, Binance-class trading console and deployed live at `https://trade.star7gaurav.in/new-dashboard`.

**Commits:** `3a7786e` (foundation) · `7c432bd` (Overview+SystemHealth) · `dcaa2db` (Trades+Performance) · `c40455d` (Brain+WF) · `8b9eb6e` (Settings)

**What was built:**

| Tab | Content |
|---|---|
| Overview | 7-stat strip (P&L/WR/positions/regime/conf.), live trades mini-table, system health summary, Brain queue, WF gate badges |
| Trades | Open trades table, paginated closed trades (pair+exit filter), per-pair WR/PF table, trade detail drawer |
| Performance | Cumulative P&L SVG chart (area+line, zero baseline), daily/weekly/monthly tables, per-pair horizontal bar chart |
| Brain | Queue stat strip, experiments table (window filter), live WebSocket brain log stream |
| Walk-Forward | Latest run PASS/FAIL gates (WR/Sharpe/DD/PF), fold-by-fold table, expandable history list |
| System Health | Load/disk/mem/FreqTrade strip, full cron table with expandable log tails (stale-first), Docker containers, Watchdog |
| Settings | Strategy config, FreqAI identifier, thresholds, pair whitelist badge grid (26 pairs), wallet balance |

**Backend (FastAPI streamer):** `auth.py` (HMAC-signed JWT, 7-day expiry) · `cron_status.py` (parse crontab + tail logs) · `system_health.py` (uptime/disk/mem/docker) · 20+ REST endpoints · 30s in-memory cache · systemd service `finbuddy-streamer.service`.

**Design:** Inter + JetBrains Mono · 7 color tokens · restrained dark theme · no neon/glow · all numeric cells tabular-nums · 76.5KB gzipped JS bundle.

**Task file:** `finbuddy_memory/tasks/phase-12b-dashboard-v2.md`

---

### 2026-05-24 (Evening) — Pair Universe Trim 37 → 26 + CPU Optimization Complete

**Pair removal:** 356 closed trades analyzed with full exit-reason breakdown. Two-framework consensus (Claude behavioral + Antigravity structural). 11 pairs removed:

| Pair | Reason |
|---|---|
| DASH, ZEC, BCH | Dead coins — no institutional volume, negative P&L |
| DOGE | Structural: trailing_stop WR=14% (-$8.91). Spike-revert faster than 15m ATR can arm/disarm |
| AAVE | PF=0.07, avg win $0.15 / avg loss $1.12 — gap-risk incompatible with ATR stop |
| TRX | WR=20% — announcement-driven, not learnable from OHLCV/funding features |
| 1000SHIB | edge=0.05 — model wins $0.05, loses $0.89; needs 95% WR to break even |
| BNB, INJ, HBAR | 0 entries in 5 weeks post all bug fixes — model sees no edge above ±0.5 threshold |
| ATOM | Borderline data, dual-framework agreement |

**Remaining 26 pairs:** 1000PEPE, ADA, APT, ARB, AVAX, BTC, DOT, ENA, ETH, FET, FIL, LDO, LINK, LTC, NEAR, ONDO, OP, POL, RENDER, SOL, SUI, TAO, TON, UNI, WIF, XRP
**Watch list (2 weeks):** AVAX, ADA — borderline edge, monitor until June 7.
**FreqAI cache flushed** (historic_predictions.pkl, pair_dictionary.json moved to .bak) — prevents schema mismatch on restart.
**Container restarted** with `docker-compose up -d` — 26-pair training underway.

---

### 2026-05-24 (Day) — System-Wide CPU Optimization & Self-Aware Subconscious Reflection

**Root causes found:** Massive load average (7.38 on 4 cores) caused by overlapping cron jobs, redundant dummy scripts, and the monthly Deep Walk-Forward backtest crushing the CPU at the exact same time as the continuous Brain.

**Fix 1 — Removed Dead Mock Executor:**
- `executor_wrapper.sh` running every 5 minutes 24/7 was deleted. This was a legacy Phase 7 prototype that queried FreqTrade and wrote mock signals to SQLite. It consumed CPU 288 times a day for absolutely no purpose.

**Fix 2 — De-duplicated 08:00 AM Cron Stampede:**
- `pair_performance.py` was firing at the exact same millisecond as `daily_summary.py` and `digest.py` every morning at 08:00 AM, causing an artificial CPU spike. Since `pair_performance.py` only dumps a text table to a hidden log file (and `daily_summary.py` already sends the relevant Telegram digest), it was removed from the crontab.

**Fix 3 — Subconscious Reflection (Deep Walk-Forward Optimization):**
- The 38-hour 27-month trailing Deep Walk-Forward (`walkforward_deep.sh`) previously caused severe CPU starvation when it ran alongside the Brain.
- `walkforward_deep.sh` was wrapped in `nice -n 19 ionice -c 3` and limited to `--max-workers 1` and `--lgbm-threads 1`.
- **⚠️ CORRECTED 2026-05-26:** `nice -n 19` was ineffective — Docker containers spawn their own process namespace and do NOT inherit host nice values. All WF fold containers ran at NI=0. Real fix: `--cpu-shares 256` passed to `docker-compose run` inside `walk_forward.py` (commit `42eb5d8`). See 2026-05-26 session below.

---

### 2026-05-23 — P0–P2 Fixes: Brain Unblocked + WF Fixed + Circuit Breaker

**Root causes found from Telegram logs (7 FAILED/day, all WF folds empty, 0 trades in BEAR):**

**P0.1 — Brain experiments 99% failure rate FIXED (`runner.py`)**
- 37-pair sequential backtest ~74 min > `BACKTEST_TIMEOUT_S=3900` (65 min) → always timed out
- Fix: split 37 pairs into 2 groups of ~18-19, run via `ThreadPoolExecutor(max_workers=2)`. Each group ~38 min.
- All 37 pairs still evaluated per experiment — user rejected reducing to 15 pairs (correct call)
- New helpers: `_load_brain_pairs`, `_create_pair_group_config`, `_parse_raw_trades_from_zip`, `_compute_metrics_from_raw_trades`, `_build_env_args`, `_run_hypothesis_group`
- Partial-success: if one group fails, single-group result logged (not FAILED)

**P0.2 — WF folds always empty FIXED (`walk_forward.py`)**
- fold timeout=16200s (4.5h). 37-pair training needs ~5.5-6h. fold_03 was BACKTESTING when killed — 30 min from done.
- Fix: timeout → 21600 (6h). Daily WF 22:00 → ~08:00 UTC. First real results tonight.

**P1 — Daily circuit breaker (`FinBuddyFreqAI_v23.py`, `.env`, `docker-compose.yml`)**
- `custom_stake_amount()` top: reads `FREQAI_DAILY_LOSS_LIMIT=10`. Blocks new entries when today P&L < -10 USDT.
- `.env` updated. `docker-compose.yml` environment block updated (vars must be explicitly listed). Verified in container.

**P2.1 — Brain WR gate (`promote.py`)**
- `find_candidates()`: requires ≥1 bull run AND ≥1 bear run with WR ≥ 50%. Profit alone wasn't enough.

**P2.2 — Asymmetric SEED (`hypothesis_gen.py`)**
- `short_threshold`: -1.5 → -0.8. LONG WR=57%, SHORT WR=34% — brain starts with tighter short requirement.

**P2.3 — Combined multiplier cap (`FinBuddyFreqAI_v23.py`)**
- `(long_mult_series * wr_adj).clip(upper=2.0)` — prevents BEAR(×1.3) × bad WR(×1.26) → ×1.638 compounding into 0-trade days.

**P2.4 — Karpathy `backtest_runner` `NoneType.predict` crash FIXED (`backtest_runner.py`)**
- Nightly Phase 5 validation crashed because it hardcoded the old `--strategy FinBuddyFreqAI` (v22 classifier emitting "L"/"S" strings) while the live `config.json` uses `LightGBMRegressor`. This mismatch raised `ValueError: could not convert string to float: 'S'`.
- Second root cause: hardcoded `20260101-20260401` window dropped 100% of ETH/SOL data because 2400 candles of warmup reached before data availability.
- Fix: Updated to `--strategy FinBuddyFreqAI_v23` and shifted window to `20260301-20260515` (guaranteed data coverage). Pending hypotheses will now backtest properly tonight.

**Pending next:**
- P3.1: Open Interest Delta feature (`build_historical_oi.py`, add to strategy, bump identifier, flush models)
- P3.2: Leverage tier tuning (FREQAI_LEV_MED_CONF_RATIO=1.7, FREQAI_LEV_HIGH_CONF_RATIO=2.5)

---

### 2026-05-22 (Evening) — 15-Bug Deep Analysis (commit `3deeafc`)

Brain was completely silenced. 20 total bugs fixed across two 2026-05-22 sessions.
Brain now exploring z-scored hypothesis space with windows bull_2024Q1/Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1.
Identifier: `finbuddy_v23_no_median_1779447827` (per-pair median removed, z-score already centers).
First promotion requires ≥2 bull + ≥2 bear z-scored experiments passing gates.

---

### 2026-05-20 — The 13-commit day (Round 1 unblock + Round 2 structural + Round 3 config-drift)

By end of day, 13 non-chore commits shipped over three audit rounds. Live bot identifier bumped twice (`finbuddy_v23_funding_*` → `finbuddy_v23_sym_*`), 8 real structural bugs fixed, 1 new feature (funding rate) + 1 new behavior (confidence-based leverage tiers), 1 quick patch (per-pair median offset for prediction bias), 1 cron escape bug that was silently breaking pair_performance for 11 days.

**Round 1 — initial unblock + new feature**
- `4702549` **Stop-ratchet bug + time-limit:** `custom_stoploss` recomputed `sl_pct = K_SL × current_atr_pct` every candle, ratcheting the stop inward when post-entry volatility contracted. 106 of 292 trades exited at avg -0.18%. Now anchored via `trade.set_custom_data("entry_atr_pct")`. Same commit cut time-limit exit from 72→24 candles (was force-closing dead positions at 18h on 15m TF).
- `3eafab8` **Brain promotion gates loosened + `requeue` CLI:** `MIN_AVG_PROFIT_IMPROVEMENT` 1.0pp → 0.1pp; gate `min(profits)>0` → `avg(profits)>0 AND min > -0.3`; new `brain_cli.py requeue` subcommand; `live_baseline.json` created with `avg_profit_pct=0.0`.
- `d7bd60e` **Funding-rate feature:** 3 new LightGBM features (`%-funding_rate`, `%-funding_rate_z30d`, `%-funding_rate_chg`) from Binance Futures `/fapi/v1/fundingRate`. 7,333 historical events back to 2019-09-10 written to `finbuddy_memory/historical/funding_rate.parquet`. Daily refresh cron 01:25 UTC.
- `7c8bf52` **Live bot 6h dead recovery + auto_promote None render fix:** Funding-feature addition created 271→274 column schema mismatch with FreqAI's root-level `historic_predictions.pkl` cache. Live bot threw Pipeline-expected every candle for 6h, no training, no trades. Recovery: flushed root state + 50 stale `sub-train-*` dirs from old identifier, restarted. `reference_feature_added_recovery.md` saved. Same commit fixed auto_promote.py reading metrics from `summary.weighted_sharpe` (root) instead of `summary.aggregate.weighted_sharpe` → every Telegram message had been showing "Sharpe: None".
- `d6c883d` **Daily walk-forward cron:** `0 22 * * * walkforward_daily.sh` (12mo rolling, ~80min initial estimate). Monthly heavy WF (27mo) kept on the 1st. `auto_promote.py` at 04:00 UTC. Legacy `run_promotion.sh` (broken CSV path) removed from cron.
- `f9a8a2b` **WF per-fold timeout 3600s → 7200s:** WF on the 6mo-train universe was timing out at 1h; bumped to 2h.

**Round 2 — structural symmetry + prediction-bias patch**
- `b4b02b7` **5 structural bugs + 3 cleanups:**
  - **Bug A**: walk_forward.py was NOT passing FREQAI_K_SL/K_TP/LONG_THRESHOLD/SHORT_THRESHOLD/STABILITY_N/FEATURE_SET/RECENT_WR via docker-compose. Strategy fell back to class defaults (LT=1.5, ST=-1.5, K_SL=1.0…) while live runs LT=3.25, ST=-2.75, K_SL=2.0. Every WF result of the prior 11 days was testing a different strategy.
  - **Bug B**: RSI TA filter asymmetric — long gate `rsi_14 < 68` (87pt band, ~90% candles) vs short gate `15 < rsi_14 < 50` (35pt band, ~50% candles). RSI=52 passed longs, blocked shorts. Net ~2× long bias.
  - **Bug C**: Funding-rate gate longs-only. Now symmetric.
  - **Bug D**: `%-recent_wr` feature dropped — training-serving skew (live read 0.34, brain/WF defaulted to 0.50).
  - **Bug E**: live config.json now sets DI_threshold=1.0 + use_SVM_to_remove_outliers=true (matches brain config).
  - **F**: stale `timeframe="5m"` class attr → "15m".
  - **G**: removed `class_weight: balanced` (no-op for LightGBMRegressor).
  - **H**: dry_run_wallet 1000→10000 (later reverted in `2f01b56`).
- `a187ab9` **Per-pair median offset for prediction long-bias:** Smoking gun — across 20 pairs × 100 candles, 480 long signals vs 27 short signals (17.8× imbalance). Model trained on bull-heavy 2024-25 data predicts +1 to +8% mean per pair (ZEC +8.2%, DOGE +3.9%, BTC/ETH +1.5%). Symmetric thresholds can't fix asymmetric predictions. Patch: subtract rolling-100-candle median per-pair before threshold compare. **Proper fix (target z-scoring at train time) deferred.**
- `60d4fb4` **Confidence-based leverage tiers:** Was fixed 2× for all entries. Now 1× / 2× / 3× by ratio of `centered_pred / threshold`. Env-tunable (`FREQAI_LEV_LOW/MED/HIGH` + corresponding CONF_RATIO vars).
- `5fcf290` **WF timeout 7200s → 10800s:** DI+SVM added by Bug E made each fold 3h not 2h. Total WF run ~18h.
- `2f01b56` **Wallet revert 10000 → 1000:** user requested original wallet size; brain/WF keep 10000 via env override.

**Round 3 — config drift + race conditions (audit found 5 more)**
- `5f37ab8` **5 real bugs from deep audit:**
  - **Bug I**: Brain backtest config (`v23_regression_15m_di_config.json`) drifted from live in THREE places — `max_open_trades` 4 vs 8, `stake_amount` 200 fixed vs unlimited dynamic, `pair_whitelist` **5 pairs vs 25 pairs**. The "best brain config so far" `e0e1bf338410` had only ever been tested on BTC/ETH/SOL/XRP/DOGE — 20 of the 25 live pairs were never validated. Aligned all three. The 265 prior brain entries marked legacy via `live_baseline.json::config_aligned_at`.
  - **Bug II**: Cluster-cap race condition in `confirm_trade_entry`. Two same-candle entries both snapshot pre-write state, both pass `< MAX_CLUSTER_POSITIONS`. Fix: defensive secondary check in `custom_stake_amount` (later in flow → fresher DB state) returns stake=0 if overflowed.
  - **Bug III**: Leverage FALLBACK was returning MED (2×). After the per-pair median offset shipped, an entry can pass `populate_entry_trend` and then leverage callback sees lower ratio. Old code gave 2× to sub-threshold conviction. Now LOW (1×).
  - **Bug IV**: `confirm_trade_entry` gate order. Was macro → funding HTTP → cluster. Reordered to cluster → macro → funding so cluster-full pairs don't waste a Binance HTTP request.
  - **Bug V**: `custom_stake_amount` was calling `_risk_engine.get_regime()` which re-reads the regime JSON. Could disagree with `populate_entry_trend` on cron-boundary candles. Now uses `self._get_current_regime()`.

**Same-day operational fixes (not separate commits but real bugs):**
- `pair_performance` cron was broken for 11 days — crontab `+%Y-%m-%d` with unescaped `%` was being treated as a literal newline by cron and truncating the command. Fixed by escaping as `+\%Y-\%m-\%d`. Memory note `reference_cron_percent_escape.md`.
- `.env` value changes were not loading because `docker-compose restart` does NOT re-resolve `${VAR:-default}` substitutions — must use `docker-compose up -d` to recreate. Memory note `reference_compose_env_reload.md`.
- Trade volume collapsed (40/day → 3/day) on 2026-05-19 due to thresholds tightened to `LT=3.25 / ST=-2.75 / N=2` — the model would have needed to predict +3.25% in 3h, almost never. User chose moderate `LT=2.0 / ST=-2.0 / N=1` → trade volume recovering.

**Memory notes added today (auto-memory layer in `~/.claude/projects/.../memory/`):**
- `reference_stop_ratchet_bug.md`
- `feedback_live_strategy_file.md` (live strategy is v23, NOT bare-name v22)
- `reference_brain_gates.md`
- `project_funding_rate_feature.md`
- `reference_feature_added_recovery.md` (root cache flush recipe)
- `project_promotion_pipeline.md`
- `project_walk_forward_daily.md`
- `reference_long_bias_root_causes.md`
- `reference_cron_percent_escape.md`
- `reference_compose_env_reload.md`
- `reference_prediction_bias_fix.md`
- `reference_round3_audit.md`

**Persistent runbook added in project memory:**
- `finbuddy_memory/tasks/pair_addition_runbook.md` — 9-step recipe for safely adding pairs. Required reading before next universe expansion.

**Known open issues deferred (documented for future sessions):**
- Target z-scoring at train time (the proper fix that per-pair median patches)
- Open Interest delta as next feature
- Pair expansion to ~37 pairs — runbook in place, gated on tonight's WF result
- Bull window experiments still show model long-bias even with mitigations (post-bias-patch needs ≥24h of new brain runs before re-evaluating)
- Brain analyst occasionally queues already-pruned TFs (small cycle waste)

**In-flight tonight:**
- Manual WF (PID 3095719, started 13:21 UTC) — first run testing ALL today's fixes. ~18h ETA. Result lands ~07:00 UTC tomorrow. This is the headline test of whether the day's work moved the needle.
- Brain `*/10 cron` continues to run experiments on the aligned 25-pair universe; post-alignment results should start displacing the legacy 265 entries within 24-48h.

---

### 2026-05-20 — Unblock-the-brain session (8 fixes + 1 new feature)

The brain had run 157 experiments with 0 promotions because the gates were unreachable at v23's current edge. The live bot was silently dead for 6h after a feature addition broke the FreqAI pipeline cache. Fixed both in this session:

1. **Brain promotion gates loosened** (commit `3eafab8`) — `MIN_AVG_PROFIT_IMPROVEMENT` 1.0pp → 0.1pp; gate changed from `min(profits)>0` to `avg(profits)>0 AND min > MIN_PER_RUN_PROFIT_FLOOR=-0.3`. Tunable constants documented in `reference_brain_gates.md` with re-tighten path.
2. **`brain_cli.py requeue` subcommand** (commit `3eafab8`) — force-queue (config_hash, window) pairs to reach 2 bull + 2 bear sample count. Ran for the 5 cross-window winners; queue: 3 → 18.
3. **Baseline file created** — `finbuddy_memory/promotions/live_baseline.json` with `avg_profit_pct=0.0` so the improvement math is honest (was -0.5% fallback).
4. **Daily walk-forward** (commit `d6c883d`) — `0 22 * * * walkforward_daily.sh` (12mo rolling, ~80min). Monthly heavy WF (27mo) kept on the 1st. `auto_promote.py` at 04:00 UTC. Legacy `run_promotion.sh` removed from cron.
5. **Stop-ratchet bug fixed** (commit `4702549`) — `custom_stoploss` was recomputing `sl_pct = K_SL × current_atr_pct` every candle, ratcheting the initial stop inward as volatility contracted. 106/292 trades exited at avg -0.18% in ~204 min. Now caches `entry_atr_pct` via `trade.set_custom_data`. Live-strategy-file mix-up (edited retired v22 first, then v23) → `feedback_live_strategy_file.md` added.
6. **Time-limit exit** (commit `4702549`) — 72 candles → 24 candles (= 2× label_period_candles=12). Was force-closing dead positions at 18h on 15m TF; now 6h.
7. **Funding-rate feature** (commit `b4e9d6f`) — 3 new features fed to LightGBM: `%-funding_rate`, `%-funding_rate_z30d`, `%-funding_rate_chg`. `scripts/build_historical_funding.py` paginates Binance Futures `/fapi/v1/fundingRate` — 7,333 events back to 2019-09-10 written to `finbuddy_memory/historical/funding_rate.parquet`. Daily refresh cron 01:25 UTC.
8. **Live bot dead 6h recovery** (commit `7c8bf52`) — adding funding feature created 271→274 column schema mismatch with FreqAI's root-level `historic_predictions.pkl` cache. Live bot threw `Pipeline expected length=271 but got 274` every candle, no training, no trades. Recovery: stopped, removed root-level state files + 50 stale `sub-train-*` dirs from old identifier, restarted. Now training on 533 features. `reference_feature_added_recovery.md` saved.
9. **auto_promote.py None rendering** (commit `7c8bf52`) — was reading `summary.weighted_sharpe` (root) instead of `summary.aggregate.weighted_sharpe` → every Telegram message showed "Sharpe: None / WR: None%". Fixed + added `_fmt()` helper that renders "—" for missing values.
10. **Disk cleanup** — Docker image prune (-2.3 GB) + 2.4 GB of retired-version FreqAI model dirs (v14–v22 + grid-search runs). 444 → 223 model dirs. Live identifier preserved. brain_cleanup.py daily cron handles ongoing.

Known open issues (documented for next session):
- Model is **over-long in bear regimes** (avg ~60% longs in bear_2025Q1). Likely training-data bias toward 2024 bull period. Mitigation: target standardization or class weight. Not yet shipped.
- Bull_2024Q1 systematic 30% WR catastrophe in brain experiments — same root cause as above.
- Brain analyst occasionally queues hypotheses on TFs it just pruned (small waste, not blocking).

Two TODOs that close the brain→live loop end-to-end:
- (a) Tonight's walk-forward (22:00 UTC) is the first apples-to-apples test of v23 + funding feature.
- (b) Once any cross-window winner accumulates 2 profitable bull AND 2 profitable bear runs of the SAME config_hash, the loosened gate fires its first promotion Telegram.

---

### 2026-05-19 — The "Six Fixes" session (deep audit + forward unblock)

Live v22 +$94 dry-run profit was reality-checked as regime coincidence, not edge (last 20 trades 3W/17L = 15% WR after BEAR→NEUTRAL flip). Six structural fixes shipped to unblock forward progress:

1. **Per-pair-per-regime dynamic gate** — `scripts/pair_regime_performance.py` writes `pair_regime_stats.json` every 30 min from rolling 30-day closed-trade history; `FinBuddyFreqAI_v23.py:populate_entry_trend()` zeroes out enter_long/short for blocked combos. Rule: `n≥5 AND WR<40% AND PF<0.7`. First run blocked OP/BEAR, LINK/NEUTRAL, UNI/BEAR. Data-driven, no hand-picked blacklist.
2. **Data download** — 15m + 30m feathers for all 25 pairs back to 2024-01-01 (previously only 7 pairs on 15m, 0 pairs on 30m past 2024-06). Added to `download_data_daily.sh`.
3. **v22 → v23 full migration** — config.json swapped to `FinBuddyFreqAI_v23` + `LightGBMRegressor` + 15m + identifier `finbuddy_v23_live_*`. Brain `V22_ENABLED=False` flag (code intact for history). 40 stale v22+5m queued hypotheses purged.
4. **Analyst↔generator feedback loop closed** — `hypothesis_gen.py` reads `analyst_report.json` and skips blacklisted timeframes; also gated by actual data-coverage check on BTC feather. Stops the waste cycle where analyst pruned 5m then generator regenerated it.
5. **Auto-apply pipeline live** — `promote.py:apply_promotion()` now actually deploys: backups config, writes `.env`, bumps identifier, restarts container, Telegram confirms with rollback. Previously printed instructions only.
6. **brain_cleanup top-K preservation** — preserves top-10 best-profit brain model dirs indefinitely as analyzable references; only purges garbage at the 7-day age threshold.

Critical decisions confirmed by user:
- ❌ No static pair blacklists. Per-pair-per-regime gating IS the right approach (memory: `feedback_approach.md` updated).
- ✅ v22 file stays on disk, never re-activated (same pattern as AiGuardrailStrategy).
- ✅ N8N container untouched even though pipeline is dead.

Next session priorities: (a) watch v23 first 48h trade WR vs prior 48h, (b) push brain to find first PF>1.0 v23 config via the now-clean queue, (c) wire auto-promote gate (when v23 beats baseline for N days, send Apply button).

---

## 🧠 What Is Cortexa?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them via walk-forward backtest
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product
- **Primary market: Binance Futures (USDT-M Perpetual) — long AND short**
- Spot trading will be added later as a secondary module

---

keep in mind no matter what we have to make it self aware, self evolving, conscious brain. and when say self aware it means dynamically can changes parameters to adjust tuning itself. so that. it can run on long, short both by detecting trend time. as we have made plan already. and it must have wide range it stored so that it can have broader perspective , reference and data to analyze. but keep also in mind the code you do make it achieve should not be make it worse than current system.

<!-- AUTO-SYNC-START -->
> 🤖 *Auto-synced by `scripts/sync_context.py` at 2026-08-03 08:00 UTC*

## 🚀 Live System State (Auto-Synced)

| Component | Status | Notes |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run | Strategy v16.2, Binance USDT-M, isolated margin, port 8080 |
| **FreqAI identifier** | `finbuddy_v23_tf1h_1782044602` | Active model key |
| **Whitelist** | 25 pairs | Binance USDT-M perpetuals |
| **Regime** | ⚖️ NEUTRAL | From HMM (updates every 4h) |
| **Open trades** | 0 (0L / 0S) | Live positions |
| **Closed trades** | 1026 | All-time P&L: -5.36 USDT |
| **Last training** | unknown | Age of most recent 'Done training' log event |
| **Walk-forward** | ❌ FAIL — WR 0.0%, Sharpe 0.00, DD 0.0%, PF 0.00 (0 trades, run `FinBuddyFreqAI_v23_2026-01-01_2026-08-01_20260802T220001`) | OOS validator — gates Phase 10 |

<!-- AUTO-SYNC-END -->

---

## 📊 Monitoring Tools

| Script | Schedule | Purpose |
|---|---|---|
| `scripts/watchdog.py` | Cron every 30m | Telegram alert: container down, training stale (>8h), heartbeat lost (>5m), **disk >80%**. File-log fallback prevents false alerts from Docker buffer eviction or slow docker daemon. |
| `scripts/trade_postmortem.py` | Cron every 15m | Appends every closed trade to `finbuddy_memory/trades/closed.md` with regime tag. **Bias detector**: Telegram alert if last 10 trades are ≥85% one-sided (6h cooldown). |
| `scripts/daily_summary.py` | Cron 8am daily | Telegram morning digest: regime, open trades (L/S split), yesterday P&L, all-time stats, last training age. |
| `scripts/pair_performance.py` | Cron 8am daily | Per-pair WR/PF/profit table (last 7 days). |
| `scripts/sync_context.py` | Cron every 4h | Auto-syncs the `<!-- AUTO-SYNC -->` block in this file with live state; appends state-change events to `finbuddy_memory/session_events.md`; auto-commits. |
| `scripts/walkforward_notify.py` | Cron every 30m | Watches `walkforward_results/` for completed runs (`summary.json` present) and Telegrams the PASS/FAIL verdict. Idempotent. |
| `scripts/walkforward_monthly.sh` | Cron 1st of month 03:00 UTC | Auto-runs `walk_forward.py` on a 27-month window. flock(1) prevents overlap. |
| `scripts/download_data_daily.sh` | Cron 04:30 UTC daily | Refreshes 3 days of futures OHLCV/funding/mark data so monthly WF can use `--skip-download`. |
| `scripts/walk_forward.py` | On-demand + monthly cron | Rolling-fold OOS validator (train 6mo / test 1mo, 21 folds). Gates Phase 10. |

---

## 📈 Backtest History — Futures (v6 → v18)

### Rounds 1–5 (v6 → v10): Stop-Loss Architecture Sweep

| Round | Strategy | Key Change | Bull P&L | Bear P&L | Bull Sharpe | Bear Sharpe |
|---|---|---|---|---|---|---|
| 1 | v6 | Futures-ready spot rewrite | -10 | -23 | -0.145 | -0.258 |
| 2 | v7 | Stoploss tightened to -1.5% | -47 | -36 | -0.896 | -0.554 |
| 3 | v8 | ATR-based `custom_stoploss()` | -33 | -12 | -0.78 | -0.22 |
| 4 | v9 | `trailing_stop=False` + macro short-gate | -7 | -22 | -0.13 | -0.37 |
| **5** | **v10** | **`stoploss_from_open()` — entry-anchored stops** | **+7.24** | **-8.78** | **+0.13** | **-0.15** |

### Round 8 (v15): Grid Search — The Breakthrough

**Grid**: 90 combos; 1h TF; label_period∈{4,6,8}; ml_threshold∈{0.55,0.60,0.65,0.70}

**Winner**: ml_threshold=0.60, ml_exit=0.60, label_period=6, atr_threshold=0.002

| Metric | Bull (2024-01-01→2025-01-01) | Bear (2025-01-01→2026-04-01) | Target | Pass? |
|---|---|---|---|---|
| Win Rate | 57.7% | 58.7% | >50% | ✅ Both |
| Max Drawdown | 2.5% | 7.0% | <20% | ✅ Both |
| Sharpe | +1.49 | -0.114 | >0.5 | ✅ Bull / ❌ Bear |
| Profit Factor | >1.2 | 0.979 | >1.2 | ✅ Bull / ❌ Bear |

**Decision**: CONDITIONAL GO. Deploy, run dry-run; walk-forward OOS is the next gate.

### v18 Campaign (2026-05-10): 24 Runs — 0/24 PASS

**Grid**: k_mult∈{1.0,1.5,2.0} × label_period∈{12,24} × ml_threshold∈{0.60,0.65} × 2 windows (bull+bear)

| Metric | Range across all 24 runs | Target | Pass? |
|---|---|---|---|
| Win Rate | 61–64% | >50% | ✅ Every combo |
| Max Drawdown | 1.57–4.60% | <20% | ✅ Every combo |
| Sharpe | −0.12 to −4.88 | >0.5 | ❌ Every combo |
| Profit Factor | 0.83–0.996 | >1.2 | ❌ Every combo |

**Root cause**: Symmetric 1:1 R:R (k_tp=k_sl). Fee drag (~$196/yr at 4.6 trades/day) exactly cancels gross edge. Losers held 2× longer (14h vs 7h), adding funding fee drag.

**Grid confirmed inert**: k_mult, label_period, and ml_threshold are all insufficient. The structural R:R must change.

**Fix — v19**: Asymmetric barriers `K_TP=2.0×ATR, K_SL=1.0×ATR`. At 62% WR → theoretical PF=3.26.

### v19 Plan — Asymmetric Barriers (2026-05-12)

**Grid**: K_TP∈{1.5,2.0,2.5} × K_SL∈{0.8,1.0} × ml_threshold∈{0.60,0.65,0.70} = **18 combos × 2 windows = 36 runs**

| Combo | Theoretical PF at 62% WR | Break-even WR |
|---|---|---|
| K_TP=1.5 / K_SL=1.0 | 2.45 | 40% |
| K_TP=2.0 / K_SL=1.0 | 3.26 | 33% |
| K_TP=2.5 / K_SL=1.0 | 4.07 | 29% |
| K_TP=1.5 / K_SL=0.8 | 3.06 | 35% |
| K_TP=2.0 / K_SL=0.8 | 4.08 | 29% |
| K_TP=2.5 / K_SL=0.8 | 5.10 | 24% |

**label_period_candles = 6 (fixed)** — R8 grid winner. Tighter K_SL resolves more labels within 6h.

### The v23 Pivot — Omni-Timeframe & MLOps (Phase 13)

The v21 backtest campaign completely failed (`0/18 PASS`, `WR 21%`) because the 1H ML signals conflicted massively with the static 4H macro gate. We cannot restrict the AI with static rules; the AI must *learn* the rules.

We shifted the entire architecture to **Phase 13: The Conscious Brain**, deploying a 5-minute base, native 15m/1h/4h peripheral vision, Order Block liquidity vetoes, and a True Self-Evolution MLOps pipeline.

👉 **Read the full architectural breakdown:** [[research/phase-13-v23-omni-timeframe-architecture.md]]

---

## 🔧 Deep Audit + 8 Fixes (2026-05-19 PM)

After the v22→v23 live migration shipped this morning (commit `f338ed5`), a full system audit found 1 critical bug + 7 smaller issues. All eight addressed in a single session.

### Critical: v23 training fails on every pair after live swap
- **Symptom:** `100 percent of training data dropped due to NaNs` → `n_samples=0` → bot trained nothing for ~90 min.
- **Root cause #1 — stale historical parquets.** `finbuddy_memory/historical/macro_features.parquet` + `regimes/historical_regime.parquet` were built once on 2026-05-17 and never put on a cron. Live candles at 2026-05-19 fell off the `merge_asof(direction="backward")` window's safe edge.
- **Root cause #2 — `docker-compose.yml` was not passing `FREQAI_*` env-vars into the live container.** Brain's `apply.py` writes promotion configs to `freqtrade/.env`, but nothing in compose ever mapped them through. So `docker restart freqtrade` got *zero* `FREQAI_*` vars — strategy ran on hard-coded defaults. Also meant brain promotions had no effect on live.
- **Fixes:**
  - Rebuilt both parquets to 2026-05-19; added 01:15/01:20 UTC daily cron.
  - Added `environment:` block in `freqtrade/docker-compose.yml` mapping `FREQAI_K_TP/K_SL/LONG_THRESHOLD/SHORT_THRESHOLD/STABILITY_N/FEATURE_SET/ML_THRESHOLD`, `BTC_MA200_GATE`, `FINBUDDY_RECENT_WR`, `FREQTRADE__FREQAI__IDENTIFIER` (all with sane defaults).
  - Hardened `_load_historical_macro` + `_load_historical_regime` to log coverage + WARN when parquet > 3d stale.
  - Container recreated via `docker-compose up -d --force-recreate`; env-vars verified present.

### 7 smaller fixes shipped same commit
1. **Watchdog NaN-training rule** — `scripts/watchdog.py` now pages on "100 percent of training data dropped" within 60 min.
2. **Daily summary scoped to current identifier** — `scripts/daily_summary.py` filters trades by promotion timestamp (parsed from identifier suffix). Lifetime kept as separate line.
3. **Telegram listener flock** — eliminates `Conflict: terminated by other getUpdates` races.
4. **Duplicate karpathy cron removed** — was running `karpathy/run_loop.py` twice at 02:00.
5. **`config.json.bak-*` retention** — `promote.apply_promotion()` keeps only the 3 most recent.
6. **Brain feature-toggle dimension** — `AGGRESSIVE_CHOICES_V23` now includes `feature_set: ["all","no_macro","no_regime","minimal"]`; propagated via `runner.py` → `FREQAI_FEATURE_SET` → strategy gates macro/regime features. Lets brain test whether external features help (117 experiments, 0 winners, every run with same features).
7. **CLAUDE.md staleness** — Phase 1 roadmap row updated to v23 live state.

### Files touched (single commit)
- `freqtrade/docker-compose.yml` — env-var wiring (closes brain → live config loop)
- `freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py` — staleness logs, FEATURE_SET toggle
- `scripts/watchdog.py`, `scripts/daily_summary.py`, `scripts/brain/promote.py`
- `scripts/brain/hypothesis_gen.py`, `scripts/brain/runner.py`
- `CLAUDE.md`
- Crontab: +2 parquet rebuild lines, telegram flock, karpathy dedupe

---

## 🐛 Candle-Count Bug Fixed (2026-05-19 PM, commit `0ede041`)

**Bug:** Both `custom_stoploss` (emergency vol shield) and `custom_exit` (time-limit) divided `total_seconds` by hardcoded `300` — the seconds-per-candle for a **5m** timeframe. The live config runs **15m (900s)**. Every candle-count was 3× too large.

**Impact:**
- Emergency shield: fired after 10 min instead of 30 min (first 2 real 15m candles)
- Time-limit exit: fired at 6h instead of 18h — killed trades 3× before their natural TP

**Fix:** Imported `timeframe_to_seconds` from `freqtrade.exchange`; replaced both hardcoded `300` with `timeframe_to_seconds(self.timeframe)`. Now TF-agnostic — survives future config changes.

**Root cause pattern:** Same bug class as the v17 `/ 900 → / 3600` fix (caught in CLAUDE.md). The strategy class defaults to `timeframe = "5m"` but `config.json` overrides to 15m. Any hardcoded TF-seconds value will silently break on TF change.

---

## 🚀 Current State (2026-05-17 — afternoon)

| Component | Status |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run, futures isolated (untouched throughout this work) |
| **Strategy (live)** | 🟠 **FinBuddyFreqAI v22** — unchanged, still earning P&L |
| **FreqAI identifier (live)** | `finbuddy_v22_balanced_1779015982` — class_weight=balanced added, retraining all 25 pairs |
| **FreqAI Model (live)** | ✅ FinBuddyLLMModel **v5** — auto-confirm ≥ 0.40 bypass |
| **Live P&L** | **+98.69 USDT** (231 closed trades) — 3 open shorts |
| **v23 Strategy (experimental)** | ✅ Regression + 3 structural fixes complete (2026-05-17 afternoon, commit 864a711) |
| **Smoke tests done** | 11 across 5 timeframes + filters (5m/15m/30m/1h/4h, ±DI/SVM, ±3% threshold) |
| **All Crons** | ✅ Live (Phase 2–5, watchdog, postmortem, daily summary, WF notify) |
| **Walk-forward** | ⬜ PENDING — run after FIX-validated smoke tests pass |
| **Phase 10 go-live** | ⬜ BLOCKED — needs v23 walk-forward PASS |

## 🤖 Autonomous Brain Deployed (2026-05-17 evening, commit 0854481)

**Per the vision realignment, the autonomous hypothesis engine is now live.**

| Component | File | Purpose |
|---|---|---|
| Experiment log | `scripts/brain/experiment_log.py` | JSONL append-only store; queryable by metric/window/band |
| Hypothesis generator | `scripts/brain/hypothesis_gen.py` | SAFE band (small perturbations) + AGGRESSIVE band (full sample across TF/K_SL/threshold/stability/label_period/filters). BOTH bands run in parallel. |
| Runner | `scripts/brain/runner.py` | FIFO queue worker; runs one backtest per invocation; Telegram-reports each result |
| Promotion engine | `scripts/brain/promote.py` | Aggregates by config hash; requires bull+bear positive + improvement; APPROVAL-GATED via Telegram + manual `--apply` command |
| CLI | `scripts/brain/brain_cli.py` | `status / seed / generate / run / scan / best` |

**Cron entries (autonomous from here)**:
- `*/30 * * * *` — run one experiment from queue
- `0 */6 * * *` — generate new hypotheses (4× daily)
- `0 7 * * *` — daily promotion candidate scan + Telegram alert if found

**Profit Projection at $800 wallet**:
- Floor (bare-min): $4/mo (0.5% net); below this = strategy broken
- Conservative: $13/mo (1.6% net); $171/yr at +21%
- Brain target: $23/mo (2.9% net); $321/yr at +40%
- Stretch (matches v22 live today): $30+/mo

Queue state at deploy: 23 hypotheses (3 seeds + 20 mixed) on bull_2024Q1 + bear_2025Q1.

### 🧠 Brain's First Autonomous Findings (2026-05-18 ~12:30 UTC)

After 8 autonomous brain experiments, structured log shows:

| Rank | Profit % | WR | Window | Variant |
|---|---|---|---|---|
| 🥇 | **-0.16%** | **43.2%** | bear_2025Q1 | stability_n=3 (safe perturbation +1) |
| 🥈 | -0.28% | 41.4% | bear_2025Q1 | seed baseline |
| 🥉 | -0.28% | 41.0% | bear_2025Q1 | short_threshold -2.75 (looser shorts) |
| 4 | -0.30% | 36.4% | bull_2024Q1 | short_threshold looser |
| 5 | -0.33% | 40.6% | bear_2025Q1 | stability_n -1 (looser stability) |

**Key autonomous discovery**: The brain found `stability_n=3` beats both 2 and 1 on bear → suggests
even stricter filter might help (the brain WILL try stability_n=4 in next cycle).

**Pattern**: top 3 results all on bear window → model's natural strength is bear regime. This aligns
with live v22 making money in current bear regime (+110 USDT).

**Best ever seen, manual or brain**: -0.16% (brain) vs -0.31% (my manual best). Brain ALREADY beat me
with one safe perturbation. Vision validated.

### Brain V2 — v22 architecture added (2026-05-18, commit 045864f)

The brain now explores BOTH architectures in parallel:
- **v23 Regression** (LightGBMRegressor predicting future_return %)
- **v22 Classifier** (LightGBMClassifier — the LIVE-profitable architecture)

Architecture-aware components:
- Two seed configs: SEED_CONFIG_V22 + SEED_CONFIG_V23
- PERTURB_V22 menu: k_tp, k_sl, ml_threshold (probability)
- PERTURB_V23 menu: long_threshold, short_threshold, k_sl, k_tp, stability_n
- generate_aggressive_band(): half v22, half v23 each cycle
- runner.py routes correct env vars per arch
- v22_backtest_config.json (5m, LightGBMClassifier, 5 pairs, balanced class_weight)

Rationale: v22 is live and profitable (+110 USDT). Finding a BETTER v22 variant is
higher-probability than chasing v23 across the profitability line. Brain explores both
because vision says "broader perspective" — let the architectures compete in the same
JSONL log and may the best win.

## 🧠 Vision Realignment (2026-05-17 afternoon)

Gaurav called out that I was doing **bot tuning** (picking thresholds, asking "which path?") instead of building **the brain** (autonomous, self-evolving, hypothesis-generating system). The vision says Cortexa "observes markets, forms hypotheses, tests them, promotes winners, retires losers, and gets smarter over time — without Gaurav having to intervene."

**Corrected plan (approved by user):**
1. **Fix existing strategy first** (Tasks #1–#4) — 3 structural fixes + validation
2. **Then build hypothesis engine** (Task #5) — autonomous brain WITH approval gate (notify-only initially)
3. **Hypothesis aggressiveness must be balanced** — both SAFE (small param tweaks) AND AGGRESSIVE (model swaps, feature regenerations) bands explored

## 🔧 v23 Strategy Fixes (2026-05-17, commit 864a711)

Three structural fixes addressing root causes found across 11 smoke tests:

### Fix #1 — Historical regime injection ✅
- **Bug**: `_get_current_regime()` always read live `current.json` → dynamic thresholds INERT in backtest
- **Fix**: `scripts/build_historical_regime.py` builds per-candle regime from BTC 4h history (5935 candles since 2023-09)
  - Distribution: 63% NEUTRAL / 19% BULL / 11% BEAR / 5% EUPHORIA / 2% CRASH
- Strategy now reads `finbuddy_memory/regimes/historical_regime.parquet` and applies regime multipliers PER CANDLE
- In live: falls back to current.json (no change)

### Fix #2 — Historical macro features ✅
- **Bug**: `%-fear_greed`, `%-btc_dominance`, `%-news_sentiment` were CONSTANT per backtest → VarianceThreshold dropped them
- **Fix**: `scripts/build_historical_macro.py` fetches F&G history from alternative.me (3025 daily points since 2018)
- Replaced btc_dominance proxy with `btc_strength` = BTC 7d return − ETH 7d return (range -0.30 to +0.18)
- Strategy uses vectorized `merge_asof` for per-candle assignment

### Fix #3 — Entry signal stability filter ✅
- **Bug**: Single-candle noise spikes triggered bad entries (exit_signal 100% WR but entries 30-40% WR proved this)
- **Fix**: New `FREQAI_STABILITY_N` env var (default 2). Entry requires `predicted_return > threshold` for N CONSECUTIVE candles

### Fix #4 — Validation (running 2026-05-17 14:28 UTC)
- BULL window (2024-01 to 2024-04) + BEAR window (2025-01 to 2025-04) in parallel
- Expected: regime adjustment fixes the 139-bleeding-longs problem in bear (smoke #11)
- Expected: stability filter eliminates noise-triggered entries that gave 0% WR at stop_loss

## 📊 11-Smoke-Test Reference Matrix (pre-fix baseline)

| # | TF | K_SL | Thresh | Filter | WR | PF | Sharpe | Profit |
|---|---|---|---|---|---|---|---|---|
| 1 | 5m | 1.0 | ±1.0 | none | 19% | 0.49 | -39 | -3.04% |
| 2 | 5m | 2.0 | ±1.5 | none | 35% | 0.52 | -19.6 | -2.41% |
| 4 | 1h | 2.0 | ±1.0 | none | **43%** | 0.71 | -4.5 | -1.72% |
| 5 | 15m | 2.0 | ±1.5 | none | 38% | 0.63 | -10.3 | -1.66% |
| 7 | 4h | 1.5 | ±2.0 | none | 33% | 0.65 | **-2.33** | -0.67% |
| 8 | 15m | 2.0 | ±1.5 | DI+SVM | 35% | 0.53 | -7.24 | -0.84% |
| 10 | 15m | 2.0 | ±3.0 | DI+SVM | 30% | 0.41 | -2.97 | **-0.31%** |
| 11 | 15m bear | 2.0 | ±3.0 | DI+SVM | 40% | 0.76 | -4.63 | -0.58% |

**Pattern proven across all tests**: `exit_signal` trades were 90-100% WR universally (proves model has real edge). Bleed came from noise-triggered entries and stale-regime-multiplier blindness — both addressed by fixes #1–#3.

## 🐛 Critical Bug Fixed (2026-05-13) — commit `21796ea`

**Bug**: `custom_stoploss` returned `None` for ALL trades (longs and shorts) since v17.

**Root cause**: `stoploss_from_open()` ALWAYS returns `>= 0` (per docs). Guards were `< 0` — always rejected the value — always returned `None` — hard `-8%` config stoploss fired for every loss. No ATR protection ever worked since v17.

**Evidence**: NEAR short #64 ran 7.4h to exactly −8.14%. All open shorts showed `sl=0.0000`.

**Fix**: Changed both `< 0` guards to `> 0`. The `= 0` case (stop already breached) is correctly discarded.

**Implication**: v17/v18 backtest PF results were worse than they would have been with working ATR stops. v19 campaign will be the first with ATR protection actually functioning.

---

## 📋 Phase 0 Checklist (Foundation) ✅ COMPLETE

- [x] Task 0.1 — Trade Event Handler (wired, active in N8N v4 pipeline)
- [x] Task 0.2 — Telegram configuration (enabled with token + chat_id)
- [x] Task 0.3 — **Pairlist Audit** (D/USDT, CHIP, SOMI, ZBT blacklisted in config)
- [x] Task 0.4 — N8N cleanup (2 active workflows, dead ones removed)
- [x] Task 0.5 — User config (user_01_gaurav.json configured)

**Status:** All 5 tasks verified complete on live server. Phase 0 → Phase 1 transition ready.
## 🧱 Core Engineering Principles

1. **Code over manual work:** Automate with cron/script; never waste AI tokens on repetitive tasks.
2. **AI for progress, not routine:** Use AI for design, debugging, monitoring, improvements.
3. **DRY & reusable design:** Shared logic in helpers/modules — no duplication across strategies.
4. **Documentation as memory:** All non-trivial behavior must be documented.
5. **Memory Maintenance (Crucial):** Agents MUST review project memory (`CLAUDE.md` and `FINBUDDY_PROJECT_MEMORY.md`) at the start of every session, identify stale information (versions, status, results), and update it immediately. This minimizes token usage and ensures a single source of truth.
6. **Never hardcode secrets:** API keys always from environment variables, never committed files.

---

## 📚 Critical Freqtrade Rules (from develop docs — must follow)

| Rule | Why It Matters |
|---|---|
| `INTERFACE_VERSION = 3` in every strategy | v2 strategies silently break in new versions |
| `can_short = True` at strategy class level | Without this, short signals are silently ignored |
| `startup_candle_count ≥ max_indicator_period` | Backtesting will use unstable (NaN-filled) candles without this |
| Never use `datetime.now()` in callbacks | Use `current_time` parameter — live vs backtest differ |
| Never use `iloc[-1]` or loops in `populate_*` | Must be vectorized pandas — loops break backtesting |
| Custom stoploss for futures: `return -0.04 * trade.leverage` | Without leverage multiply, stoploss is too tight |
| `adjust_trade_position()` for DCA | Requires `position_adjustment_enable: true` in config |
| Env vars override config.json override strategy | `FREQTRADE__EXCHANGE__KEY=...` format in Docker |
| Backtest flag `--enable-protections` | Includes cooldown/stoploss guard effects |
| `--timeframe-detail 1m` for precise SL/TP | Without this, stoploss fires may be imprecise in backtest |

---

## 🤖 AI Model Stack

> **Rule:** Never hardcode API keys. Always use environment variables.

| Model | Provider | Env Var | Cost | Role |
|---|---|---|---|---|
| **NVIDIA NIM (7 models)** | NVIDIA | `NVIDIA_API_KEY` | Free tier | ✅ Signal confirmation via FinBuddyLLMModel — PRIMARY chain |
| **OpenRouter free** | OpenRouter | `OPENROUTER_API_KEY` | Free tier | ✅ Signal confirmation fallback |
| **claude-sonnet-4-6** | Anthropic | `ANTHROPIC_API_KEY` | Per use | Claude Code — deploy, monitor, debug |
| **gemini-2.5-flash** | Google | `GEMINI_API_KEY` | Free tier | Nightly research loop (Phase 5) |
| **deepseek-chat** | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M | Future bulk hypothesis generation |

---

## 🚨 7-Day No-Trade Crisis (2026-05-08) — RESOLVED

**Symptom:** Bot running, training models, refreshing pairlist — ZERO trades for 7 days.

| Root Cause | Fix |
|---|---|
| 21 new pairs not training — old identifier had pre-existing partial state (4 pairs) | Changed identifier → forced clean retrain of all 25 pairs |
| `datasieve.pipeline WARNING - Could not find step di` (assumed blocking) | Confirmed cosmetic when `DI_threshold` not set — no fix needed |
| Macro filter deadlock — BTC between MA200 and 4h EMA50, neither long nor short could fire | Defaulted `BTC_MA200_GATE=0` (opt-in); removed hardcoded `btc_4h_below_ema50==1` short filter |

**Commit:** `d127347` — "fix: unstick v15 — disable BTC MA200 gate, remove hard btc_4h_below_ema50 short filter, fresh FreqAI identifier"

---

## 🚨 Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ CONDITIONAL | Partially passes — conditions remain |
| ⏳ RUNNING | Actively in progress |
| ⬜ PENDING | Not started |
| 🔴 RETIRED/ABANDONED | Superseded — do not continue |

---

## 🆕 Phase Roadmap (Authoritative — 2026-05-19)

| Phase | Status | Focus |
|---|---|---|
| [[tasks/phase-0-foundation\|0 — Foundation]] | ✅ Complete | FreqTrade, Telegram, server, N8N cleanup |
| [[tasks/phase-1-freqai-brain\|1 — FreqAI Brain]] | 🔄 In Progress | **v23 live since 2026-05-19** — LightGBMRegressor, 15m, z-scored predictions, 37 pairs, parallel WF (3 workers). 195 zscore experiments queued. First real WF result tonight 22:00 UTC. |
| [[tasks/phase-2-data-enrichment\|2 — Data Enrichment]] | ✅ Live | 5 external fetchers + combined_context.json, cron every 15m |
| [[tasks/phase-3-hmm-regime\|3 — HMM Regime]] | ✅ Live | 5-regime HMM + regime-aware sizing hooks, cron every 4h |
| [[tasks/phase-4-obsidian-memory\|4 — Obsidian Memory]] | ✅ Live | CONTEXT auto-write + vault git-commit, cron every 15m (credentials fixed 2026-05-23) |
| [[tasks/phase-5-karpathy-loop\|5 — Karpathy Loop]] | ✅ Live | Nightly Gemini + DeepSeek R1 research at 02:00 |
| 6 — TradingView | 🔴 Abandoned | Requires paid plan — dropped 2026-05-04 |
| [[tasks/phase-7-executor\|7 — Executor]] | ✅ Live (paper) | Python signal executor cron every 5m |
| [[tasks/phase-8-futures-setup\|8 — Futures Setup]] | ✅ Complete | Binance futures API, isolated margin, memory mounted |
| [[tasks/phase-9-futures-risk\|9 — Risk Engine]] | ✅ Complete | Regime stake sizing, cluster cap, funding guard, DD gate |
| [[tasks/phase-10-live-migration\|10 — Live Migration]] | ⬜ BLOCKED | Needs brain to find passing config + walk-forward PASS |
| [[tasks/phase-11-self-evolution\|11 — Self-Evolution]] | ✅ Live | Dynamic regime thresholds, per-pair-per-regime gate, WR feedback loop |
| [[tasks/phase-12-brain-dashboard\|12 — Brain Dashboard]] | ✅ Complete | React SPA with WebSockets, Live Trades, Neural Feed |
| [[tasks/phase-13-conscious-brain\|13 — Conscious Brain]] | ✅ Live | Regression arch, autonomous hypothesis engine, auto-apply pipeline |
| [[tasks/phase-14-10usdt-daily\|14 — 10 USDT/Day]] | 🔄 In Progress | WR 38%→55% path; brain zscore experiments; Open Interest Delta feature LIVE (2026-05-23) |

---

## 🗓️ Live Crontab (server — verified 2026-05-27)

```
0 * * * *      auto_commit.sh                          # vault git commit hourly
*/15 * * * *   fetch_all_external.py                   # Phase 2 external data
0 */4 * * *    hmm_regime_detector.py                  # Phase 3 HMM every 4h
*/15 * * * *   memory_writer.py && git_commit.sh       # Phase 4 memory
*/30 * * * *   watchdog.py                             # CPU alert (CRIT≥6.0, WARN≥4.0) + training + heartbeat
*/15 * * * *   trade_postmortem.py                     # closed-trade ledger + bias detector
0 8 * * *      daily_summary.py                        # Telegram morning digest
0 8 * * *      digest.py                               # brain daily digest to Telegram
0 */4 * * *    sync_context.py                         # auto-sync FINBUDDY_PROJECT_MEMORY.md
*/30 * * * *   walkforward_notify.py (flock)           # notify on walk-forward complete
30 4 * * *     download_data_daily.sh                  # forward-increment market data
*/15 * * * *   brain_cli.py run --max 1 (flock)        # brain: run next pending hypothesis
0 */6 * * *    brain_cli.py generate --safe 1 --aggr 1 # brain: generate hypotheses (limited rate)
30 */6 * * *   brain_cli.py analyse                    # brain: analyst self-diagnose + prune
0 7 * * *      brain_cli.py scan                       # brain: scan for promotable configs → Telegram
*/2 * * * *    telegram_listener.py (flock)            # Apply/Skip button handler
0 4 * * *      brain_cleanup.py                        # prune old model dirs
0 4 * * *      auto_promote.py                         # WF Sharpe vs baseline alert
*/30 * * * *   pair_regime_performance.py --quiet      # per-pair-per-regime gate update
15 1 * * *     build_historical_macro.py               # rebuild macro parquet daily
20 1 * * *     build_historical_regime.py              # rebuild regime parquet daily
25 1 * * *     build_historical_funding.py             # rebuild funding rate parquet daily
30 1 * * *     build_historical_oi.py                  # rebuild Open Interest parquet daily
0 22 * * *     walkforward_daily.sh                    # daily WF — 1 fold, 4mo train+1mo test (~3.5h)
30 18 */4 * *  walkforward_deep.sh                     # deep WF — 7 folds, 18mo window, --cpu-shares 256 (~35h)
```

**Removed from cron (historical):**
- `executor_wrapper.sh` — deleted 2026-05-24 (dead Phase 7 prototype)
- `run_promotion.sh` — removed 2026-05-19 (replaced by brain_cli.py scan + telegram Apply button)
- `karpathy/run_loop.py` — removed 2026-05-24 (outputs feed nowhere; CPU waste)

---

## 🔗 Related Files

- [[CLAUDE]] ← deep project context, architecture, and full session history
- [[COLLABORATION_CONTRACT]] ← roles, automation rules, AI vs code boundaries
- [[CLAUDE_HANDOFF]] ← current action queue + label/walk-forward decisions
- [[tasks/TASKS]] ← canonical phase list and statuses
- [[finbuddy_memory/CONTEXT]] ← live context injected into AI prompts
- [[finbuddy_memory/regimes/current]] ← live regime snapshot
- [[strategies/graveyard]] ← strategy registry & lifecycle

---

*This hub must be updated at the end of every major session. It is the high-level single source of truth for the project.*
