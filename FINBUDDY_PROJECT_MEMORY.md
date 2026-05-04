# FinBuddy Project Hub

> **Phase boundary:** As of 2026-05-03, all performance evaluation and future research are considered **Futures Mode only** (Binance USDT-M Perpetual, long AND short). Any older spot-only conclusions or metrics are kept only as historical context and must NOT be used to judge the current system.

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟢 v11 deployed · Phases 0–7 wired · Futures infra online · Walk-forward / label redesign next
**Last Updated:** 2026-05-04 (Claude Code — Phase 8+9 complete, label fix, risk engine wired)

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

## ✅ Step 7 Complete (2026-05-03) — Infra Phases 1–7

**What Claude Code’s latest session achieved on server (reporting back to this hub):**

- **FreqTrade futures container**: ✅ Running, dry-run; FinBuddyFreqAI **v11** loaded; API available on port 8080
- **Phase 2 — Data enrichment**: ✅ `fetch_all_external.py` wired to cron every 15 minutes, writing `combined_context.json`
- **Phase 3 — HMM regime engine**: ✅ `hmm_regime_detector.py` wired to cron every 4 hours, writing `finbuddy_memory/regimes/current.{json,md}`
- **Phase 4 — Obsidian memory writer**: ✅ `memory_writer.py` + `git_commit.sh` wired to cron every 15 minutes, updating `finbuddy_memory/CONTEXT.md` and auto-committing vault changes
- **Phase 5 — Karpathy loop**: ✅ `karpathy/run_loop.py` wired to daily cron at 02:00, writing nightly research notes under `finbuddy_memory/research/`
- **Phase 6 — TradingView webhook**: ⚠️ **Partial** — `webhook_receiver.py` created; FastAPI/uvicorn NOT yet installed; service not running; Nginx proxy path in place but backend returns 502 until uvicorn is installed
- **Phase 7 — Python executor**: ✅ `executor/executor.py` wired to cron every 5 minutes, `/health` endpoint reports “0 signals processed (DB initialized and functional)”

### Live crontab (server truth, as of 2026-05-03)
```cron
*/15 * * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/fetch_all_external.py >> /home/ubuntu/.finbuddy/logs/data_fetcher.log 2>&1
0 */4 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/hmm_regime_detector.py >> /home/ubuntu/.finbuddy/logs/hmm_regime.log 2>&1
*/15 * * * * python3 /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/memory_writer.py && bash /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/git_commit.sh >> /home/ubuntu/.finbuddy/logs/memory_writer.log 2>&1
0 2 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/karpathy/run_loop.py >> /home/ubuntu/.finbuddy/logs/karpathy.log 2>&1
*/5 * * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/executor/executor.py >> /home/ubuntu/.finbuddy/logs/executor.log 2>&1
```

This confirms: **Phases 2, 3, 4, 5, and 7 are not just coded — they are live and automated.**

---

## 🚨 Strategic Pivot (2026-05-02)

### Why We Pivoted Away From Spot

Spot trading is structurally long-biased — you can only buy low, sell high. The 192-combo backtest failure across 3 rounds was not a strategy bug — it is an **architectural ceiling**. BTC fell -47.55% during the test period (2025-02-01 → 2026-04-01). No parameter tuning, no better ML model, no regime filter can fix a long-only strategy in a sustained -47% bear market. We were fighting physics.

**Root finding from Round 3:** ML signal quality is confirmed healthy (79–81% WR on signal-driven exits). The brain works. The market type was wrong.

### Why Futures (USDT-M Perp) Fixes This

| Feature | Spot | Futures (Perp) |
|---|---|---|
| Bear market | ❌ Can't profit | ✅ Short positions profit |
| Bull market | ✅ Works | ✅ Works (with leverage) |
| Sideways/range | ❌ Bleeds | ✅ Scalping + funding rates |
| Shorting | ❌ Not possible | ✅ Native |
| Leverage | ❌ None | ✅ 2–5x conservative use |
| Funding rate income | ❌ None | ✅ Passive when neutral |
| Market neutrality | ❌ | ✅ Long/short, delta-neutral |

---

## 📈 Five Futures Backtest Rounds — Trajectory (v6 → v10)

*(v11 is the current live strategy; v10 remains the last fully analyzed backtest round.)*

| Round | Strategy | Key Change | Bull P&L | Bear P&L | Bull Sharpe | Bear Sharpe |
|---|---|---|---|---|---|---|
| 1 | v6 | Futures-ready spot rewrite | -10 | -23 | -0.145 | -0.258 |
| 2 | v7 | Stoploss tightened to -1.5% | -47 | -36 | -0.896 | -0.554 |
| 3 | v8 | ATR-based `custom_stoploss()` | -33 | -12 | -0.78 | -0.22 |
| 4 | v9 | `trailing_stop=False` + macro short-gate | -7 | -22 | -0.13 | -0.37 |
| **5** | **v10** | **`stoploss_from_open()` — entry-anchored stops** | **+7.24** | **-8.78** | **+0.13** | **-0.15** |

*(Full R5 analysis and the walk-forward OOS failure are kept in `CLAUDE_HANDOFF.md` for historical reference and future label redesign work.)*

---

## 🚀 Current State

| Component | Status |
|---|---|
| **FreqTrade** | ✅ Running, dry-run, AiGuardrailStrategy |
| **N8N v4 Pipeline** | ✅ Active, 15-min signal generation, Groq Llama 3.3 70B |
| **Groq AI** | ✅ Live, free tier, ~200ms response |
| **Strategy Registry** | ✅ Created, rsi_macd_ai_v1 active (pending backtest) |
| **Memory Vault** | ✅ Obsidian structure ready |
| **Phase 0** | 🔴 In progress (4/5 complete) |

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
5. **Never hardcode secrets:** API keys always from environment variables, never committed files.

---

## 📚 Critical Freqtrade Rules (from develop docs — must follow)

These are rules from the official Freqtrade develop docs that directly impact our strategy code:

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
| **grok-3-mini** | xAI | `XAI_API_KEY` | $0.10/M | ✅ Real-time signal confirmation — PRIMARY |
| **grok-3** | xAI | `XAI_API_KEY` | $2/M | Optional upgrade if needed |
| **claude-sonnet-4-5** | Anthropic | `ANTHROPIC_API_KEY` | $3/$15/M | ✅ Claude Code — deploy, monitor, debug |
| **gemini-2.5-flash** | Google | `GEMINI_API_KEY` | Free tier | Nightly research loop (Phase 5) |
| **deepseek-chat** | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M | Future bulk hypothesis generation |

---

## 🚨 Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ NEEDS REVIEW | Code in GitHub, NOT yet fully live or has gaps |
| 🟡 IN PROGRESS | Actively being worked on |
| ⬜ PENDING | Not started |
| 🔴 RETIRED | Superseded — do not continue |

---

## 🚀 Current System State (as of 2026-05-03)

| Component | Status | Notes |
|---|---|---|
| **FreqTrade futures** | ✅ Running, dry-run | FinBuddyFreqAI v11, Binance USDT-M, isolated margin |
| **Phase 1 — FreqAI brain** | 🟡 Active | v11 deployed; label_period=12, ml_threshold grid up to 0.70, grid re-running |
| **Phase 2 — Data enrichment** | ✅ Live | All 5 fetchers + master aggregator cron’d |
| **Phase 3 — HMM regimes** | ✅ Live | 5-regime HMM writes `regimes/current.{json,md}` every 4h |
| **Phase 4 — Obsidian memory** | ✅ Live | CONTEXT + signals/research auto-written + git auto-commit |
| **Phase 5 — Karpathy loop** | ✅ Live | Nightly Gemini + DeepSeek research at 02:00 |
| **Phase 6 — TradingView webhook** | 🔴 Abandoned | TradingView alerts require paid plan — dropped. FreqAI is sole signal source. |
| **Phase 7 — Executor** | ✅ Live (paper) | Signal executor cron every 5 min; `/health` OK; 0 signals processed so far |
| **N8N pipeline** | 🔴 Permanently disabled | FreqAI is sole signal source |

---

## 🆕 Revised Phase Roadmap (Authoritative)

*(This table supersedes any older roadmap tables in this file. For the canonical live view, also see `tasks/TASKS.md`.)*

| Phase | File | Status | Focus |
|---|---|---|---|
| 0 | `tasks/phase-0-foundation.md` | ✅ Complete | Foundation — FreqTrade, Telegram, server, N8N cleanup |
| 1 | `tasks/phase-1-freqai-brain.md` | 🟡 In Progress | FreqAI brain — futures long+short, v11 failing → v12 plan drafted at `finbuddy_memory/research/v12_strategy_plan.md` (awaiting Gaurav review) |
| 2 | `tasks/phase-2-data-enrichment.md` | ✅ Live | External data fetchers + combined_context.json |
| 3 | `tasks/phase-3-hmm-regime.md` | ✅ Live | 5-regime HMM engine + regime-aware sizing hooks |
| 4 | `tasks/phase-4-obsidian-memory.md` | ✅ Live | Obsidian vault auto-write + auto git commit |
| 5 | `tasks/phase-5-karpathy-loop.md` | ✅ Live | Nightly research loop (Gemini + DeepSeek R1) |
| 6 | `tasks/phase-6-tradingview.md` | 🔴 Abandoned | TradingView alerts are a paid feature — dropped (2026-05-04) |
| 7 | `tasks/phase-7-executor.md` | ✅ Live (paper) | Python signal executor + `/health` endpoint |
| 8 | `tasks/phase-8-futures-setup.md` | ✅ Complete | Binance futures activated, API key configured, finbuddy_memory mounted in container |
| 9 | `tasks/phase-9-futures-risk.md` | ✅ Complete | RiskEngine wired into custom_stake_amount: get_regime() + stake_multiplier() + DD gate |
| 10 | `tasks/phase-10-live-migration.md` | ⬜ Pending | Dry-run → live capital migration, kill switch, go-live protocol |

---

## 🎯 What Each Agent Does (Summary)

| Tool | Role | Focus |
|---|---|---|
| **Perplexity AI** | Architect & Repo Maintainer | Designs phases, writes/updates code & docs, keeps memory in sync |
| **Claude Code** | Ops, Monitoring, Executor | Runs commands on server, deploys, monitors, runs backtests, updates task status |

Workflow is now explicitly baked into:
- `COLLABORATION_CONTRACT.md` (roles & boundaries)
- `CLAUDE.md` (deep project context, history, and architecture)
- `tasks/TASKS.md` (phase list + statuses)
- This file, `FINBUDDY_PROJECT_MEMORY.md` (high-level hub)

---

## 🔗 Related Files

- [[CLAUDE]] ← deep project context, history, and architecture
- [[COLLABORATION_CONTRACT]] ← roles, automation rules, AI vs code boundaries
- [[CLAUDE_HANDOFF]] ← current action queue + label/walk-forward decisions
- [[tasks/TASKS]] ← canonical phase list and statuses
- [[finbuddy_memory/CONTEXT]] ← live context injected into AI prompts
- [[finbuddy_memory/regimes/current]] ← live regime snapshot
- [[strategies/registry]] ← strategy registry & lifecycle

---

*This hub must be updated at the end of every major session. It is the high-level single source of truth for the project.*
