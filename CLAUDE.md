# FinBuddy — Master Project Context for Claude

> This file is the single source of truth for any Claude instance working in this repo.
> Read this fully before touching any file, writing any code, or making any suggestion.
> For current phase status and roadmap → always check [[FINBUDDY_PROJECT_MEMORY]] first.

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
5. **Never hardcode secrets:** API keys, passwords, and tokens must always come from environment variables, never from committed files.

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

## What Is Live and Working Right Now (verified 2026-05-09 by Claude Code)

### FreqTrade
- Running **`FinBuddyFreqAI.py` (v16.2)** in dry-run mode on **Binance Futures USDT-M** — long+short
- FreqAI identifier: `finbuddy_v16_clean_1778316280` — 25 pairs, all trained, zero KeyError H
- 1000 USDT virtual wallet, max 4 open trades, 200 USDT stake × regime multiplier
- API: `http://localhost:8080/api/v1` — user: `bot`, pass: `REDACTED-FREQTRADE__API_SERVER__PASSWORD`
- Whitelist: **25 pairs**, **1h timeframe**
- First clean trades: #30 BTC short, #31 TON short, #32 DASH short (2026-05-09 10:00 UTC)

### N8N
- 🔴 **Permanently disabled** — FreqAI is sole signal source

### OpenClaw ("Jack")
- ☠️ **Permanently abandoned** — was only used as an OpenRouter proxy

### Telegram
- **FreqTrade native bot** (token `8557119080:...`) — ✅ live, fires trade notifications + watchdog alerts + daily summary
- Both post to Chat ID: `5622292536`

### All Crons Live (verified 2026-05-09)
```
0 * * * *    auto_commit.sh                    # vault git commit hourly
*/15 * * * * fetch_all_external.py             # Phase 2 data
0 */4 * * *  hmm_regime_detector.py            # Phase 3 HMM
*/15 * * * * memory_writer.py && git_commit.sh # Phase 4 memory
0 2 * * *    karpathy/run_loop.py              # Phase 5 research
*/5 * * * *  executor/executor.py              # Phase 7 executor
*/30 * * * * watchdog.py                       # Telegram alert: container/training/heartbeat
*/15 * * * * trade_postmortem.py               # Closed-trade ledger → closed.md
0 8 * * *    pair_performance.py               # Per-pair WR/PF report
0 8 * * *    daily_summary.py                  # Telegram morning digest
0 6 * * *    run_promotion.sh                  # Daily promotion check
```

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

### ✅ Active: `FinBuddyFreqAI.py` v16.2 — Futures Long/Short (2026-05-09)
- Binance Futures USDT-M (perpetual, isolated margin), **1h TF**, 25 pairs, `can_short=True`
- FreqAI LightGBM **2-class model** (`["L","S"]`) — time-barrier candles DROPPED (not mapped to S)
- FreqAI identifier: `finbuddy_v16_clean_1778316280` — all 25 pairs trained, zero KeyError H
- `custom_stoploss()` anchored via `stoploss_from_open()`, `trailing_stop=False`
- **Regime-aware exits** (v16): CRASH/BEAR → exit longs at 0.55, BULL/EUPHORIA → exit shorts at 0.55, NEUTRAL → symmetric 0.65
- **HMM kill-switches**: CRASH → no longs, EUPHORIA → no shorts
- **Correlation cluster cap** (v16.2): max 2 trades from MEGA_CAP cluster (BTC/ETH/SOL/etc) or L2 cluster (ARB/OP/etc) — enforced via `confirm_trade_entry()`
- **Funding-rate long guard** (v16.2): blocks new longs if BTC perpetual funding >0.05%/8h
- Enter tags: `freqai_lgbm_v16_long` / `freqai_lgbm_v16_short`
- `BTC_MA200_GATE` env var defaults to `"0"` — opt-in only

### ❌ Retired: `AiGuardrailStrategy.py`
- Superseded by `FinBuddyFreqAI.py`. Do not reference or restart.

### Deployed but not active: `FinBuddyLLMModel.py` (Task 1.2)
- Custom FreqAI model with Grok-3-Mini LLM confirmation layer
- Committed to `freqtrade/user_data/freqaimodels/` — not currently wired into config

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
| 0 | `tasks/phase-0-foundation.md` | ✅ **Complete** (2026-04-27) | Foundation — FreqTrade, Telegram, server |
| 1 | `tasks/phase-1-freqai-brain.md` | 🔄 **In Progress** — v16.2 live, walk-forward running | FreqAI brain — long + short, 2-class model |
| 2 | `tasks/phase-2-data-enrichment.md` | ✅ **Live** — cron every 15m | External data fetchers — Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends |
| 3 | `tasks/phase-3-hmm-regime.md` | ✅ **Live** — cron every 4h | HMM 5-regime engine wired into strategy |
| 4 | `tasks/phase-4-obsidian-memory.md` | ✅ **Live** — cron every 15m | Obsidian vault auto-write + git auto-commit |
| 5 | `tasks/phase-5-karpathy-loop.md` | ✅ **Live** — cron 02:00 daily | Nightly research loop — Gemini + DeepSeek R1 |
| 6 | `tasks/phase-6-tradingview.md` | 🔴 **Abandoned** (2026-05-04) | TV alerts require paid plan — permanently dropped |
| 7 | `tasks/phase-7-executor.md` | ✅ **Live** — cron every 5m | Python signal executor (paper mode) |
| 8 | `tasks/phase-8-futures-setup.md` | ✅ **Complete** (2026-05-05) | Binance futures API, isolated margin |
| 9 | `tasks/phase-9-futures-risk.md` | ✅ **Complete** (2026-05-09) | Risk engine: regime sizing + cluster cap + funding guard |
| 10 | `tasks/phase-10-live-migration.md` | ⬜ **BLOCKED** | Needs walk-forward PASS or 6-month dry-run track record |

---

## Architecture Decision (ADR-001): Signal-as-a-Service
Full doc in `docs/ADR-001-multi-tenant-architecture.md`.

**Chosen Option C** — Signal-as-a-Service + thin per-user executor:
- One central brain publishes signals (O(1) cost regardless of user count)
- Each user has a lightweight Python executor (~300–500 LOC)
- Non-custodial: user API keys scoped for trading only (no withdrawal)
- One user's problem cannot cascade to others

**Phase 1 (now):** Single user (Gaurav), multi-tenant-shaped code.
**Phase 2 (after 6-month live track record):** Add signup, API-key encryption, billing, dashboard.

---

## Signal Contract
Fully specced in `docs/signal-contract.md`. Key fields:
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

### March 31 – April 4, 2026
- Removed Dify completely (9 containers, freed ~6GB disk)
- Fixed FreqTrade: API credentials, wrong strategy, f-string syntax, SQLite reset
- Got first dry-run trade: BTC/USDT @ 67,206.72 USDT
- Dropped OpenRouter → Groq direct API
- N8N v4 pipeline confirmed live with Groq Llama 3.3 70B

### April 21–22, 2026
- Wrote ADR-001, signal contract, strategy registry, N8N workflow split plan
- Set up FinBuddy Obsidian memory vault

### April 27, 2026
- Phase 0 live audit by Claude Code — confirmed v4 pipeline active, two Telegram bots live
- Created full 7-phase task roadmap in `tasks/`
- Created `CLAUDE.md` as master project context

### April 30, 2026 (Claude Code)
- `FinBuddyFreqAI.py` v6 deployed and running — `AiGuardrailStrategy.py` **retired**
- LightGBM training per pair confirmed live
- **N8N pipeline fully disabled** — FreqAI is now sole signal source
- Round 3 backtest: 144 combos, all FAIL, best Sharpe -0.401
- Phase 0: **5/5 complete**

### May 1, 2026 (Perplexity)
- Decided AI model stack: **Grok-3-Mini (xAI)** as signal confirmation in Task 1.2
- Added 5 Core Engineering Principles
- Updated `FINBUDDY_PROJECT_MEMORY.md` as master hub
- `COLLABORATION_CONTRACT.md` updated with role boundaries

### May 2, 2026 — 1:30 AM (Claude Code)
- Round 3 full analysis committed: 192 total combos across all rounds, all fail
- Root cause confirmed: bear market period (BTC -47.55%), not strategy logic
- ML signal quality confirmed: 79-81% WR on signal-driven exits ✅
- Graveyard.md updated, results CSV committed

### May 2, 2026 — 2:49 PM (Perplexity)
- Full memory sync across all 4 core MD files
- Stale references cleaned across all docs

### May 2, 2026 — Late session (Claude Code)
- 5 rounds of futures backtests run end-to-end (R1 → R5)
- Strategy iterated v6 → v7 → v8 → v9 → v10
- **R5 v10 is the breakthrough**: first positive Sharpe, first profitable bull, first PF > 1
- v10 mechanism: `custom_stoploss()` rewritten per Freqtrade docs, both stops anchored to entry price via `stoploss_from_open()` — flipped the trailing cohort from -0.60% avg / 15.8% WR to +0.04% avg / 51.2% WR
- Macro short-gate fix in v9 cut bull shorts from 81 → 26
- Docker user/permissions: ubuntu added to `opc` group; `freqtrade/user_data` group-owned + `g+w` so both ubuntu and the container's ftuser (uid 1000 = opc) can write
- `XAI_API_KEY` moved out of `docker-compose.yml` into `freqtrade/.env` (gitignored)
- FreqAI model artifacts now properly gitignored

### May 2, 2026 — 3:31 PM (Perplexity)
- **🚨 STRATEGIC PIVOT: Futures-first architecture decided**
- Spot backtesting retired — futures (USDT-M Perp) is now primary market
- Full vision expanded: all crypto market types as modular plugins (perp, funding rate, grid, arb, spot, DCA)
- Revised 10-phase roadmap committed
- `FINBUDDY_PROJECT_MEMORY.md`, `CLAUDE.md`, `CLAUDE_HANDOFF.md` all updated

### May 3–5, 2026 (Claude Code)
- Phase 8 (futures setup) + Phase 9 (risk engine) completed
- `FinBuddyLLMModel.py` (Task 1.2) deployed — xAI Grok-3-Mini signal confirmation layer wired into FreqAI
- `FinBuddyFreqAI.py` v15 deployed — 1h TF, label_period=6, 90-combo grid run (R8)
- **R8 winners**: ml_threshold=0.60, ml_exit=0.60, label_period=6, atr_threshold=0.002
- Bull window (2024-01-01→2025-01-01) ALL PASS: Sharpe +1.49, WR 57.7%, DD 2.5%, PF >1.2
- Bear window (2025-01-01→2026-04-01) partial: WR 58.7% ✅, DD 7.0% ✅, Sharpe -0.114 ❌, PF 0.979 ❌
- RiskEngine wired: regime-aware stake sizing in `custom_stake_amount()`, DD gate active
- Watchdog (`scripts/watchdog.py`) created — cron every 30m, Telegram on container down/training stale/heartbeat lost
- Trade postmortem (`scripts/trade_postmortem.py`) created — cron every 15m, closed trades → `finbuddy_memory/trades/closed.md`
- Walk-forward validator (`scripts/walk_forward.py`) created — OOS rolling-fold, gates Phase 10
- Fresh FreqAI identifier `finbuddy_v15_clean_1778268802` deployed — all 25 pairs trained
- Walk-forward: `docker-compose` bug (was `docker compose`) fixed; timerange bug (test-only → train+test) fixed; data download pre-step added

### May 8, 2026 — 7-Day No-Trade Crisis (Claude Code)
- **Crisis discovered**: Bot running, training ticking, but ZERO trades for 7 days straight
- **Root cause 1**: Old identifier `finbuddy_lgbm_v15` had partial state (4 pairs) — 21 new pairs never trained. Fix: new identifier `finbuddy_v15_clean_1778268802` → all 25 pairs retrained.
- **Root cause 2**: `datasieve.pipeline WARNING - Could not find step di` — confirmed cosmetic, NOT blocking
- **Root cause 3**: Macro filter deadlock — BTC at $80k between MA200 ($83k) and 4h EMA50 ($79k). Long required `btc_macro_bull==1` (FALSE), short required hardcoded `btc_4h_below_ema50==1` (FALSE). Zero trades possible. Fix: defaulted `BTC_MA200_GATE=0` (opt-in), removed hardcoded short filter.
- Commit `d127347`: "fix: unstick v15 — disable BTC MA200 gate, remove hard btc_4h_below_ema50 short filter, fresh FreqAI identifier"
- v16 Tier 1 build: regime-aware asymmetric exits, HMM kill-switches, v17 short filter finally removed
- `scripts/daily_summary.py` created — daily 8 AM Telegram digest (regime, open trades L/S split, P&L, stats)
- `daily_summary.py` added to crontab at `0 8 * * *`

### May 9, 2026 (Claude Code)
- **v16.1 clean 2-class model**: time-barrier candles dropped entirely (label=None not mapped to "S"). Fixed KeyError: 'H' crash affecting 20+ pairs. New identifier `finbuddy_v16_clean_1778316280`. All 25 pairs trained in 40s.
- **v16.2 additions**: `confirm_trade_entry()` with (1) BTC funding-rate long guard (blocks if funding >0.05%/8h) + (2) correlation cluster cap (max 2 trades per MEGA_CAP or L2 cluster). Cache at `/freqtrade/user_data/data/external/funding_rate_cache.json`.
- Enter tags updated: `freqai_lgbm_v11_long/short` → `freqai_lgbm_v16_long/short`
- **Watchdog fix 1**: Training false alert from Docker buffer eviction by 6770 KeyError H errors. Added file-log fallback (`use_file_fallback=True`) scanning `freqtrade.log` + rotated files.
- **Watchdog fix 2**: Heartbeat false alert from Docker daemon slowdown during `docker-compose run`. Raised timeout 15s→30s, enabled file fallback for heartbeat check too.
- **Walk-forward**: Data downloaded (all 25 pairs, 2024-01-01→2026-04-01, futures). 21 folds running. Results in `walkforward_results/FinBuddyFreqAI_2024-01-01_2026-04-01_20260509T091607/`.
- **First clean trades**: Trades #30–32 fired — first valid v16.1/v16.2 signals. (Trades 1–25 = legacy v11 spot, 26–29 = biased HOLD bug, 30+ = clean v16.)
- Dead cron entries removed: `@reboot openclaw`, `@reboot uvicorn webhook_receiver`
- All project context files synced to v16.2 state

### May 9, 2026 — Afternoon (Claude Code) — Anti-staleness + automation hardening + WF integrity

**Anti-staleness system (3 layers):**
- `scripts/sync_context.py` (cron 4h) — reads live data and rewrites `<!-- AUTO-SYNC -->` block in FINBUDDY_PROJECT_MEMORY.md, appends state-changes to `finbuddy_memory/session_events.md`, auto-commits.
- `.git/hooks/pre-commit` — soft warning when strategy/config/scripts change without doc update.
- `<!-- AUTO-SYNC -->` markers in FINBUDDY_PROJECT_MEMORY.md so live-state table is machine-maintained.

**Four pure-Python automations (zero token cost):**
- `scripts/walkforward_notify.py` (cron 30m) — Telegrams PASS/FAIL when a walk-forward run completes (presence of `summary.json`).
- `scripts/trade_postmortem.py` — added `check_trade_bias()`: alerts when last 10 trades are ≥85% one-sided (catches model-bias failure mode early; 6h cooldown).
- `scripts/watchdog.py` — added disk-usage check (warn 80%, critical 90%). Oracle free tier has no native warning.
- `scripts/walkforward_monthly.sh` (cron 1st of month, 03:00) + `scripts/download_data_daily.sh` (cron 04:30) — auto-runs walk-forward on a 27-month window monthly using fresh data; flock prevents overlap.

**Walk-forward bugs fixed (commits `752a046`, `5e1eaf9`):**
- Parser bug 1: read `max_drawdown_account` (correct field), not `max_drawdown` (didn't exist) → DD always 0%.
- Parser bug 2: aggregated metrics over the full 7-month timerange instead of the 1-month test window → fold 5 reported 2,079 trades instead of ~71. Fixed by parsing the per-trade list and filtering by `close_date ∈ [test_start, test_end)`.
- Sharpe now computed from daily-aggregated PnL (252-day annualisation), not bogus full-window number.
- Added `--reparse <run_id>` flag to re-aggregate completed runs without re-running 2h backtests.
- **Methodology bug — lookahead bias**: WF was loading the live bot's cached `finbuddy_v16_clean_*` models (trained on data through May 2026) and using them to predict on backtest dates from May 2024 forward. Fixed by passing `FREQTRADE__FREQAI__IDENTIFIER=wf_<ts>_f<NN>` per fold via env var on `docker-compose run`, forcing fresh in-window training.
- **Implication**: every walk-forward run before today's commits is invalid. Next monthly run will use the fixed code automatically.

---

## 🔗 Related Files (Obsidian Links)

- [[FINBUDDY_PROJECT_MEMORY]] ← master hub — always read this first for current status
- [[COLLABORATION_CONTRACT]] ← roles, automation rules, AI vs code boundaries
- [[CLAUDE_HANDOFF]] ← current action queue for Claude Code
- [[finbuddy_memory/CONTEXT]] ← live context injected into every AI prompt
- [[tasks/phase-1-freqai-brain]] ← current phase task file
- [[finbuddy_memory/strategies/graveyard]] ← retired strategies + backtest failures
- [[finbuddy_memory/signals/log]] ← signal history
- [[finbuddy_memory/regimes/current]] ← live regime

---

*This file must be updated at the end of every major session. It is the operational memory for any Claude instance opening this repo.*
