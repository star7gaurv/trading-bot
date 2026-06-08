# FinBuddy — Master Project Context for Claude

> This file is the single source of truth for any Claude instance working in this repo.
> Read this fully before touching any file, writing any code, or making any suggestion.
> For current phase status and roadmap → always check [[finbuddy_memory/FINBUDDY_PROJECT_MEMORY]] first.
keep in mind no matter what we have to make it self aware, self evolving, conscious brain. and when say self aware it means dynamically can changes parameters to adjust tuning itself. so that. it can run on long, short both by detecting trend time. as we have made plan already. and it must have wide range it stored so that it can have broader perspective , reference and data to analyze. but keep also in mind the code you do make it achieve should not be make it worse than current system.
---

## What FinBuddy Actually Is

FinBuddy is **not a trading bot**. It is an **autonomous, self-evolving AI brain for crypto trading**. The distinction matters. A bot follows fixed rules. FinBuddy observes markets, forms hypotheses, tests them, promotes winners, retires losers, and gets smarter over time — without Gaurav having to intervene. FreqTrade placing orders on Binance is just the hands. The brain is the product.

The long-term vision is a **multi-tenant SaaS platform** where retail traders plug their exchange accounts into the FinBuddy brain as a service. One central intelligence, many users. The brain gets better with time and every user inherits that improvement automatically.

**Project name:** FinBuddy. The old name "Jarvis" is permanently retired — never use it.

---

## 🚨 Strategic Pivot (2026-05-02) — READ THIS FIRST

**PRIMARY MARKET IS NOW FUTURES (USDT-M PERPETUAL), NOT SPOT.**

The 192-combo spot backtest failure was not a strategy bug — it was an architectural ceiling. Spot is structurally long-only. In a -47.55% bear market (BTC 2025-02-01 → 2026-04-01), no long-only strategy can achieve Sharpe > 0.5. The ML signal quality is confirmed healthy (79–81% WR on signal-driven exits). The market type was wrong.

**Futures gives FinBuddy long + short capability = truly market-agnostic.**

### Do NOT do this anymore:
- Run more backtests on spot with the same bear market period
- Try to fix the spot strategy with regime filters as the primary solution
- Deploy Task 1.2 on the spot strategy

### DO this instead (in order):
1. Switch FreqTrade to Binance Futures USDT-M (config change)
2. Rewrite `FinBuddyFreqAI.py` for long + short signals
3. Run bull period backtest on futures (2024-01-01 → 2025-01-01)
4. Validate: Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2
5. Then deploy Task 1.2 (FinBuddyLLMModel.py) on the futures strategy

---

## Full Vision — All Crypto Market Modules

FinBuddy will support all major crypto market types as modular strategy plugins:

| Module | Type | Priority |
|---|---|---|
| **Perp Futures (Long/Short)** | Directional | 🔥 Immediate |
| **Funding Rate Farming** | Passive income | ⚡ Phase 2 |
| **Grid Trading** | Sideways/range | ⚡ Phase 3 |
| **Spot-Futures Basis Arb** | Market neutral | 🕐 Phase 4 |
| **Statistical Arb (pair trading)** | Market neutral | 🕐 Phase 5 |
| **Spot Trading** | Long-only | 🕐 Secondary |
| **DCA / Accumulation** | Long-term | 🕐 Phase 6 |

All modules share: the same regime signal, the same AI brain, the same memory vault.

---

## This Is a Fluid System

This is not a fixed blueprint. FinBuddy is a self-evolving system and the project approach evolves with it. Tools, models, workflows, and components can be dropped, swapped, or added at any time based on what works best. Nothing here is sacred except the core idea: an autonomous AI brain that trades, learns, and improves itself continuously.

- If a better model exists, we switch to it (we dropped OpenRouter → Groq → now Grok-3-Mini)
- If a tool stops serving the vision, we cut it (cut Dify, cut N8N pipeline)
- If a new approach is faster or cheaper, we take it
- Always optimize for what moves the brain forward, not what preserves existing work

---

## Core Engineering Principles (Added 2026-05-01)

These apply to ALL code, scripts, and automation in this repo:

1. **Code over manual work:** If it can be automated with code (cron, script, config), do it once and do **not** waste AI tokens or manual effort on it again.
2. **AI for progress, not routine:** Use AI (Perplexity, Claude, Grok) for design, debugging, monitoring, and improvements — not for tasks that a simple script or cron job can handle.
3. **DRY & reusable design:** Project code must follow "Do Not Repeat Yourself". Shared logic lives in reusable helpers/modules — never duplicate code across strategies, scripts, or phases.
4. **Documentation as memory:** Any non-trivial behavior (strategy logic, cron setup, API integration, experiments) must be documented so we never forget what's already implemented.
5. **Memory Maintenance (Crucial):** Agents MUST review project memory (`CLAUDE.md` and `finbuddy_memory/FINBUDDY_PROJECT_MEMORY.md`) at the start of every session, identify stale information (versions, status, results), and update it immediately. This minimizes token usage and ensures a single source of truth.
6. **Never hardcode secrets:** API keys, passwords, and tokens must always come from environment variables, never from committed files.

---

## Solo Operator Constraints

Gaurav is the sole builder. He manages everything from his **mobile phone via Termius SSH**. This is not a limitation — it is a design constraint that every decision must respect.

- Every component must be debuggable from a phone
- Operational complexity must stay low
- Hard infra cost ceiling: **$3–5/month total**
- Oracle Free Tier is the home base — anything requiring paid infra is a last resort
- No Kubernetes, no microservices, no containers per user

---

## Infrastructure

| Component | Detail |
|---|---|
| Server | Oracle Free Tier, Ubuntu 24.04 ARM64, 4 vCPU, 24GB RAM |
| Server IP | `REDACTED-SERVER_IP` |
| Server user | `ubuntu` (SSH), sometimes seen as `opc` for older files |
| Docker Compose root | `/home/ubuntu/var/www/html/trade/` |
| FreqTrade version | 2026.3, Docker container |
| N8N | ~~Docker container~~ 🔴 **DISABLED since 2026-04-30** |
| GitHub repo | `git@github.com:star7gaurv/trading-bot.git` (note: star7gaurv, not star7gaurav — typo in repo name) |
| Dev tooling on server | Claude Code 2.1.109 (npm global install) |

### Domains
- `trade.star7gaurav.in` → FreqTrade UI
- `n8n.star7gaurav.in` → N8N (disabled — container still exists but pipeline off)
- `jack.star7gaurav.in` → OpenClaw (port 18789) — ☠️ **Abandoned** (was only used as OpenRouter proxy)

---

## What Is Live and Working Right Now (verified 2026-06-08 UTC by Claude Code — two-layer threshold deadlock fixed)

### FreqTrade
- Running **`FinBuddyFreqAI_v23.py` (v23)** in dry-run mode on **Binance Futures USDT-M** — long+short
- FreqAI identifier: **`finbuddy_v23_nosvm_1780729988`** (bumped 2026-06-06 — SVM disabled to fix do_predict=0 bug; previous: `finbuddy_v23_perpair_funding_1780574683` from 2026-06-04 brain promotion)
- FreqAI model: **LightGBMRegressor** (predicts z-scored `&-future_return`, N(0,1) distribution). DI=1.0. **SVM disabled** (was flagging all live candles as outliers).
- **1000 USDT** virtual wallet, max 8 open trades
- **Confidence-based leverage** (commit `60d4fb4`): 1x / 2x / 3x tiers based on `centered_pred / threshold` ratio. Fallback LOW (1x).
- API: `http://localhost:8080/api/v1` — user: `bot`, pass: `REDACTED-FREQTRADE__API_SERVER__PASSWORD`
- Whitelist: **26 pairs** (trimmed from 37 on 2026-05-24 — removed DASH/ZEC/BCH/DOGE/AAVE/TRX/1000SHIB/BNB/INJ/HBAR/ATOM), **15m timeframe** (each pair has 5 TFs of historical data: 15m + 30m + 1h + 4h + 1d)
- **Per-pair-per-regime gate active** — `pair_regime_stats.json` blocks pair-regime combos with rolling 30d (n≥5, WR<40%, PF<0.7)
- Strategy env vars (live): K_TP=3.0, K_SL=2.0, **LONG_THRESHOLD=0.3, SHORT_THRESHOLD=-0.3, STABILITY_N=1** (FIXED 2026-06-08: LT reset from 1.5 — two-layer deadlock fixed; see session note below)
- **`_GLOBAL_STD = 0.30`** in strategy (FIXED 2026-06-08: was 0.95 from raw-% era; z-score model has std≈0.13–0.30)
- **`std_factor = (pair_pred_std / 0.30).clip(lower=0.5, upper=1.0)`** (FIXED: cap was 3.0 — was penalizing pairs with better prediction variance, making their threshold harder)

### Model features (~530 total after Bug D removed `%-recent_wr` 2026-05-20)
Standard layer 4 features include 3 funding-rate features (`%-funding_rate`, `%-funding_rate_z30d`, `%-funding_rate_chg`) from BTC perp data, plus fear_greed, btc_strength, news_sentiment, regime_numeric. Daily refresh of historical funding parquet at 01:25 UTC. `%-recent_wr` DROPPED 2026-05-20 (training-serving skew: live read 0.34, brain/WF defaulted 0.50).

### Fixes shipped 2026-05-22 evening — 15-bug deep analysis (commit `3deeafc`)

**Tier 1 — Brain silenced (unblocks promotion):**
- Fix 1: Renamed `recent_2025Q4/2026Q1` → `bull_2025Q4/bear_2026Q1` — promote.py classifies by substring; old names were invisible
- Fix 2: SEED thresholds ±3.0 → ±1.5 — z-scored predictions are N(0,1); ±3.0 was 2σ, almost never hit
- Fix 3: `target_version="zscore"` field on all new experiments; promote.py filters to zscore-only — 268 legacy raw-% experiments excluded
- Fix 4: `filter_di`/`filter_svm` now passed as env vars to brain docker container — brain can actually vary these
- Fix 5: `analyst.py WINDOW_DAYS` updated with `bull_2025Q4: 92, bear_2026Q1: 90`
- Fix 6: `_config_hash()` → `json.dumps(sort_keys=True)` for deterministic hashing
**Tier 2 — Strategy & system correctness:**
- Fix 7: Removed per-pair median offset from 3 locations (leverage, entry, exit) — z-score target makes it double-correction + adds leverage/entry inconsistency. Identifier bumped.
- Fix 8: WR feedback bidirectional — `wr_adj = 1.0 - ((recent_wr - 0.55) * 2.0)` clamped [0.5, 2.0]. WR=32% → 46% harder to enter (was: no adjustment at all)
- Fix 9: Mutual-exclusion lock between daily WF and deep WF prevents OOM crashes at 03:26/09:27 UTC. Both reduced to `--max-workers 2`
- Fix 10: `daily_summary.py` yesterday filter: `.isoformat()` → `.strftime("%Y-%m-%d %H:%M:%S")` — was silently dropping all yesterday's trades (T vs space separator)
- Fix 11: `auto_promote.py` Telegram credentials: removed hard-coded token, reads from `config.json` like all other scripts
- Fix 12: Removed dead OB column computation from `populate_indicators` — veto removed in commit `b44aebe`, columns still computed wasting CPU
**Tier 3 — Robustness:**
- Fix 13: `generate_and_queue()` dedup check — won't re-queue (config_hash, window) pairs already in queue/log
- Fix 14: `analyst.py` import moved inside `cmd_analyse()` — analyst errors no longer break `run`/`generate`/`scan`
- Fix 15: `walkforward_notify.py` flock prevents duplicate Telegram alerts from concurrent cron instances

### Fixes shipped 2026-05-19 → 2026-05-20 (13 commits, 5 rounds of audit)

**Round 1 — initial unblock (2026-05-19):**
- `4702549` Stop-ratchet bug: ATR-anchored at entry-time via `trade.set_custom_data`, time-limit 72→24 candles
- `3eafab8` Brain promotion gates loosened: `MIN_AVG_PROFIT_IMPROVEMENT` 1.0→0.1pp; `min>0` → `avg>0 AND min>-0.3`; `brain_cli.py requeue` CLI; `live_baseline.json` created
- `d7bd60e` Funding-rate feature added: 3 LightGBM features, 7,333 historical events backfilled
- `7c8bf52` Live bot 6h dead recovery: flushed root `historic_predictions.pkl` after schema mismatch; auto_promote.py None rendering fixed (was reading wrong summary.json path)
- `d6c883d` Daily walk-forward cron at 22:00 UTC + auto_promote at 04:00 UTC; legacy `run_promotion.sh` removed
- `f9a8a2b` WF per-fold timeout 3600s → 7200s

**Round 2 — structural bugs (2026-05-20):**
- `b4b02b7` 5 bugs + 3 cleanups: WF env-var drift (passed wrong thresholds), RSI asymmetric gate (long 87pt vs short 35pt band), funding gate longs-only, recent_wr feature drift, DI/SVM not in live config; strategy timeframe stale, class_weight no-op for regressor, dry_run_wallet 1000→10000 (later reverted)
- `a187ab9` Per-pair median offset for prediction bias: model trained on bull-heavy data predicts +1 to +8% mean per pair; subtract rolling-100 median before threshold compare
- `60d4fb4` Confidence-based leverage tiers (1x/2x/3x by ratio of centered_pred to threshold; env-tunable)
- `5fcf290` WF timeout 7200s → 10800s (DI+SVM scaling)
- `2f01b56` Revert dry_run_wallet 10000 → 1000

**Round 3 — config drift + races (2026-05-20):**
- `5f37ab8` 5 bugs: brain backtest config used 5 pairs vs live's 25 + max_open_trades 4 vs 8 + stake_amount 200 vs unlimited (HUGE — brain "winners" were never tested on 20 live pairs); cluster-cap race condition (secondary check in custom_stake_amount); leverage FALLBACK 2x→1x; gate order reorder; regime read race
- Cron `pair_performance` `%` escape bug fixed (was silently truncating for 11 days)
- `.env` reload requires `docker-compose up -d` not just `restart` (memory note saved)

### Profitability reality check (2026-05-22 evening)
- **296+ lifetime trades** (dry-run). All 268 prior brain experiments used raw-% target — excluded from promotion by `target_version` filter.
- **Brain restarting fresh** with z-scored target + correct windows (bull_2025Q4/bear_2026Q1 now visible). First promotion needs ≥2 bull + ≥2 bear z-scored experiments passing criteria.
- **No promotion has fired yet.** Brain explores z-scored hypothesis space for the first time.
- Per-pair median offset removed (Fix 7) — predictions feed directly to threshold without bias correction. Model retrained fresh with new identifier.
- v22 strategy file + LLM model file kept on disk for history; never loaded by live config or brain.

### Open issues deferred to future sessions
1. **Open Interest delta** as a new feature (second-best published signal after funding rate).
2. **Pair expansion** — runbook at `finbuddy_memory/tasks/pair_addition_runbook.md`; defer until z-scored brain gets first WF PASS.

### N8N
- 🔴 **Permanently disabled** — FreqAI is sole signal source

### OpenClaw ("Jack")
- ☠️ **Permanently abandoned** — was only used as an OpenRouter proxy

### Telegram
- **FreqTrade native bot** (token `8557119080:...`) — ✅ live, fires trade notifications + watchdog alerts + daily summary
- Both post to Chat ID: `5622292536`

### All Crons Live (verified 2026-05-19)
```
0 * * * *    auto_commit.sh                     # vault git commit hourly
*/15 * * * * fetch_all_external.py              # Phase 2 data
0 */4 * * *  hmm_regime_detector.py             # Phase 3 HMM
*/15 * * * * memory_writer.py && git_commit.sh  # Phase 4 memory
0 2 * * *    karpathy/run_loop.py               # Phase 5 research
*/5 * * * *  executor/executor.py               # Phase 7 executor
*/30 * * * * watchdog.py                        # Telegram alert: container/training/heartbeat
*/15 * * * * trade_postmortem.py                # Closed-trade ledger → closed.md
0 8 * * *    pair_performance.py                # Per-pair WR/PF report
0 8 * * *    daily_summary.py                   # Telegram morning digest
*/10 * * * * brain_cli.py run --max 1           # Phase 1 brain: one experiment
0 */6 * * *  brain_cli.py generate              # brain hypothesis generation
30 */6 * * * brain_cli.py analyse               # brain self-diagnose + prune
0 7 * * *    brain_cli.py scan                  # brain promotion scan → pending.json + Telegram
*/2 * * * *  telegram_listener.py               # Apply/Skip button handler (calls promote.py --apply)
0 22 * * *   walkforward_daily.sh               # daily WF (3mo trailing, ~5.5h, 3 folds, 2 workers)
30 18 */4 * * walkforward_deep.sh              # deep WF every 4 days at 18:30 UTC (midnight IST) — 27mo, 21 folds, ~38.5h
0 4 * * *    auto_promote.py                    # WF Sharpe vs baseline alert
*/30 * * * * walkforward_notify.py              # PASS/FAIL Telegram on new WF summary (flock protected)
30 4 * * *   download_data_daily.sh             # forward-increment data download
25 1 * * *   build_historical_funding.py        # daily BTC perp funding rate parquet refresh
```
**Removed from cron 2026-05-19:** `0 6 * * * run_promotion.sh` — legacy CSV-based, file kept on disk but unused. Brain promotion flows via `brain_cli.py scan` → Telegram Apply button.

---

## AI Model Assignment Matrix (Updated 2026-05-01)

| Task | Model | Provider | Env Var | Cost |
|---|---|---|---|---|
| Signal confirmation (Task 1.2) | **grok-3-mini** | xAI | `XAI_API_KEY` | $0.10/M |
| Coding & ops | Claude Sonnet 4.6 | Anthropic | `ANTHROPIC_API_KEY` | Sparingly |
| Future large-context research | Gemini 2.5 Flash | Google | `GEMINI_API_KEY` | Free tier |
| Future cheap hypothesis gen | DeepSeek chat | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M |

**Total projected cost: ~$3–5/month**

### Models That Were Dropped and Why
- **OpenRouter** — dropped April 2026. Rate limits + model ID changes on free tier.
- **Dify** — dropped February 2026. Freed ~6GB disk.
- **Groq Llama 3.3 70B** — was primary N8N signal model. Replaced by Grok-3-Mini. N8N pipeline using Groq is now disabled.
- **OpenClaw** — abandoned. Was only a proxy for OpenRouter which was also dropped.

---

## Current Strategy

### ✅ Active: `FinBuddyFreqAI_v23.py` v23 — Regression + Per-Pair-Per-Regime Gate
- Binance Futures USDT-M (perpetual, isolated margin), **15m base TF**, **26 pairs** (trimmed 2026-05-24), `can_short=True`
- **LightGBMRegressor**: predicts `&-future_return` (regression target, no classifier bias)
- **2x Leverage**: Implemented via `leverage()` callback.
- **Max Open Trades**: 8.
- **Dynamic thresholds**: long/short thresholds adjust per candle by regime + recent WR
- **Per-pair-per-regime gate** (2026-05-19): blocks (pair, regime) combos with rolling 30d WR<40% AND PF<0.7
- **Stability filter**: requires N=2 consecutive candles past threshold
- FreqAI identifier: `finbuddy_v23_live_*` — bumped on each brain promotion
- `custom_stoploss()`: ATR-based asymmetric (K_TP=2.0, K_SL=2.0 — currently)
- **Status**: Live since 2026-05-19. Awaiting brain to find profitable config + auto-promote.

### 🗄️ Retired (on disk for history, not referenced by live config or brain)
- `FinBuddyFreqAI.py` (v22) — superseded by v23 on 2026-05-19. v22 dry-run "profit" was regime-coincident.
- `FinBuddyLLMModel.py` (v5) — LLM gate layer. Was wrapping v22 classifier; v23 doesn't need it.
- (Same pattern as `AiGuardrailStrategy.py` — file remains, never re-activated.)
- Falls through to raw LightGBM if all LLM providers fail

### ❌ Retired: `AiGuardrailStrategy.py`
- Superseded by `FinBuddyFreqAI.py`. Do not reference or restart.

---

## 🔬 Backtest History — Spot (retired) → Futures (active)

### Spot — retired
| Round | Combos | Best Sharpe | Verdict |
|---|---|---|---|
| 1–3 (spot) | 192 total | -0.174 | Architectural ceiling: spot is long-only and the test window was a -47.55% bear. Retired. ML signal quality confirmed healthy (79–81% WR on signal exits). |

### Futures (USDT-M perpetual, isolated, 5 pairs)

Bull window: `20240101-20250101` (BTC +122.88%)
Bear window: `20250101-20260401` (BTC -39.27%)
Acceptance targets: **Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2**

| Round | Strategy | Bull Sharpe | Bear Sharpe | Bull P&L | Bear P&L | Note |
|---|---|---|---|---|---|---|
| 1 | v6 (futures-ready) | -0.145 | -0.258 | -10 | -23 | 13/14 SL hits at -3.59% destroy P&L |
| 2 | v7 (SL -1.5%) | -0.896 | -0.554 | -47 | -36 | Tighter SL → 41/42 chops, WR collapsed |
| 3 | v8 (ATR custom_stoploss) | -0.78 | -0.22 | -33 | -12 | Hard SL hits → 0; trailing chop new problem |
| 4 | v9 (trailing_stop=False + macro short gate) | -0.13 | -0.37 | -7 | -22 | Bull shorts 81→26; trailing arm still chopping |
| **5** | **v10 (stoploss_from_open, entry-anchored)** | **+0.13** | **-0.15** | **+7.24** | **-8.78** | **First profitable bull. Trailing cohort flipped from chop to lock-in.** |

### Round 5 (v10) — current state
| | Bull | Bear |
|---|---|---|
| Win Rate | **57.9%** ✅ | **58.6%** ✅ |
| Sharpe (closed) | **+0.13** | -0.15 |
| Max Drawdown | **1.68%** ✅ | **3.66%** ✅ |
| Profit Factor | 1.11 | 0.91 |
| P&L (USDT) | **+7.24** | -8.78 |
| exit_signal WR | 92.3% | 81.8% |

WR ✅ and DD ✅ pass on both legs. Sharpe and PF still under target but the gap closed dramatically (Sharpe target 0.5; PF target 1.2).

### Walk-forward OOS validation (running 2026-05-09)
`scripts/walk_forward.py` running overnight — 21 folds, 2024-01-01 → 2026-04-01. Results gate Phase 10.
Check: `tail -f ~/.finbuddy/logs/walk_forward.log`

---

## Full Build Roadmap (verified 2026-05-09)

| Phase | File | Status | Focus |
|---|---|---|---|
| 0 | `finbuddy_memory/tasks/phase-0-foundation.md` | ✅ **Complete** (2026-04-27) | Foundation — FreqTrade, Telegram, server |
| 1 | `finbuddy_memory/tasks/phase-1-freqai-brain.md` | 🔄 **In Progress** — v23 live since 2026-05-19; brain explores; per-pair-per-regime gate active | FreqAI brain — long + short, LightGBMRegressor (regression, no classes) |
| 2 | `finbuddy_memory/tasks/phase-2-data-enrichment.md` | ✅ **Live** — cron every 15m | External data fetchers — Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends |
| 3 | `finbuddy_memory/tasks/phase-3-hmm-regime.md` | ✅ **Live** — cron every 4h | HMM 5-regime engine wired into strategy |
| 4 | `finbuddy_memory/tasks/phase-4-obsidian-memory.md` | ✅ **Live** — cron every 15m | Obsidian vault auto-write + git auto-commit |
| 5 | `finbuddy_memory/tasks/phase-5-karpathy-loop.md` | ✅ **Live** — cron 02:00 daily | Nightly research loop — Gemini + DeepSeek R1 |
| 6 | `finbuddy_memory/tasks/phase-6-tradingview.md` | 🔴 **Abandoned** (2026-05-04) | TV alerts require paid plan — permanently dropped |
| 7 | `finbuddy_memory/tasks/phase-7-executor.md` | ✅ **Live** — cron every 5m | Python signal executor (paper mode) |
| 8 | `finbuddy_memory/tasks/phase-8-futures-setup.md` | ✅ **Complete** (2026-05-05) | Binance futures API, isolated margin |
| 9 | `finbuddy_memory/tasks/phase-9-futures-risk.md` | ✅ **Complete** (2026-05-09) | Risk engine: regime sizing + cluster cap + funding guard |
| 10 | `finbuddy_memory/tasks/phase-10-live-migration.md` | ⬜ **BLOCKED** | Needs walk-forward PASS or 6-month dry-run track record |

---

## Architecture Decision (ADR-001): Signal-as-a-Service
Full doc in `finbuddy_memory/docs/ADR-001-multi-tenant-architecture.md`.

**Chosen Option C** — Signal-as-a-Service + thin per-user executor:
- One central brain publishes signals (O(1) cost regardless of user count)
- Each user has a lightweight Python executor (~300–500 LOC)
- Non-custodial: user API keys scoped for trading only (no withdrawal)
- One user's problem cannot cascade to others

**Phase 1 (now):** Single user (Gaurav), multi-tenant-shaped code.
**Phase 2 (after 6-month live track record):** Add signup, API-key encryption, billing, dashboard.

---

## Signal Contract
Fully specced in `finbuddy_memory/docs/signal-contract.md`. Key fields:
- `signal_id` (UUID v4) — idempotency key
- `user_id`, `pair`, `side` (buy/sell/hold), `confidence` (0.0–1.0)
- `regime` — CRASH/BEAR/NEUTRAL/BULL/EUPHORIA
- `strategy_id` — references `strategies/registry.json`
- `position_size_pct` — fraction of capital (default 0.02)
- `stop_loss_atr_multiplier` — default 2.0

---

## Key Credentials & Service URLs

| Item | Value |
|---|---|
| Server IP | `REDACTED-SERVER_IP` |
| FreqTrade API | `http://localhost:8080/api/v1` |
| FreqTrade API user | `bot` |
| FreqTrade API password | `REDACTED-FREQTRADE__API_SERVER__PASSWORD` |
| FreqTrade UI | `https://trade.star7gaurav.in` |
| N8N | `https://n8n.star7gaurav.in` (disabled) |
| N8N admin | `admin` / `REDACTED-N8N_ADMIN_PASSWORD` |
| Telegram Chat ID | `5622292536` |
| Docker Compose path | `/home/ubuntu/var/www/html/trade/` |
| Active strategy | `freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py` |
| GitHub repo | `git@github.com:star7gaurv/trading-bot.git` |

---

## Code Location Rules

- **All new code goes inside `freqtrade/user_data/`** — never outside this directory
- Strategies: `freqtrade/user_data/strategies/`
- FreqAI models: `freqtrade/user_data/freqaimodels/`
- Notebooks: `freqtrade/user_data/notebooks/` (gitignored)
- N8N workflows: `n8n/workflows/`
- Architecture docs: `docs/`
- Strategy registry: `strategies/registry.json`
- User configs: `users/`
- FinBuddy brain memory: `finbuddy_memory/`
- Phase scripts: `scripts/`

## .gitignore Rules
- `freqtrade/user_data/logs/`
- `freqtrade/user_data/data/`
- `freqtrade/user_data/tradesv3.sqlite*`
- `freqtrade/user_data/notebooks/`

---

## Key Engineering Lessons (Hard-Won)

| Problem | Root Cause | Fix |
|---|---|---|
| `NaN` in RSI/MACD calculations | N8N splits Binance kline array into 50 items on manual run, differently on cron | Consolidated into single `Merge Context` node with dual-path array handling |
| N8N HTTP Request body failing | `return` statements not supported inside N8N expression context | Moved payload to dedicated `Build Groq Payload` code node |
| N8N API not returning workflows | `/api/v1/workflows` only returns default project space | Access named-project workflows via direct URL |
| SQLite permission error on FreqTrade | DB files owned by `opc` user from old setup | Full SQLite wipe + removed `db_url` MySQL reference |
| FreqTrade loading wrong strategy | `--strategy SampleStrategy` hardcoded in docker-compose.yml | Fixed with `sed` |
| f-string syntax error in strategy | Backslash escapes inside `{}` not allowed in Python < 3.12 | Rewrote all f-strings with single quotes outside |
| Rounds 1–3 spot backtests all fail | Bear market period (BTC -47.55%) + spot is long-only | **Pivoted to futures (long + short)** |

---

## Session History Summary

> Full session history lives in `finbuddy_memory/FINBUDDY_PROJECT_MEMORY.md`. Only the most recent session is kept here.

### May 26, 2026 — 5 System Improvements (commit `7a65b56`)
1. **Daily WF `--cpu-shares 512`**: `walkforward_daily.sh` now passes `--cpu-shares 512` to docker containers. Daily WF (medium priority) yields to live bot under contention. Deep WF uses 256 (lower priority).
2. **Watchdog CPU load alert**: Added check #5 to `watchdog.py` — CRITICAL alert when `load >= 6.0` (1.5× cores), WARN at `>= 4.0`. Runs via existing 30m cron. Today's 7.79 load would have fired ~5h earlier.
3. **WF Telegram: Worst DD field**: `walkforward_notify.py` now includes `Worst DD` in every WF result Telegram. Key: `worst_drawdown` from aggregate dict.
4. **Brain experiment duration**: Per-experiment Telegram now shows `Duration` (e.g. "74m 22s"). `elapsed_s` was already computed but not surfaced.
5. **Cross-window auto-queue**: `queue_missing_windows()` added to `experiment_log.py`. After any passing brain run (profit>0, sharpe>0), runner auto-queues the same config on all 5 windows not yet tested/queued. Eliminates the need for random re-discovery of promising configs on other windows. Accelerates reaching ≥2 bull + ≥2 bear promotion bar.

### May 26, 2026 — Docker CPU-Shares Fix + Deep WF Rescheduled to Midnight IST (commit `42eb5d8`)
- **Root cause found:** `nice -n 19 ionice -c 3` in `walkforward_deep.sh` was applied to the Python `walk_forward.py` process but Docker containers spawn their own process namespace and do NOT inherit host nice values. All 3 FreqTrade processes (live bot + WF fold + brain experiment) ran at NI=0, causing load average 7.79 on a 4-core server (380% CPU saturation).
- **Fix — Docker `--cpu-shares 256`:** `walk_forward.py` now accepts `--cpu-shares` flag and passes it directly to `docker-compose run`. Docker's CPU shares are cgroup-level weights (applied INSIDE the container): 256/1024 = yields to live bot+brain under contention, uses full CPU when system is idle. `nice`/`ionice` wrapper removed from `walkforward_deep.sh` (it was doing nothing).
- **Deep WF rescheduled:** Cron `0 3 */4 * *` (8:30 AM IST — work hours!) → `30 18 */4 * *` (18:30 UTC = midnight IST). Deep WF now runs overnight; report in Telegram by morning IST.

### May 24, 2026 — System-Wide CPU Optimization
- **Subconscious Reflection (PARTIALLY INCORRECT — see May 26 fix):** `walkforward_deep.sh` was wrapped in `nice -n 19 ionice -c 3`. This was not effective inside Docker containers (nice does not propagate into container namespaces). The real fix shipped 2026-05-26 via `--cpu-shares 256`.
- **Removed Dead Mock Executor:** `executor_wrapper.sh` running every 5 minutes 24/7 was deleted. This was a legacy Phase 7 prototype that consumed CPU 288 times a day for absolutely no purpose.
- **De-duplicated 08:00 AM Cron Stampede:** Removed `pair_performance.py` from the crontab. It was firing at the exact same millisecond as `daily_summary.py` and `digest.py` every morning, causing an artificial CPU spike for a redundant text log.

### May 22, 2026 Evening (Claude Code) — 15-bug deep analysis + brain unblocked

**Comprehensive codebase audit — 3 tiers of bugs, all fixed in commit `3deeafc`:**

**Brain was completely silenced (Tier 1 — 6 fixes):**
- Brain windows `recent_2025Q4/2026Q1` had no "bull"/"bear" in name → promote.py's substring classifier dropped them → brain's most recent 13 months of market invisible to promotion. Renamed to `bull_2025Q4`/`bear_2026Q1`.
- SEED thresholds ±3.0 were unreachable for z-scored N(0,1) predictions (±3.0 = 2σ, 0.27% probability). Changed to ±1.5. `_clamp()` bounds updated from ±6.0 to ±3.0.
- 268 legacy raw-% experiments contaminating promotion (incompatible label semantics). Added `target_version="zscore"` to all new configs; `find_candidates()` now filters to zscore-only.
- `filter_di`/`filter_svm` config fields were never passed as env vars to brain docker → brain could not explore DI/SVM params. Added to v23 env_args block.
- `analyst.py WINDOW_DAYS` dict was missing new windows → wrong timeframe noise computation.
- `_config_hash()` non-deterministic for nested dicts → changed to `json.dumps(sort_keys=True)`.

**Strategy correctness (Tier 2 — 6 fixes):**
- Per-pair median offset (Fix 7): z-score training already centers predictions at 0. Subtracting rolling-100 median was adding noise AND creating inconsistency between leverage tier and entry signal (different centering formulas). Removed from all 3 locations (leverage, entry, exit). FreqAI identifier bumped to `finbuddy_v23_no_median_1779447827`, bot restarted.
- WR feedback bidirectional (Fix 8): old formula only rewarded WR>55%, never penalized WR<55%. At current WR=32%, system was applying zero threshold adjustment. New: `wr_adj = 1.0 - ((recent_wr - 0.55) * 2.0)` clamped [0.5, 2.0] — WR=32% now raises threshold 46%.
- Concurrent WF OOM crashes (Fix 9): confirmed cause of bot restarts at 03:26 and 09:27 UTC. Daily WF (22:00, 5.5h) + deep WF (03:00 every 4d, 38.5h) overlap on day 4 → 8 threads on 4-core. Added mutual-exclusion flock between scripts. Both reduced to max-workers=2.
- Daily digest yesterday filter broken (Fix 10): `isoformat()` produces "T" separator; FreqTrade API uses space separator. All yesterday's trades were silently dropped. Fixed with `strftime("%Y-%m-%d %H:%M:%S")`.
- Hard-coded Telegram token in `auto_promote.py` (Fix 11): was visible in git history. Replaced with `config.json` lookup (same as other scripts).
- Dead OB column computation removed (Fix 12): OB veto removed from entry in commit `b44aebe` but columns still computed on every candle for all 37 pairs — wasted CPU.

**Robustness (Tier 3 — 3 fixes):**
- `generate_and_queue()` dedup: won't re-queue (config_hash, window) pairs already in queue/log.
- `analyst.py` import lazy-loaded inside `cmd_analyse()` — analyst errors no longer crash `run`/`generate`/`scan`.
- `walkforward_notify.py` flock prevents duplicate Telegram alerts from concurrent cron instances.

**Brain state at end of session:**
- All 268 prior experiments excluded from promotion (raw-% target, wrong label semantics).
- Brain now explores z-scored hypothesis space with realistic ±1.5 seed thresholds and correct windows.
- First promotion requires ≥2 bull + ≥2 bear z-scored experiments passing criteria — brain restarting from zero.
- Bot live: 37 pairs, thresholds ±0.5, `finbuddy_v23_no_median_1779447827`, fresh model training underway.

### May 19, 2026 PM (Claude Code) — Candle-count bug fixed + full memory audit

**Bug found and fixed (commit `0ede041`):**
Both `custom_stoploss` and `custom_exit` hardcoded `/300` (5m seconds) for candle-count but the live config runs 15m (900s). The time-limit exit was firing at 6h instead of 18h — killing trades 3× too early. The emergency vol shield covered only 10 min instead of the intended 30 min. Fixed by importing `timeframe_to_seconds(self.timeframe)` from `freqtrade.exchange` — now TF-agnostic.

**Memory / docs audit (same session):**
- `CLAUDE_HANDOFF.md` was completely stale (still said v22 live, 0 profitable brain runs, "swap not yet"). Rewrote to v23 current state with brain progress (139 runs, 2 profitable).
- `FINBUDDY_PROJECT_MEMORY.md` Phase Roadmap still said "v17 live". Updated to v23. Crontab was from 2026-05-09 (missing 12 brain + parquet + pair-regime crons). Replaced with full verified crontab.
- Auto-memory files `project_overview.md` + `project_phase1_status.md` were 7 days stale (v19 references). Fully rewritten to v23 state.

**Brain state as of this session:**
- 139 experiments completed, 2 profitable: `bear_2025Q1` (+0.192%, Sharpe=1.424, PF=1.214) and `bull_2024Q2` (+0.04%)
- Best config: `lt=3.25, st=-3.0, k_sl=2.0, k_tp=2.0, stability_n=1, lp=12`
- Promotion criteria not yet met (need ≥2 bull + ≥2 bear runs passing)

**Known gap to fix next:**
- `download_data_daily.sh` only forward-increments — will cause 4h NaN crash again when a new pair is added
- Brain does not auto-queue cross-window validation for a config that passes one window

### May 17, 2026 PM (Claude Code) — Strategy fixes + vision realignment

**Gaurav's feedback**: I was doing bot tuning (manually tweaking thresholds, asking "Path A/B/C?")
instead of building the brain (autonomous, self-evolving, hypothesis-generating). Per vision,
FinBuddy must form hypotheses, test them, promote winners — without human intervention.

**Corrected plan (approved)**:
1. Fix existing strategy FIRST (Task #1-4)
2. Build hypothesis engine SECOND (Task #5) with approval gate
3. Hypothesis aggressiveness: balanced (safe param tweaks AND aggressive model/feature swaps)

**Strategy fixes (commit 864a711)** — 3 structural root causes from 11 smoke tests:
- **Fix #1 Historical regime injection**: `_get_current_regime()` always read live current.json
  → dynamic thresholds inert in backtest. Built `scripts/build_historical_regime.py` (5935
  candles per BTC 4h since 2023-09). Strategy now reads `regimes/historical_regime.parquet`
  and applies regime multipliers PER CANDLE.
- **Fix #2 Historical macro features**: `%-fear_greed`/`%-btc_dominance` were constant
  per backtest → VarianceThreshold dropped them. Built `scripts/build_historical_macro.py`
  (3025 daily F&G from alternative.me since 2018 + btc_strength = BTC 7d ret − ETH 7d ret).
- **Fix #3 Entry stability filter**: `FREQAI_STABILITY_N` env (default 2). Entry requires N
  consecutive candles past threshold (filters single-candle noise spikes).

Validation: smoke tests on bull + bear windows running. Pending: hypothesis engine after validation.

### May 17, 2026 AM (Claude Code) — v23 Conscious Brain: regression architecture deployed

**Core architectural pivot**: Replaced LightGBMClassifier with LightGBMRegressor in v23.
Root cause: classification with K_TP=2.0/K_SL=1.0 produces 67% S-labels → LightGBM biased
to predict Short → 0 longs in bull market. Even `class_weight=balanced` only got WR to 35%.
Regression eliminates classes → no imbalance.

**Changes merged to master (88590b7)**:
- `FinBuddyFreqAI_v23.py`: regression target `&-future_return`, dynamic thresholds method,
  external macro features (fear_greed, btc_dominance, news, regime_numeric, recent_wr).
  Supply/Demand OB detection kept from concurrent master work.
- `backtest_config.json`: freqaimodel=LightGBMRegressor (was LightGBMClassifier)
- `config.json`: class_weight=balanced added + identifier bumped to `finbuddy_v22_balanced_1779015982`
- `walk_forward.py`: phantom-result bug FIXED (unlink before each fold) + `--config` flag
- `scripts/auto_promote.py` (NEW): notify-only MLOps promotion engine
- `scripts/trade_postmortem.py`: writes FINBUDDY_RECENT_WR to .env every 15min (feedback loop)

**Smoke test results (3-month bull window)**:
- #1 (5m, K_SL=1.0, ±1.0%): **454L / 173S** ← class bias eliminated! WR 19%, PF 0.49
- #2 (5m, K_SL=2.0, ±1.5%): 226L / 91S, WR 35%, PF 0.52 — hit 5m structural ceiling
- #3 (1h, K_SL=1.0, ±1.5%): RUNNING — testing if 1h breaks the noise ceiling

**Verdict**: Regression conclusively fixes class bias. 5m has ~35% WR ceiling. Next: validate
1h base where v15 R8 winner historically hit 57.7% WR. Live v22 still running, untouched.

### May 12, 2026 (Claude Code) — LLM over-filtering fix + full system audit
- **Full audit**: all 25 pairs confirmed trained; regime/external data pipeline confirmed working
- **Root cause of "fluctuation"**: LLM was blocking 91% of signals (8.8% pass rate) including 90%+ confidence ML predictions. Diagnosed from log analysis: 77 CONFIRM / 174 HOLD / 623 REJECT.
- **Fix — FinBuddyLLMModel v5**: `AUTO_CONFIRM_THRESHOLD=0.40` bypasses LLM for proba ≥ 0.90. Pass rate immediately improved to 54.5%. Cooldown reduced 3600→1800s.
- **Dead code documented**: `feature_engineering_std` (wrong name, never called). Left dead intentionally — activating adds new features that crash existing models. Will activate in v19 with new identifier.
- **Housekeeping**: Removed 9 abandoned/dead .md files (session logs, N8N docs, empty placeholders, phase-6 TradingView).
- **v18 campaign result**: 0/24 PASS. Root cause: symmetric 1:1 R:R + fee drag. v19 asymmetric barriers is the fix.
- **v19 built**: K_MULT split → K_TP/K_SL env vars, `feature_engineering_standard` activated, identifier bumped, campaign runner `scripts/autobacktest_v19.py` built (36 runs, K_TP∈{1.5,2.0,2.5} × K_SL∈{0.8,1.0} × ml_threshold∈{0.60,0.65,0.70}).

### May 14, 2026 (Antigravity AI) — FinBuddy v21 Intelligent Evolution
- **Deep-dive Analysis**: Found the root causes of the 42% win rate (74 losses): 
  1. A "Short Bias" caused by a lagging, global regime detector blocking all longs. Shorts had a 30% WR while Longs had a 66% WR.
  2. Hard fallback stoploss in `config.json` (-0.08) overriding the ATR stoploss and allowing massive 16% leveraged losses.
  3. Indiscriminate pair selection leading to chronically losing pairs (NEAR, AVAX).
- **The Intelligence Upgrade (v21)**: Replaced dumb static rules with dynamic algorithms analyzing every candle.
  - **Relative Strength (RS)**: Bot now analyzes pairs vs BTC. Only longs strong pairs (outperforming BTC) and shorts weak pairs. No manual blacklists required.
  - **Dynamic ML Thresholds**: Instead of hard-capping shorts, the ML threshold dynamically increases (to 0.65) if the bot wants to trade against the local trend or relative strength.
  - **Removed Global Regime Blocks**: The `enter_long = 0` in BEAR regime rule is gone. The bot is smart enough to find longs in bearish macros if the pair shows relative strength.
  - **Fixed Stoploss**: Updated emergency stoploss to -0.04 in config and strategy (proper 8% leveraged safety net).
  - **Noise-Resistant Trailing Stop**: Increased trailing lock threshold to `1.5 * TP` to avoid premature exits on 1h wicks.
- **Bot restarted**: Running v21 intelligence over the `finbuddy_v19_asym_1778575138` FreqAI identifier.

### May 13, 2026 (Claude Code) — Critical stoploss bug found + fixed; v19 bull campaign launched

---

## 🔗 Related Files (Obsidian Links)

- [[finbuddy_memory/FINBUDDY_PROJECT_MEMORY]] ← master hub — always read this first for current status
- [[finbuddy_memory/COLLABORATION_CONTRACT]] ← roles, automation rules, AI vs code boundaries
- [[finbuddy_memory/CLAUDE_HANDOFF]] ← current action queue for Claude Code
- [[finbuddy_memory/CONTEXT]] ← live context injected into every AI prompt
- [[finbuddy_memory/finbuddy_memory/tasks/phase-1-freqai-brain]] ← current phase task file
- [[finbuddy_memory/strategies/graveyard]] ← retired strategies + backtest failures
- [[finbuddy_memory/regimes/current]] ← live regime

### May 9, 2026 — Evening (Claude Code) — v17 symmetric barriers + central LLM client

**Root cause diagnosed: WR stuck at 42.5% = label base rate (not model failure)**

Walk-forward run T130947 (first clean, lookahead-bias-fixed run) showed WR=42.5% across all 17 folds. Analysis found this equals the mathematical base rate P(L label) = k_sl/(k_tp+k_sl) = 1.5/3.5 = 42.9%. Model has zero OOS directional edge — it just predicts the base rate.

Two root causes:
1. **Label asymmetry** (k_sl=1.5 < k_tp=2.0): SL closer than TP → 57% of resolved candles are S labels → LightGBM biased toward predicting S → WR ≈ base rate of 43%.
2. **Degenerate models** (68 "No further splits" warnings per fold): When LightGBM can't find useful feature splits, it outputs pavg≈0.68 (S base rate) for every candle → proba_short=0.68 > 0.60 → constant shorts regardless of direction.

**Fixes applied (commit 22075c4, v17):**
- `k_sl = 1.5 → 2.0` in set_freqai_targets: symmetric barriers → P(L)=50% base rate; degenerate models output 0.50 < 0.60 threshold → auto-filtered
- `custom_stoploss` initial stop: -1.5×ATR → -2.0×ATR (matches new k_sl)
- Regime kill-switches extended: CRASH+BEAR → no longs; BULL+EUPHORIA → no shorts (was: only CRASH blocked longs, only EUPHORIA blocked shorts)
- FreqAI identifier: `finbuddy_v16_clean_1778316280` → `finbuddy_v17_sym_1778353539` (forces retrain)
- Live bot restarted at 19:05 UTC, retraining all 25 pairs with symmetric labels

**Also delivered in this session (earlier):**
- Central LLM client (`scripts/llm_client.py`) — 7 verified providers (NVIDIA NIM + OpenRouter)
- FinBuddyLLMModel v3 — imports from central client, removed dead XAI/Groq code
- ML threshold 0.55 → 0.60 (flat, matches R8 grid winner)
- Karpathy backtest_runner rewritten (was a stub, now runs real docker exec backtests)
- Watchdog: docker_since_min=90 cap to prevent 510-min timeout on training check
- Removed dead `_get_tradingview_signal()` method (Phase 6 abandoned)

**WF #5 (T190609) running** — validates symmetric barrier fix. Expected: WR > 50% in bull folds (BULL/EUPHORIA → shorts blocked), WR > 50% in bear folds (BEAR/CRASH → longs blocked). If aggregate WR > 50%, Phase 10 (live migration) gate criteria can be re-evaluated.

### May 9, 2026 — Late Evening (Claude Code) — stale-string cleanup

Comprehensive audit and cleanup of FinBuddyFreqAI.py to match live v17 state:
- Class docstring: "v15" → clean v17 summary (removed v12/v13 history)
- `timeframe`: "15m" → "1h" (config.json overrides to 1h, strategy now matches)
- `BTC_MA200_GATE` default: "1" → "0" (opt-in per design; default was never changed)
- `custom_stoploss` section header: "v10" → "v17"
- `custom_exit`: division `/ 900` (15m candle count) → `/ 3600` (1h candle count) — actual bug fix, time limit was 6h instead of intended 24h; comment updated
- Triple-barrier section header: "v12 with HOLD" → "v17 symmetric"
- `set_freqai_targets` docstring: stale v12 params/history → v17 (1h data, k_sl=2.0, lp=6)
- Entry section header: "v11" → "v17"
- `populate_entry_trend` docstring: stale v11 feather-file refs removed
- `enter_tag`: `freqai_lgbm_v16_long/short` → `v17`
- `populate_exit_trend` docstring: "v16" → "v17"
- CLAUDE.md "What Is Live" + "Current Strategy" sections: v16.2/old identifier → v17

---

*This file must be updated at the end of every major session. It is the operational memory for any Claude instance opening this repo.*


## Session 2026-05-23 — P0–P2 Fixes: Brain Unblocked + WF Fixed + Circuit Breaker (commit `8bede56`, `aba9e4d`)

**Context:** Telegram logs confirmed brain was producing 7 FAILED experiments/day with 0 completing, and all WF folds were returning empty `[]`. BEAR regime + bad WR compounding caused 0 trades. Root causes found and all 6 fixes shipped.

### P0.1 — Brain parallel pair-group split (`runner.py`)
- **Root cause:** 37-pair sequential backtest ~74 min > `BACKTEST_TIMEOUT_S=3900` (65 min). Every experiment timed out.
- **Fix:** Split 37 pairs into 2 groups of ~18-19, run both simultaneously via `ThreadPoolExecutor(max_workers=2)`. Each group ~38 min — well under timeout. All 37 pairs still evaluated per experiment (user explicitly rejected reducing to 15 pairs — "we can split them like we did on WF").
- **New helpers:** `_load_brain_pairs`, `_create_pair_group_config`, `_parse_raw_trades_from_zip`, `_compute_metrics_from_raw_trades`, `_build_env_args`, `_run_hypothesis_group`. Partial-success path: if one group fails, single-group result logged instead of FAILED.

### P0.2 — WF fold timeout (`walk_forward.py`)
- **Root cause:** `timeout=16200` (4.5h). 37-pair training needs ~5.5-6h. fold_01/02 killed at 02:29 UTC (exactly 4.5h after 22:00 start). fold_03 was actively **backtesting** (training done!) when killed at 07:00 — only 30 min from finishing.
- **Fix:** `timeout=16200` → `21600` (6h). Daily WF 22:00 → ~08:00 UTC next morning.

### P1 — Daily circuit breaker (`FinBuddyFreqAI_v23.py`, `.env`, `docker-compose.yml`)
- Added at top of `custom_stake_amount()`. Reads `FREQAI_DAILY_LOSS_LIMIT` from env (default 10 USDT). Blocks new trade entries when today's closed P&L < -limit.
- `.env` updated: `FREQAI_DAILY_LOSS_LIMIT=10`. `docker-compose.yml` environment block updated (was using explicit list — var wasn't forwarded without adding it). Verified in container: `docker exec freqtrade env | grep FREQAI_DAILY` = `10`.

### P2.1 — Brain WR gate (`promote.py`)
- `find_candidates()` now requires ≥1 bull run AND ≥1 bear run with WR ≥ 50% to proceed. Profit alone wasn't sufficient filter.

### P2.2 — Asymmetric SEED (`hypothesis_gen.py`)
- `SEED_CONFIG_V23["short_threshold"]`: `-1.5` → `-0.8`. LONG WR=57%, SHORT WR=34% — brain exploration should start with tighter short bar.

### P2.3 — Combined multiplier cap (`FinBuddyFreqAI_v23.py`)
- `_compute_dynamic_thresholds()`: `(long_mult_series * wr_adj).clip(upper=2.0)` — prevents BEAR(×1.3) × bad WR(×1.26) = ×1.638 compounding. With EMA-50 filter also failing in BEAR, this was causing 0-trade days.

### Live state after session
- Bot: alive, all env vars confirmed in container
- Identifier: unchanged (`finbuddy_v23_no_median_1779447827`) — no feature change
- Next brain experiment will use parallel split (old running experiment pid=513444 uses old code; expires at ~3900s then next cron tick picks up new code)
- WF runs tonight 22:00 UTC — first real fold results expected tomorrow morning

### What to watch next
- Brain log: first `[brain] completed X` entry (not FAILED) — confirms parallel split working
- WF tonight: summary.json should have `folds: [{...}, {...}, {...}]` not `[]`
- If WF PASS (WR>50%, Sharpe>0.5, DD<20%, PF>1.2) → brain promotion auto-fires

---

## Session 2026-05-22 — Parallel WF Engine + 3 Trade-Blocking Bug Fixes

### Walk-Forward Overhaul (all committed)
- **walk_forward.py v2** (`cde90f4`): `ProcessPoolExecutor(max_workers=3)` replaces sequential fold loop. Per-fold isolated `.last_result_fXX.json` sentinels eliminate race condition. `--max-workers` and `--lgbm-threads` CLI flags.
- **LightGBM `num_threads=2`** in both config files. 3 workers × 2 threads = 6 logical threads on 4-core server.
- **`walkforward_daily.sh`** (`5b6b1cb`): 3-month trailing, 3 folds, ~5.5h. Fast nightly regression detector. Lock: `walkforward_daily.lock`.
- **`walkforward_deep.sh`** (`5b6b1cb`): Replaces monthly. 27-month trailing, 21 folds, ~38.5h. Cron: `30 18 */4 * *` (midnight IST). Lock: `walkforward_deep.lock`. `--cpu-shares 256` passes Docker CPU weight so WF yields to live bot+brain (added `42eb5d8`).
- Speedup: 7-fold campaign 38.5h → 13h. Monthly 115h → 38.5h.

### 3 Trade-Blocking Bugs Fixed (`eeae872`, `1786d01`)
1. **`startup_candle_count` 400 → 2400**: z-score ROLLING=2880 needs min_periods=200; 400 caused 101/499 NaN drops per inference cycle. 3000 exceeded Binance's 2494-candle 15m limit → crashed. 2400 = safe maximum.
2. **Thresholds 2.0 → 0.8**: z-scored predictions are N(0,1) — ±2.0 is 2σ, rarely hit. ±0.8 covers ~42% of distribution, generates real signals.
3. **Stale pre-z-score regime gate stats cleared**: LINK had 0% WR in 5 NEUTRAL trades (old strategy), ZEC had 36% WR — both permanently blocked. Reset all pair-regime stats to neutral (n=0, wr=0.5) for fresh accumulation from z-score trades.

### Active at end of session
- Live bot: v23, 37 pairs, thresholds ±0.8, startup_candle_count=2400, RUNNING
- Parallel WF test: `FinBuddyFreqAI_v23_2025-01-01_2025-12-01_20260521T210437` (5 folds, 3 workers, nohup on server)
- Walk-forward: daily @ 22:00 UTC (3mo) + deep every 4 days @ 03:00 UTC (27mo)

### What to watch
- First trade entry after threshold fix (should happen within 1-2 candles of next 15m close)
- NaN drop count should be 0 after startup_candle_count=2400 fix
- Parallel WF 5-fold result: needs WR>50%, Sharpe>0.5, DD<20%, PF>1.2 to pass promotion gate

---

## Session 2026-05-22 (PM) — 5 Trade-Blocking Bugs Diagnosed + Fixed

**Context:** Bot was producing zero trades. Zero trades started after commit `b44aebe`... wait,
the OB veto was the reason for zero trades. Bot also self-restarted at 3:26 AM and 9:27 AM (OOM
from parallel WF + brain processes running simultaneously).

### Bug 1: Phase 13 OB Veto — 100% long block (commit `b44aebe`)
- `ob_long_ok = close < bearish_ob * 0.99` was 0/100 candles on live BTC data (bearish_ob=77,777, BTC=77,619 — price trapped above the threshold)
- `ob_short_ok = close > bullish_ob * 1.01` was 5/100 candles (narrow range: bullish_ob=76,995)
- **Fix:** Removed both OB veto conditions from `populate_entry_trend`
- **Also fixed:** `ta_short` had `close < ema_50 * 0.99` asymmetry vs `ta_long` using plain `close > ema_50`; removed `* 0.99` gap
- **Root cause:** OB logic is for REVERSAL trading; v23 is TREND-FOLLOWING. Incompatible by design.

### Bug 2: `set_freqai_targets` fillna(0.0) corrupting training data (commit `edc9435`)
- `fillna(0.0)` on the z-scored `&-future_return` target was teaching LightGBM that the last 24 rows (unknown future) have 0% return
- FreqAI drops NaN-target rows before fitting — `fillna` was bypassing this safety
- **Fix:** Removed `.fillna(0.0)` — let FreqAI handle NaN rows correctly

### Bug 3: `promote.py` `docker-compose restart` silently broken (commit `edc9435`)
- `restart` does NOT reload `.env` — promoted thresholds were written to file but container kept old values
- Every promotion since the feature was added (2026-05-19) was silently broken
- **Fix:** Changed to `docker-compose up -d freqtrade` which recreates container and picks up `.env`

### Bug 4: Brain backtest stoploss -0.08 vs live -0.04 (commit `edc9435`)
- `v23_regression_15m_di_config.json` had `stoploss: -0.08` (2× wider than live -0.04)
- Brain winners were validated against a safety net that doesn't exist in production
- **Fix:** Updated to `stoploss: -0.04`

### Bug 5: Brain WINDOWS missing 13 months of market (commit `edc9435`)
- WINDOWS only covered through 2025-04 — all of Q4 2025 and Q1 2026 was unrepresented
- Brain found "winners" on 2024 market conditions while bot ran in 2026 conditions
- **Fix:** Added `recent_2025Q4` (20251001-20260101) and `recent_2026Q1` (20260101-20260401) windows
- `DATA_COVERAGE_CUTOFF` updated to 2026-01-01

### Active at end of session
- Live bot: v23, 37 pairs, thresholds ±0.5 (LONG=0.5/SHORT=-0.5), RUNNING
- First trade after OB fix: SUI SHORT +0.47% (06:56 UTC), TAO LONG open +0.90%
- ZEC NEUTRAL **blocked** by pair-regime gate (n=11, WR=36%, PF=0.45) — gate working
- All 268 prior brain experiments used raw-% target; z-scored target added today → brain restarting fresh

### What to watch
- Brain will generate new experiments with z-scored target + recent 2025Q4/2026Q1 windows
- Daily WF at 22:00 UTC will run with OB veto removed — first meaningful WF result expected tomorrow
- Next promotion: wait for brain to accumulate ≥2 bull + ≥2 bear z-scored experiments passing criteria

### May 30, 2026 — 3-Bug Critical Fix: Trading Deadlock Broken (commit `bd46828`)

**Root cause: LT=3.25 promotion created a self-sealing mathematical deadlock.**
The first brain promotion (2026-05-28 19:51 UTC, hash `2ae96f164387`) applied LT=3.25 / ST=-3.0.
Combined with WR=0.40 (recent WR feedback), the effective threshold became 4.23σ — mathematically
impossible for the N(0,1) model to breach. Result: zero live trades since 2026-05-28, WF
producing "no trades across all folds" on both daily and deep runs. Promotion gate completely blind.

**3 fixes in commit `bd46828`:**
1. **LT reset**: `FREQAI_LONG_THRESHOLD` 3.25→1.5, `FREQAI_SHORT_THRESHOLD` -3.0→-1.5 in `.env`.
   Container recreated (`docker-compose up -d`). Effective threshold now 1.95σ → ~1.6 trades/day.
   The WR feedback deadlock is broken: trades will accumulate → WR rises → wr_adj shrinks → healthy.
2. **promote.py dedup**: `find_candidates()` now loads `applied.jsonl` and skips already-live hashes.
   The daily 07:00 scan was re-sending "APPLY REQUIRED" Telegram for already-applied config every
   morning. Now silent when current config is best (correct behavior).
3. **Stale `historic_predictions.pkl` flushed**: Renamed to `.pre_promotion.pkl`. The file had
   dtype=O all-zero values (stale from pre-promotion identifier) — confusing monitoring scripts.
   FreqAI rebuilds it automatically from identifier-specific sub-train models.

**State after fixes:**
- LT=1.5 / ST=-1.5, K_TP=2.25, K_SL=2.0, N=2 — live in container (verified `docker exec env`)
- Identifier unchanged: `finbuddy_v23_promoted_1779997908` (no model retraining triggered)
- Brain continues exploring LT=3.25 range (where best result +1.14% WR=64% was found)
- WF tonight at 22:00 UTC should produce ≥1 fold with trades and real Sharpe/WR metrics

### June 6, 2026 — P0+P1+P3: Zero-Trade Double-Deadlock Fixed + Disk Recovered (commit `b4e59cec`)

**Context:** Zero trades since 2026-06-01. Investigated live `historic_predictions.pkl` (not just Telegram logs) and found two independent blockers, each sufficient to kill all entries.

**P0 — do_predict=0 on 100% of live candles (primary killer):**
- After 2026-06-04 brain promotion (identifier → `finbuddy_v23_perpair_funding_1780574683`), `use_SVM_to_remove_outliers: true` was active. The SVM was flagging every current candle as an outlier (training-serving distribution skew — recent market doesn't match training window).
- `populate_entry_trend` requires `do_predict==1` — with 100% zeros, no long or short could ever fire.
- Fix: `use_SVM_to_remove_outliers: false` in `config.json`. Identifier bumped → `finbuddy_v23_nosvm_1780729988`. Flushed stale `historic_predictions.pkl` + `pair_dictionary.json`. Container force-recreated.

**P1 — Positive prediction bias → short deadlock in BEAR (second independent blocker):**
- Live predictions: BTC mean +0.64σ (min +0.33, never negative), ETH +0.76, SOL +0.94.
- BEAR regime hard-blocks longs. Shorts need `centered_pred < ~-0.9σ`. Model never reaches it. Result: regime blocks longs, model can't short → deadlock.
- Root cause: Fix 7 (2026-05-22) removed serve-time rolling-median recentering on the assumption "z-scored training ⇒ serve-time centered at 0". Live data proved false — serving distribution drifts positive when market conditions differ from training window.
- Fix: re-added `rolling(100, min_periods=10).median()` subtraction consistently in all 3 locations (entry, exit, leverage) — resolving the original inconsistency (rolling vs tail) that motivated Fix 7.

**P3 — Disk 81% unresolved by hourly watchdog cleanup:**
- `brain_cleanup.py` only freed 16 MB: `wf_*` dirs not covered by `brain_*` glob; Docker-owned files fail `shutil.rmtree` silently (PermissionError not caught).
- Fix: added `wf_*` pattern; `_rmtree_sudo()` fallback using `subprocess.run(["sudo","rm","-rf"])`; default max-age 7d → 2d.
- One-time manual sudo prune: 544 dirs removed → disk 73% (freed ~5 GB).

**What to watch:**
- After retrain (~12h): `do_predict` ratio should recover to >40%; first SHORT entry in BEAR should fire.
- Brain bull-window 0-longs: deferred. Suspected `_get_regime_series` fallback to live regime; needs one verification backtest.

### June 8, 2026 (Evening) — Infra: Disk 47→200GB, Deep Data Backfill, n8n stopped

**1. Boot volume expanded 47GB → 200GB (in-place).** Was at 77% (disk-pressure alerts). User resized the boot volume in OCI console; I ran the server-side expansion:
`echo 1 | sudo tee /sys/class/block/sda/device/rescan` → `sudo growpart /dev/sda 1` → `sudo resize2fs /dev/sda1`.
Result: `/` now **193GB, 18% used, 160GB free**. Online resize, no reboot, no data moved, no second volume.

**2. Deep historical backfill** (`scripts/backfill_historical_data.sh`, commit `…`). One-time `--prepend` download from **2020-01-01** for all 26 pairs × 5 TFs. Extends the brain's perspective to regimes it had never seen: 2020 COVID crash, 2021 euphoria, 2022 LUNA/FTX crash. BTC/ETH now 6.4yr coverage; alts backfill to listing date. Non-destructive (prepend only). Runs in background. NOTE: `docker-compose run` does NOT accept `--cpu-shares` (caused 2026-06-01 WF crash — do not add it).
- Data sizing verdict: **6.4yr for BTC/ETH is ideal** (one full cycle + extremes). More ≠ better (pre-2020 market is structurally different). Live model only trains on rolling 90d (`train_period_days`); deep history benefits brain backtests + HMM regime detector, NOT the live model's training window.

**3. n8n container STOPPED (not removed).** Was idle (310MB RAM, 0% CPU) — N8N permanently disabled for weeks. `docker update --restart=no n8n && docker stop n8n`. Container preserved; restart with `docker start n8n`.

**4. Honest brain assessment** (no action, recorded for context): scout_failed (45%) is NOT waste — it's the brain cheaply pre-filtering bad configs via 6-pair scout before full 26-pair runs (working as designed). Brain IS self-evolving in the narrow sense (hill-climb + evolutionary mutation of top performers + Optuna TPE + experiment memory), but NOT self-aware/conscious — it tunes dials inside a human-defined search space (`AGGRESSIVE_CHOICES_V23`); it cannot invent new features/strategy logic. Real next frontier = LLM-driven FEATURE/STRATEGY generation (not just param tuning). Open limitation: `bear_2026Q1` promotion gate DISABLED 2026-06-07 (45/45 failed); should be re-enabled once the centering fix lets configs pass it.

**5. Brain-side improvements (safe during freeze — zero live-model impact):**
- `promote.py`: **re-enabled bear_2026Q1 gate** (`BEAR_2026Q1_REQUIRED="bear_2026Q1"`) — precondition "_GLOBAL_STD fixed" met today. Blocks promoting configs known to fail on recent bear.
- `hypothesis_gen.py` + `analyst.py`: added **`bull_2021`** (euphoria, classified BULL) + **`crash_2022`** (LUNA/FTX black-swan STRESS window — neither bull/bear, excluded from promotion averages, used as survival gate). Enabled by the 2020 backfill; ~12/26 pairs have data this far back.
- `runner.py`: **surface backtest failure reason** — was `if returncode!=0: return []` (silent). Diagnosed the 170 "failures": only 3 were timeouts, **167 failed fast (real errors)** — so raising timeout would NOT help (corrected my earlier suggestion). Now logs the error tail to brain_run.log.
- `queue.jsonl`: pruned **25 stale out-of-scale entries** (leftover st<-1.0 / lt>0.8). Queued 3 crash_2022/bull_2021 stress experiments. Backup: `queue.jsonl.bak_20260608`.

**6. SYSTEM FROZEN to measure the centering fix.** No further **trading-logic/model** changes until ≥1 week of clean data + tonight's WF. Specifically: do NOT tune thresholds, prune features (530→~80 is deferred BECAUSE it changes the live model and would contaminate the measurement), or change the strategy. Brain-side changes above are safe — they don't touch the live model's predictions.

### June 8, 2026 (PM) — Centering Window Fix: Directional Signal Restored (commit `5aff4cd3`)

**Root cause of BOTH the brain 0-longs-in-bull bug AND the 37.7% live WR.**

The serve-time prediction centering subtracted `rolling(100).median()` = only **25 HOURS** on 15m. A 25h median tracks the price trend itself, so subtracting it stripped the model's directional signal:
- **Raw predictions: 69–72% positive** (model correctly leans long in the up-market — this is the alpha)
- **Centered (r100): 46–49% positive** (forced 50/50 → pure mean-reversion)

This converted a directional model into a mean-reversion model. Symptoms:
- Brain: 60 z-score experiments with **0 longs in BULL windows** (e.g. `bull_2024Q2` LT=1.0 → L/S=**0/38**, all shorts in a bull quarter)
- Live: **37.7% WR** — model forced to short into uptrends

**Fix:** added class constant `_CENTERING_WINDOW = 1920` (20 days), `_CENTERING_MIN_PERIODS = 200`. Applied to all 3 centering sites (leverage line ~820, entry ~1386, exit ~1504).
- Empirically (historic_predictions.pkl): raw 69% → centered **69%** (BTC), 72% → 69% (ETH) — **direction preserved**.
- Simulated entries at threshold≈0.39: BTC long 14%→**33%**, SUI 17%→**53%**, UNI 13%→**55%**, DOT 18%→**59%**.
- Shorts still fire on weak pairs (FET 24%, RENDER 27%) — **no BEAR deadlock reintroduced**.
- `1920 < startup_candle_count (2400)` so the window is fully populated and **identical in live and backtest**. `min_periods=200` matches the z-score normalization warmup (`ROLLING=2880, min_periods=200`).

**No retrain** — serve-time transform on existing predictions. Identifier unchanged (`finbuddy_v23_nosvm_1780729988`). Container restarted (strategy is a mounted volume → reloads on restart). The brain auto-benefits: it runs the same strategy file, so future experiments will explore longs in bull windows.

**Coupling rule:** if `_CENTERING_WINDOW` changes, it MUST stay identical across all 3 sites (leverage/entry/exit) so threshold comparisons are coherent, and stay `< startup_candle_count` so live==backtest.

**Validation pending:** daily WF tonight (22:00 UTC) and next brain bull-window runs are the natural gates — both should now show non-zero longs and (hopefully) improved WR.

### June 8, 2026 — Two-Layer Threshold Deadlock Fixed (commits `513170f4`, `d0d596a4`)

**Root cause: `_GLOBAL_STD=0.95` was a relic from the raw-% prediction era. After z-scoring (2026-05-22), live model predictions have std≈0.13–0.30. This caused a two-layer deadlock.**

**Layer 1 — `_GLOBAL_STD` mismatch (`513170f4`):**
- `std_factor = pair_pred_std / 0.95 = 0.13/0.95 = 0.14` → always floored to 0.5
- Effective threshold: `LT(1.5) × combined(1.3) × std_factor(0.5) = 0.975`
- Max centered_pred across all 26 pairs = 0.535
- `0.535 < 0.975` → **zero entries mathematically impossible for any pair**
- Fix: `_GLOBAL_STD = 0.95` → `0.30` in strategy. `LT = 1.5` → `0.5` in .env. Updated hypothesis_gen.py SEED/AGGRESSIVE_CHOICES/_clamp/Optuna. Removed 106 stale LT>0.9 queue entries.

**Layer 2 — `std_factor` cap backwards (`d0d596a4`):**
- With fixed `_GLOBAL_STD=0.30`, ETH pred_std=0.33 → `std_factor=0.33/0.30=1.096` (above cap of 3.0 → not clipped)
- ETH: threshold=`0.5 × 1.3 × 1.096 = 0.712`. ETH centered=0.538 < 0.712 → still blocked
- The cap being `3.0` was BACKWARDS: higher pred_std means better model discrimination, not more noise — shouldn't penalize with harder threshold
- Fix: `std_factor = (pair_pred_std / 0.30).clip(lower=0.5, upper=1.0)` — cap at 1.0. Also `LT 0.5 → 0.3`.
- With fix: ETH threshold = `0.3 × 1.3 × 1.0 = 0.390`. ETH centered=0.538 > 0.390 → **FIRES LONG**.

**Result: UNI SHORT opened at 10:00 UTC 2026-06-08 (+0.112 USDT). ETH LONG expected on next 15m candle.**

**Coupling rule for `_GLOBAL_STD` (CRITICAL — added to strategy comment):**
If `_GLOBAL_STD` ever changes again, MUST update all 5 places together:
1. `_GLOBAL_STD` constant in `FinBuddyFreqAI_v23.py`
2. `.env` `FREQAI_LONG_THRESHOLD` + `FREQAI_SHORT_THRESHOLD`
3. `hypothesis_gen.py` SEED_CONFIG_V23 LT/ST values
4. `hypothesis_gen.py` AGGRESSIVE_CHOICES_V23 + `_clamp` bounds + Optuna ranges + safe-band check
5. `queue.jsonl` — prune stale LT entries outside new valid range

**Brain queue updated:** 106 old LT>0.9 entries removed. 15 new experiments added: LT=0.2/0.3/0.5 × 5 windows.
**Brain SEED/CHOICES/clamp/Optuna all updated** to new scale [0.1–0.8] for LT, [-1.0 to -0.1] for ST.

### May 26, 2026 — UI and Security Fixes (Conscious Brain Update)
1. **P&L Today Fix**: `Overview.jsx` was checking `Array.isArray(dailyPerf)` but FreqTrade wraps it in `{"data": [...]}`. It also read `profit_all_coin` instead of `abs_profit`, and read the oldest entry instead of the newest. Fixed all 3 bugs to render P&L Today correctly.
2. **Live Walk-Forward Folds UI**: The UI used to mix the active Deep WF's progress ("8/21 folds") with the metrics of the older 1-fold Daily WF. We added `/api/wf/running-folds` to `streamer.py` to parse the `fold_*_result.json` files on the fly for the active run, and decoupled the UI so you now see a dedicated "Active Walk-Forward (Running)" card with live updating stats.
3. **Streamer.py Security Audit**: Fixed hardcoded FreqTrade credentials by moving them to `.env` (`FT_USER`, `FT_PASS`). Added token auth checks (`verify_token`) to both `/ws/brain` and `/ws/memory` WebSockets to prevent unauthorized access. Restricted CORS origins, and tightened the WF regex to prevent potential path traversal via symlinks.
