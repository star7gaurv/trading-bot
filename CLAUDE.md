# FinBuddy — Master Project Context for Claude

> This file is the single source of truth for any Claude instance working in this repo.
> Read this fully before touching any file, writing any code, or making any suggestion.
> For current phase status and roadmap → always check [[finbuddy_memory/FINBUDDY_PROJECT_MEMORY]] first.

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

## What Is Live and Working Right Now (verified 2026-05-09 by Claude Code)

### FreqTrade
- Running **`FinBuddyFreqAI.py` (v20)** in dry-run mode on **Binance Futures USDT-M** — long+short
- FreqAI identifier: `finbuddy_v19_asym_1778575138` (2x leverage, 8 max trades, macro safety gates active)
- 1000 USDT virtual wallet, max 8 open trades, 2x leverage enabled
- API: `http://localhost:8080/api/v1` — user: `bot`, pass: `REDACTED-FREQTRADE__API_SERVER__PASSWORD`
- Whitelist: **25 pairs**, **1h timeframe**
- Status: Optimized on 2026-05-14 (fixed regime path, news fetcher, and Google Trends 429)

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

### ✅ Active: `FinBuddyFreqAI.py` v20 — Futures Long/Short + Macro Safety
- Binance Futures USDT-M (perpetual, isolated margin), **1h TF**, 25 pairs, `can_short=True`
- **2x Leverage**: Implemented via `leverage()` callback for balanced profit/risk.
- **Max Open Trades**: Increased to 8 for better diversification across clusters.
- **Regime Fix**: Strategy now correctly resolves `/freqtrade/finbuddy_memory/regimes/current.json`.
- **Macro Guard**: `confirm_trade_entry` blocks longs in Extreme Fear (<20) and shorts in Extreme Greed (>80).
- FreqAI identifier: `finbuddy_v19_asym_1778575138` — Asymmetric barriers (K_TP=2.0, K_SL=1.0)
- `custom_stoploss()`: ATR-based stops fixed (commit `21796ea`)
- **External Data**: Fixed News Fetcher (Catalogs 48/49) and Google Trends (backoff/retry logic active).

### ✅ Active: `FinBuddyLLMModel.py` v5
- LightGBM + NVIDIA/OpenRouter LLM confirmation layer
- **v5 fix (2026-05-12)**: Auto-confirms signals with proba ≥ 0.90 (was blocking 91% of signals)
- `AUTO_CONFIRM_THRESHOLD=0.40` — bypass LLM for very high-confidence predictions
- `COOLDOWN_SECONDS=1800` — 30-min per-pair veto window (was 60 min)
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
| 1 | `finbuddy_memory/tasks/phase-1-freqai-brain.md` | 🔄 **In Progress** — v17 live, walk-forward running | FreqAI brain — long + short, 2-class model |
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
