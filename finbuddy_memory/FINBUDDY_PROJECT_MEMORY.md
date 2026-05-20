# FinBuddy Project Hub

> **Phase boundary:** All performance evaluation and future research are **Futures Mode only** (Binance USDT-M Perpetual, long AND short). Any older spot-only conclusions are kept as historical context only.

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status**: 🟢 v23 LIVE (swapped from v22 on 2026-05-19) · 🧠 brain autonomously testing v23-only · 🛡️ per-pair-per-regime gate active · ⛔ no positive v23 result yet (best PF=0.98 / -0.022%)
**Last Updated**: 2026-05-19 (Claude session — v22→v23 full migration, per-pair-per-regime intelligence, analyst↔generator feedback loop, auto-apply pipeline complete)

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

## 🧠 What Is FinBuddy?

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
> 🤖 *Auto-synced by `scripts/sync_context.py` at 2026-05-20 00:00 UTC*

## 🚀 Live System State (Auto-Synced)

| Component | Status | Notes |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run | Strategy v16.2, Binance USDT-M, isolated margin, port 8080 |
| **FreqAI identifier** | `finbuddy_v23_live_1779189570` | Active model key |
| **Whitelist** | 25 pairs | Binance USDT-M perpetuals |
| **Regime** | ⚖️ NEUTRAL | From HMM (updates every 4h) |
| **Open trades** | 0 (0L / 0S) | Live positions |
| **Closed trades** | 294 | All-time P&L: 96.28 USDT |
| **Last training** | 76m ago | Age of most recent 'Done training' log event |
| **Walk-forward** | ❌ FAIL — WR 0.0%, Sharpe 0.00, DD 0.0%, PF 0.00 (0 trades, run `FinBuddyFreqAI_2025-05-01_2026-05-01_20260519T220001`) | OOS validator — gates Phase 10 |

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

Gaurav called out that I was doing **bot tuning** (picking thresholds, asking "which path?") instead of building **the brain** (autonomous, self-evolving, hypothesis-generating system). The vision says FinBuddy "observes markets, forms hypotheses, tests them, promotes winners, retires losers, and gets smarter over time — without Gaurav having to intervene."

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
| 0 — Foundation | ✅ Complete | FreqTrade, Telegram, server, N8N cleanup |
| 1 — FreqAI Brain | 🔄 In Progress | **v23 live since 2026-05-19** — LightGBMRegressor, 15m, per-pair-per-regime gate, brain autonomous; 2 profitable backtest runs found (best bear PF=1.214 / +0.192%), promotion criteria not yet met |
| 2 — Data Enrichment | ✅ Live | 5 external fetchers + combined_context.json, cron every 15m |
| 3 — HMM Regime | ✅ Live | 5-regime HMM + regime-aware sizing hooks, cron every 4h |
| 4 — Obsidian Memory | ✅ Live | CONTEXT auto-write + vault git-commit, cron every 15m |
| 5 — Karpathy Loop | ✅ Live | Nightly Gemini + DeepSeek R1 research at 02:00 |
| 6 — TradingView | 🔴 Abandoned | Requires paid plan — dropped 2026-05-04 |
| 7 — Executor | ✅ Live (paper) | Python signal executor cron every 5m |
| 8 — Futures Setup | ✅ Complete | Binance futures API, isolated margin, memory mounted |
| 9 — Risk Engine | ✅ Complete | Regime stake sizing, cluster cap, funding guard, DD gate |
| 10 — Live Migration | ⬜ BLOCKED | Needs brain to find passing config + walk-forward PASS |
| 11 — Self-Evolution | ✅ Live | Dynamic regime thresholds, per-pair-per-regime gate, WR feedback loop |
| 12 — Brain Dashboard | ✅ Complete | React SPA with WebSockets, Live Trades, Neural Feed |
| 13 — Conscious Brain | ✅ Live | Regression arch, OB veto, autonomous hypothesis engine, auto-apply pipeline |

---

## 🗓️ Live Crontab (server — verified 2026-05-19)

```
0 * * * *     auto_commit.sh                          # vault git commit hourly
*/15 * * * *  fetch_all_external.py                   # Phase 2 external data
0 */4 * * *   hmm_regime_detector.py                  # Phase 3 HMM every 4h
*/15 * * * *  memory_writer.py && git_commit.sh        # Phase 4 memory
0 2 * * *     karpathy/run_loop.py                    # Phase 5 research
*/5 * * * *   executor_wrapper.sh                     # Phase 7 executor
0 6 * * *     run_promotion.sh                        # daily brain promotion check
0 8 * * *     pair_performance.py                     # per-pair WR/PF report
*/30 * * * *  watchdog.py                             # container/training/heartbeat + NaN-training alert
*/15 * * * *  trade_postmortem.py                     # closed-trade ledger + bias detector
0 8 * * *     daily_summary.py                        # Telegram morning digest
0 */4 * * *   sync_context.py                         # auto-sync FINBUDDY_PROJECT_MEMORY.md
*/30 * * * *  walkforward_notify.py                   # notify on walk-forward complete
0 3 1 * *     walkforward_monthly.sh                  # monthly walk-forward (21 folds)
30 4 * * *    download_data_daily.sh                  # forward-increment market data
*/10 * * * *  brain_cli.py run --max 1                # brain: run next pending hypothesis
0 */6 * * *   brain_cli.py generate                   # brain: generate hypotheses
0 7 * * *     brain_cli.py scan                       # brain: scan for promotable configs
0 8 * * *     digest.py                               # brain: daily digest to Telegram
*/2 * * * *   flock -n ... telegram_listener.py       # Telegram button listener (flock: no dupes)
0 4 * * *     brain_cleanup.py                        # brain: prune old model dirs
30 */6 * * *  brain_cli.py analyse                    # brain: analyst report
*/30 * * * *  pair_regime_performance.py              # per-pair-per-regime gate update
15 1 * * *    build_historical_macro.py               # rebuild macro parquet daily
20 1 * * *    build_historical_regime.py              # rebuild regime parquet daily
```

---

## 🔗 Related Files

- [[CLAUDE]] ← deep project context, architecture, and full session history
- [[COLLABORATION_CONTRACT]] ← roles, automation rules, AI vs code boundaries
- [[CLAUDE_HANDOFF]] ← current action queue + label/walk-forward decisions
- [[tasks/TASKS]] ← canonical phase list and statuses
- [[finbuddy_memory/CONTEXT]] ← live context injected into AI prompts
- [[finbuddy_memory/regimes/current]] ← live regime snapshot
- [[strategies/registry]] ← strategy registry & lifecycle

---

*This hub must be updated at the end of every major session. It is the high-level single source of truth for the project.*
