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

## What Is Live and Working Right Now (verified 2026-05-20 20:00 UTC by Claude Code)

### FreqTrade
- Running **`FinBuddyFreqAI_v23.py` (v23)** in dry-run mode on **Binance Futures USDT-M** — long+short
- FreqAI identifier: **`finbuddy_v23_zscore_1779274507`** (bumped 2026-05-20 in commit `b4b02b7` for symmetric-gates + DI/SVM + recent_wr removal)
- FreqAI model: **LightGBMRegressor** (predicts `&-future_return %`, not classifier). DI=1.0 + SVM outlier removal active.
- **1000 USDT** virtual wallet (reverted from 10000 on 2026-05-20 commit `2f01b56`), max 8 open trades
- **Confidence-based leverage** (commit `60d4fb4`): 1x / 2x / 3x tiers based on `centered_pred / threshold` ratio (env-tunable). Fallback now LOW (1x) per round-3 audit (`5f37ab8`).
- API: `http://localhost:8080/api/v1` — user: `bot`, pass: `REDACTED-FREQTRADE__API_SERVER__PASSWORD`
- Whitelist: **37 pairs**, **15m timeframe** (each pair has 5 TFs of historical data: 15m + 30m + 1h + 4h + 1d)
- **Per-pair-per-regime gate active** — `pair_regime_stats.json` blocks pair-regime combos with rolling 30d (n≥5, WR<40%, PF<0.7)
- Strategy env vars (live): K_TP=2.0, K_SL=2.0, **LONG_THRESHOLD=2.0, SHORT_THRESHOLD=-2.0, STABILITY_N=1** (loosened from 3.25/-2.75/2 on 2026-05-20 when trade volume collapsed to 3/day)

### Model features (~530 total after Bug D removed `%-recent_wr` 2026-05-20)
Standard layer 4 features include 3 funding-rate features (`%-funding_rate`, `%-funding_rate_z30d`, `%-funding_rate_chg`) from BTC perp data, plus fear_greed, btc_strength, news_sentiment, regime_numeric. Daily refresh of historical funding parquet at 01:25 UTC. `%-recent_wr` DROPPED 2026-05-20 (training-serving skew: live read 0.34, brain/WF defaulted 0.50).

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

### Profitability reality check (2026-05-20 evening)
- **296 lifetime trades, +$110.78 dry-run** wallet (1110.78 / 1000 = +11.08%)
- Brain has 265+ completed experiments. Best `e0e1bf338410` profit=+0.192% WR=48.1% Sharpe=1.42 was on bear_2025Q1 — but ONLY ever tested on 5-pair brain universe. Pre-2026-05-20 brain results marked legacy via `live_baseline.json::config_aligned_at`.
- **No promotion has fired yet.** Brain's best 16 configs (≥2+2 sample): all have B_avg ≤ 0 OR B_sharpe ≤ 0. The deferred long-bias root cause (raw % regression target with no normalization) is the structural reason bull runs underperform; per-pair median offset is a patch, not a fix.
- v22 strategy file + LLM model file kept on disk for history; never loaded by live config or brain.
- **In-flight:** manual WF (PID 3095719) started 13:21 UTC testing all today's fixes; fold 1 in progress; full result ~tomorrow 07:00 UTC.

### Open issues deferred to future sessions
1. **Target z-scoring at train time** — proper fix for the long-bias the per-pair median offset only patches over. Half-day project.
2. **Open Interest delta** as a new feature (second-best published signal after funding).
3. **Pair expansion to ~37 pairs** — full 9-step runbook saved at `finbuddy_memory/tasks/pair_addition_runbook.md`; deferred until tonight's WF result lands so we don't conflate the bug-fix effect with universe expansion.

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
0 22 * * *   walkforward_daily.sh               # NEW 2026-05-19: daily WF (12mo trailing, ~80min)
0 3 1 * *    walkforward_monthly.sh             # Monthly heavy WF (27mo full)
0 4 * * *    auto_promote.py                    # NEW 2026-05-19: WF Sharpe vs baseline alert
*/30 * * * * walkforward_notify.py              # PASS/FAIL Telegram on new WF summary
30 4 * * *   download_data_daily.sh             # forward-increment data download
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
- Binance Futures USDT-M (perpetual, isolated margin), **15m base TF**, 37 pairs, `can_short=True`
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

### ⏭️ Next: v19 — Asymmetric Barriers
- Split K_MULT → K_TP=2.0×ATR / K_SL=1.0×ATR
- Theoretical PF = 3.26 at 62% WR — fixes fee-drag failure of v18
- See `CLAUDE_HANDOFF.md` for implementation plan

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
| Active strategy | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` |
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
