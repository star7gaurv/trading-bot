# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟡 Phase 1 In Progress — Task 1.2 + 1.3 scripts NEED REVIEW  
**Last Updated:** 2026-05-01 17:06 IST by Perplexity AI

---

## 🧠 What Is FinBuddy?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them via walk-forward backtest
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product

---

## 🧱 Core Engineering Principles

1. **Code over manual work:** If it can be automated with code (cron, script, config), do it once and do **not** waste AI tokens or manual effort on it again.
2. **AI for progress, not routine:** Use AI (Perplexity, Claude, Grok) for design, debugging, monitoring, and improvements — not for tasks that a simple script or cron job can handle.
3. **DRY & reusable design:** Project code should follow “Do Not Repeat Yourself”. Shared logic must live in reusable helpers/modules so we don’t duplicate code across strategies, scripts, or phases.
4. **Documentation as memory:** Any non-trivial behavior (strategy logic, cron setup, API integration, experiments) must be documented, so we never forget what’s already implemented and can safely reuse it instead of rewriting.
5. **Never hardcode secrets:** API keys, passwords, and tokens must always come from environment variables, never from committed files.

These rules are part of the "core context" for all future work in this repo.

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
- Powers **Claude Code**, which:
  - Deploys code to the server.
  - Runs backtests / hyperopt when needed.
  - Monitors logs and surfaces bugs.
  - Improves automation when needed (e.g., tightening cron/scripts), but never replaces cron with AI.

### Gemini / DeepSeek — future usage
- Gemini 2.5 Flash (1M context) and DeepSeek are **available but not active** yet.
- Any future use will be explicitly documented in this file and in phase task files.

---

## ⚠️ Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ NEEDS REVIEW | Code written by Perplexity AI, committed to GitHub, NOT yet on server |
| 🟡 IN PROGRESS | Being actively worked on |
| ⬜ PENDING | Not started |

---

## 🚀 Current State

| Component | Status | Verified By |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run, FinBuddyFreqAI | Claude Code (2026-04-30) |
| **LightGBM (Task 1.1)** | ✅ Live — training per pair | Claude Code (2026-04-30) |
| **N8N v4 Pipeline** | 🔴 Disabled — FreqAI is sole signal source | Claude Code (2026-04-30) |
| **FinBuddyLLMModel.py (Task 1.2)** | ⚠️ In GitHub — NOT deployed | Perplexity (2026-05-01) |
| **Backtest script (Task 1.3)** | ⚠️ In GitHub — NOT run yet with new stoploss | Perplexity (2026-05-01) |
| **Phase 2 Data Fetchers** | ⚠️ In GitHub — NOT installed | Perplexity (2026-05-01) |
| **Phase 4 Memory Writer** | ⚠️ In GitHub — NOT installed | Perplexity (2026-05-01) |

---

## 🗺️ 7-Phase Roadmap

| Phase | Focus | Status | AI Models Used |
|---|---|---|---|
| 0 | Foundation | ✅ 5/5 Complete (2026-04-27) | — |
| 1 | FreqAI brain | 🟡 Task 1.2 ⚠️, 1.3–1.4 pending | Grok-3-Mini |
| 2 | External data | ⚠️ Code ready — needs cron install | — |
| 3 | HMM regime | ⬜ Not started | — |
| 4 | Memory auto-write | ⚠️ Code ready — needs cron install | — |
| 5 | Karpathy loop | ⬜ Not started | Grok + (maybe Gemini/DeepSeek + Claude Sonnet) |
| 6 | TradingView | ⬜ Not started | — |
| 7 | Python executor | ⬜ Not started | — |

---

## 📦 What Perplexity Built (2026-05-01)

### Task 1.2 — FinBuddyLLMModel.py (Grok layer)
| File | Purpose |
|---|---|
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | Custom FreqAI model: LightGBM + Grok-3-Mini blended signal |

### Task 1.3 — Backtest Scripts & Tuning
| File | Purpose |
|---|---|
| `scripts/run_backtest.sh` | One-command backtest runner with pre-flight checks |
| `scripts/backtest_config.json` | Isolated backtest config (no live keys, Telegram off) |
| `scripts/parse_backtest.py` | Auto-reads result JSON, prints PASS/FAIL with color / CSV |
| `scripts/tune_stoploss.sh` | Runs multiple backtests with different stoploss values (one-off experiment tool) |
| `scripts/README.md` | Script usage guide |

### Phase 2 — External Data Fetchers
| File | Source | Features Added to FreqAI |
|---|---|---|
| `scripts/phase2/fetch_fear_greed.py` | Alternative.me | `ext_fear_greed`, `ext_fear_greed_regime`, `ext_fear_greed_trend_7d` |
| `scripts/phase2/fetch_coingecko.py` | CoinGecko | `ext_btc_dominance`, `ext_btc_dom_normalized`, `ext_mcap_signal` |
| `scripts/phase2/fetch_cryptopanic.py` | CryptoPanic | `ext_news_sentiment`, `ext_news_bull_ratio`, `ext_news_bear_ratio` |
| `scripts/phase2/fetch_defillama.py` | DefiLlama | `ext_defi_tvl_billions`, `ext_defi_tvl_signal_24h`, `ext_defi_tvl_signal_7d` |
| `scripts/phase2/fetch_google_trends.py` | pytrends | `ext_trends_btc`, `ext_trends_contrarian`, `ext_trends_7d_change` |
| `scripts/phase2/external_data_aggregator.py` | All 5 combined | `ext_composite_score` (-1 to +1) |

### Phase 4 — Memory Auto-Writer
| File | Purpose |
|---|---|
| `scripts/phase4/memory_writer.py` | Reads FreqTrade API, writes vault entries, git commits |
| `scripts/phase4/setup_cron.sh` | Installs 2 cron jobs (every 15 min) |
| `finbuddy_memory/signals/log.md` | Signal audit log (initialized) |
| `finbuddy_memory/regimes/current.md` | Current regime tracker (initialized) |

---

## 🎯 Quick Links

| What | Where |
|---|---|
| **Core collaboration rules** | `COLLABORATION_CONTRACT.md` |
| **🚨 Handoff for Claude Code** | `CLAUDE_HANDOFF.md` ← READ THIS FIRST |
| **Full project context** | `CLAUDE.md` |
| **Phase 1 tasks** | `tasks/phase-1-freqai-brain.md` |
| **LLM model (needs deploy)** | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` |
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

*Last updated: Perplexity AI — 2026-05-01 ~17:06 IST*
