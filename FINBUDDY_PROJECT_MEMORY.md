# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🔴 Strategic Pivot — Futures-First Architecture  
**Last Updated:** 2026-05-02 15:31 IST by Perplexity AI

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

Futures makes FinBuddy **truly market-agnostic** — the brain calls direction AND regime, then positions accordingly in any market condition.

---

## 🎯 Full Vision — All Crypto Market Modules

FinBuddy will eventually support all major crypto market types as modular strategy plugins. One central AI brain, multiple execution modules:

| Module | Type | Priority | Status |
|---|---|---|---|
| **Perp Futures (Long/Short)** | Directional | 🔥 Immediate | 🔄 Rewriting now |
| **Funding Rate Farming** | Passive income | ⚡ Phase 2 | ⬜ Pending |
| **Spot-Futures Basis Arb** | Market neutral | 🕐 Phase 4 | ⬜ Pending |
| **Statistical Arb (pair trading)** | Market neutral | 🕐 Phase 5 | ⬜ Pending |
| **Grid Trading** | Sideways/range | ⚡ Phase 3 | ⬜ Pending |
| **Spot Trading** | Long-only | 🕐 Phase 6 | ⬜ Secondary |
| **DCA / Accumulation** | Long-term | 🕐 Phase 6 | ⬜ Pending |
| **Options (hedging)** | Risk mgmt | 🕐 Future | ⬜ Advanced |

All modules share: the same regime signal, the same AI brain, the same memory vault.

---

## 🧱 Core Engineering Principles

1. **Code over manual work:** If it can be automated with code (cron, script, config), do it once and do **not** waste AI tokens or manual effort on it again.
2. **AI for progress, not routine:** Use AI (Perplexity, Claude, Grok) for design, debugging, monitoring, and improvements — not for tasks that a simple script or cron job can handle.
3. **DRY & reusable design:** Project code should follow "Do Not Repeat Yourself". Shared logic must live in reusable helpers/modules so we don't duplicate code across strategies, scripts, or phases.
4. **Documentation as memory:** Any non-trivial behavior (strategy logic, cron setup, API integration, experiments) must be documented, so we never forget what's already implemented and can safely reuse it instead of rewriting.
5. **Never hardcode secrets:** API keys, passwords, and tokens must always come from environment variables, never from committed files.

---

## 🤖 AI Model Stack (Decided 2026-05-01)

> **Rule:** Never hardcode API keys. Always use environment variables.

| Model | Provider | Env Var | Cost | Role in FinBuddy |
|---|---|---|---|---|
| **grok-3-mini** | xAI | `XAI_API_KEY` | $0.10/M | ✅ **Task 1.2 — real-time signal confirmation & analysis** |
| **grok-3** | xAI | `XAI_API_KEY` | $2/M | Optional upgrade later |
| **claude-sonnet-4-5** | Anthropic | `ANTHROPIC_API_KEY` | $3/$15 per M | ✅ **Coding & ops via Claude Code (deploy, monitor, experiments)** |
| **gemini-2.5-flash** | Google | `GEMINI_API_KEY` | Free tier | Reserved for future large-context research if needed |
| **deepseek-chat** | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M | Reserved for cheap bulk hypothesis generation if needed |

### Grok (xAI) — analysis & signal confirmation
- Only model trained on real-time X/Twitter data — knows live market sentiment.
- Fast, cheap, OpenAI-compatible API (drop-in replacement).
- 60 req/min free tier — more than enough (~5–20 calls/hour for FinBuddy).
- **Must have both `x_search` and `web_search_preview` tools enabled** on the xAI API.
- Used inside `FinBuddyLLMModel.py` for signal confirmation + market reasoning.

### Claude Sonnet — code & infrastructure
- Best model for writing reliable, bug-free Python and ops scripts.
- Understands FreqTrade/FreqAI strategy structure deeply.
- Powers **Claude Code**, which deploys code, runs backtests, monitors logs, improves automation.

### Gemini / DeepSeek — future usage
- Gemini 2.5 Flash (1M context) and DeepSeek are **available but not active** yet.

---

## ⚠️ Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ NEEDS REVIEW | Code written by Perplexity AI, committed to GitHub, NOT yet on server |
| 🟡 IN PROGRESS | Being actively worked on |
| ⬜ PENDING | Not started |
| 🔴 PIVOTED | Superseded by strategic pivot — do not continue |

---

## 🚀 Current State

| Component | Status | Notes |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run | On server, Oracle Free Tier |
| **LightGBM (Task 1.1)** | ✅ Live — training per pair | Keep — reuse for futures strategy |
| **N8N v4 Pipeline** | 🔴 Disabled permanently | FreqAI is sole signal source |
| **FinBuddyFreqAI.py (v6)** | 🔴 SPOT — needs rewrite for futures | Long+short rewrite is next action |
| **FinBuddyLLMModel.py (Task 1.2)** | ⚠️ In GitHub — NOT deployed | Deploy on futures strategy, not spot |
| **Backtest scripts (Task 1.3)** | ⚠️ In GitHub — repurpose for futures | Change market type + add short logic |
| **Phase 2 Data Fetchers** | ⚠️ In GitHub — NOT installed | Still valid for futures signals |
| **Phase 4 Memory Writer** | ⚠️ In GitHub — NOT installed | Still valid, install after futures validated |

---

## 🗺️ Revised Roadmap (Post-Pivot)

### Immediate Priority (Before any other phase)

| Step | Action | Owner |
|---|---|---|
| 🔥 P0 | Switch FreqTrade config from spot to **Binance Futures USDT-M** | Claude Code |
| 🔥 P1 | Rewrite `FinBuddyFreqAI.py` for **long + short signals** | Perplexity |
| 🔥 P2 | Run **bull period backtest on futures** (2024-01-01 → 2025-01-01) | Claude Code |
| 🔥 P3 | Validate: Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2 | Perplexity reads CSV |

### Phase Roadmap (Revised)

| Phase | Focus | Status | Notes |
|---|---|---|---|
| 0 | Foundation | ✅ 5/5 Complete | Done |
| 1 | FreqAI brain — **futures long/short** | 🔄 Rewriting strategy | Task 1.1 ✅, strategy pivot in progress |
| 2 | Funding rate farming module | ⬜ Pending | Passive income on neutral regime |
| 3 | HMM 5-regime engine | ⬜ Pending | Critical for futures — regime drives long/short/neutral |
| 4 | External data + cron install | ⬜ Pending | Phase 2 code ready, needs crons |
| 5 | Grid trading module | ⬜ Pending | Sideways market strategy |
| 6 | Memory auto-write + Karpathy loop | ⬜ Pending | Phase 4 code ready, needs crons |
| 7 | Spot-futures basis arbitrage | ⬜ Pending | Market neutral |
| 8 | Spot trading module | ⬜ Pending | Secondary, after futures validated |
| 9 | TradingView webhook + Multi-executor | ⬜ Pending | SaaS buildout |

---

## 📦 What's Built & Committed (pre-pivot, still valid)

### Task 1.2 — FinBuddyLLMModel.py (Grok layer)
- `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` — LightGBM + Grok-3-Mini blended signal
- **Still valid** — deploy on futures strategy once rewrite is done

### Task 1.3 — Backtest Scripts
- `scripts/run_backtest.sh`, `scripts/backtest_config.json`, `scripts/parse_backtest.py`, `scripts/tune_stoploss.sh`
- **Repurpose** — update for futures market type and long+short logic

### Phase 2 — External Data Fetchers
- `scripts/phase2/` — fear/greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends
- **Still valid** — external signals are market-type agnostic

### Phase 4 — Memory Auto-Writer
- `scripts/phase4/memory_writer.py` + `setup_cron.sh`
- **Still valid** — install after futures strategy is validated live

---

## 🎯 Quick Links

| What | Where |
|---|---|
| **Core collaboration rules** | `COLLABORATION_CONTRACT.md` |
| **🚨 Handoff for Claude Code** | `CLAUDE_HANDOFF.md` ← READ THIS FIRST |
| **Full project context** | `CLAUDE.md` |
| **Active strategy (needs rewrite)** | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` |
| **LLM model (needs deploy on futures)** | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` |
| **Backtest runner** | `scripts/run_backtest.sh` |
| **External data fetchers** | `scripts/phase2/` |
| **Memory writer** | `scripts/phase4/memory_writer.py` |
| **xAI API console** | https://console.x.ai |
| **Server** | Oracle Free Tier, REDACTED-SERVER_IP |
| **FreqTrade UI** | https://trade.star7gaurav.in |

---

## 💬 Who Does What

| Tool | Can Do | Cannot Do |
|---|---|---|
| **Perplexity AI** | Design, write + commit code/docs to GitHub; define automation | SSH, docker restart, live logs |
| **Claude Code** | SSH, deploy, monitor, run experiments, improve automations when needed | Replace cron or scripts for repetitive tasks |

**Workflow:** Perplexity writes → marks ⚠️ NEEDS REVIEW → Claude Code deploys / verifies once → cron/scripts handle repetition → Claude monitors and improves.

---

*Last updated: Perplexity AI — 2026-05-02 15:31 IST — Strategic pivot to futures-first architecture*
