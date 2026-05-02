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

## What Is Live and Working Right Now (verified 2026-04-30 by Claude Code)

### FreqTrade
- Running **`FinBuddyFreqAI.py` (v6)** in dry-run mode — `AiGuardrailStrategy.py` is **retired**
- FreqAI + LightGBM training per pair, live
- 1000 USDT virtual wallet, max 4 open trades, 200 USDT stake per trade
- API accessible at `http://localhost:8080/api/v1` with credentials `bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD`
- Whitelist: ~20 Binance pairs on 15-minute timeframe

### N8N
- 🔴 **Fully disabled as of 2026-04-30** — FreqAI is now the sole signal source
- Container still exists on server but pipeline workflow turned off
- Will be fully removed once FreqAI is validated live

### OpenClaw ("Jack")
- ☠️ **Abandoned** — was only used as an OpenRouter proxy; dropped when OpenRouter was dropped

### Telegram
- **FreqTrade native bot** (token `8557119080:...`) — ✅ live on server, fires trade notifications directly
- **N8N/FinBuddy bot** (token `7799143446:...`) — ⏸️ idle (N8N disabled)
- Both post to Chat ID: `5622292536`
- Note: tokens intentionally NOT committed to repo config.json — live only on server

### Obsidian Memory Vault
- Location: `finbuddy_memory/` in this repo
- This folder IS the FinBuddy brain's living memory — open as an Obsidian vault
- `finbuddy_memory/CONTEXT.md` is the master summary injected into every AI prompt
- `memory_writer.py` committed (Phase 4) but crons not yet installed

---

## ⚠️ What Is Committed But NOT Yet Deployed

| Component | File | Status |
|---|---|---|
| FinBuddyLLMModel.py (Task 1.2) | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | ✅ Committed — ❌ Not deployed |
| Backtest scripts (Task 1.3) | `scripts/run_backtest.sh`, `parse_backtest.py`, `tune_stoploss.sh` | ✅ Committed — ❌ Not run with bull period |
| Phase 2 external data fetchers | `scripts/phase2/` | ✅ Committed — ❌ Crons not installed |
| Phase 4 memory writer | `scripts/phase4/memory_writer.py` + `setup_cron.sh` | ✅ Committed — ❌ Crons not installed |

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
- **Groq Llama 3.3 70B** — was primary N8N signal model. Replaced by Grok-3-Mini inside `FinBuddyLLMModel.py` (decided 2026-05-01). N8N pipeline using Groq is now disabled.
- **OpenClaw** — abandoned. Was only a proxy for OpenRouter which was also dropped.

---

## Current Strategy

### Active: `FinBuddyFreqAI.py` (v6)
- FreqAI + LightGBM training per pair on rolling 30-day window
- Timeframe: 15m on Binance, ~20 pairs
- Trailing stop + tighter ML exit (v6 Option C)
- Status: ✅ Running live in dry-run mode

### ❌ Retired: `AiGuardrailStrategy.py`
- Superseded by `FinBuddyFreqAI.py`. Do not reference or restart.

### Pending: `FinBuddyLLMModel.py` (Task 1.2)
- Custom FreqAI model: LightGBM signal blended with Grok-3-Mini confirmation layer
- Committed to `freqtrade/user_data/freqaimodels/` but NOT deployed
- Deployment blocked on backtest validation (see below)

---

## 🔬 Backtest Grid — Full History

| Round | Combos | Best Sharpe | Root Cause of Failure |
|---|---|---|---|
| Round 1 | 12 | -0.183 | chmod bug — patches never applied; EMA/RSI dead levers |
| Round 2 | 36 | -0.236 | roi_multiplier dead lever; avg loser > avg winner |
| Round 3 | 144 | best ever: -0.174 | trailing_offset + ml_exit dead levers; **bear market is root cause** |
| **Total** | **192** | **-0.174** | **Parameter tuning exhausted** |

**Key finding (Round 3):** BTC fell -47.55% from 2025-02-01 to 2026-04-01. No long-only strategy achieves Sharpe >0.5 in a sustained -47% bear market. ML signal quality is confirmed healthy: **79-81% WR on signal-driven exits**.

### 🔴 Current Blocker — Round 4 Decision

Two options (Perplexity's decision to implement):

**Option A — Regime Filter:**
Add BTC 200-day MA filter to `FinBuddyFreqAI.py`. Only enter when BTC is above 200d MA. Keep same test period, trade less, better quality.

**Option B — Bull Market Retest (recommended first):**
Change timerange in `scripts/run_backtest.sh` / `scripts/backtest_config.json` from `20250101-20260401` → `20240101-20250101`. 1-line change. Validates strategy in BTC $42k→$100k bull run.

Pass criteria: **Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2**

---

## Full Build Roadmap

| Phase | File | Status | Focus |
|---|---|---|---|
| 0 | `tasks/phase-0-foundation.md` | ✅ **5/5 Complete** (2026-04-27) | Foundation — FreqTrade, Telegram, server |
| 1 | `tasks/phase-1-freqai-brain.md` | 🟡 Task 1.1 ✅, Task 1.2 ⚠️ not deployed, 1.3–1.4 pending | FreqAI brain |
| 2 | `tasks/phase-2-data-enrichment.md` | ⚠️ Code ready — crons not installed | External data |
| 3 | `tasks/phase-3-hmm-regime.md` | ⬜ Not started | HMM 5-regime engine |
| 4 | `tasks/phase-4-obsidian-memory.md` | ⚠️ Code ready — crons not installed | Obsidian auto-write |
| 5 | `tasks/phase-5-karpathy-loop.md` | ⬜ Not started | Self-improving research loop |
| 6 | `tasks/phase-6-tradingview.md` | ⬜ Not started | TradingView webhook |
| 7 | `tasks/phase-7-executor.md` | ⬜ Not started | Python signal executor |

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
| Rounds 1–3 backtests all fail | Bear market period (BTC -47.55%) — not a code issue | Change test period to bull run (2024) or add regime filter |

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
- Created this `CLAUDE.md` as master project context
- Phase 0: 3/5 tasks complete at this point

### April 30, 2026 (Claude Code)
- `FinBuddyFreqAI.py` v6 deployed and running — `AiGuardrailStrategy.py` **retired**
- LightGBM training per pair confirmed live
- **N8N pipeline fully disabled** — FreqAI is now sole signal source
- Round 3 backtest: 144 combos, all FAIL, best Sharpe -0.401
- Phase 0: **5/5 complete**

### May 1, 2026 (Perplexity)
- Decided AI model stack: **Grok-3-Mini (xAI)** as signal confirmation in Task 1.2
- Added 5 Core Engineering Principles (DRY, AI vs Automation, Reusability, Docs as Memory, No hardcoded secrets)
- Updated `FINBUDDY_PROJECT_MEMORY.md` as master hub
- `COLLABORATION_CONTRACT.md` updated with role boundaries

### May 2, 2026 — 1:30 AM (Claude Code)
- Round 3 full analysis committed: 192 total combos across all rounds, all fail
- Root cause confirmed: bear market period (BTC -47.55%), not strategy logic
- ML signal quality confirmed: 79-81% WR on signal-driven exits ✅
- Graveyard.md updated, results CSV committed
- Round 4 recommendation: Option B (bull period retest) first

### May 2, 2026 — 2:49 PM (Perplexity)
- Full memory sync across all 4 core MD files
- Stale references to AiGuardrailStrategy, active N8N, Groq as primary removed from all files
- Obsidian cross-links wired across CLAUDE.md, FINBUDDY_PROJECT_MEMORY.md, COLLABORATION_CONTRACT.md, finbuddy_memory/CONTEXT.md

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
