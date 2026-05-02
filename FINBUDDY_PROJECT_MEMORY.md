# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** ✅ Phase 0 Complete (5 of 5) — Phase 1 Unlocked  
**Last Updated:** 2026-04-27 (verification and task file synchronization)
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
| **Full project context** | `CLAUDE.md` in repo root |
| **Phase tasks** | `tasks/phase-0-foundation.md` through `tasks/phase-7-executor.md` |
| **Memory vault** | `finbuddy_memory/` (Obsidian vault) |
| **Strategy registry** | `strategies/registry.json` |
| **Live audit results** | `finbuddy_memory/research/2026-04-27-live-audit.md` |
| **Server** | Oracle Free Tier, REDACTED-SERVER_IP |
| **FreqTrade UI** | https://trade.star7gaurav.in |
| **N8N UI** | https://n8n.star7gaurav.in |

---

## 🔷 Current Regime

```
Regime     : UNKNOWN
Confidence : —
Status     : HMM engine not yet built (Phase 3)
```

---

## 📈 Active Strategy

```
Name       : rsi_macd_ai_v1
Indicators : RSI(14), MACD(12,26,9), ATR(14)
AI Layer   : Groq Llama 3.3 70B
Timeframe  : 15 minutes
Threshold  : ≥ 65% confidence
Status     : Active (N8N v4) — PENDING walk-forward validation
```

---

## 🗺️ 7-Phase Roadmap

| Phase | Focus | Status | ETA |
|---|---|---|---|
| 0 | Foundation | ✅ 5/5 Complete | Done (2026-04-27) |
| 1 | FreqAI brain | 🟡 Ready to Start | 2-3 days |
| 2 | External data | ⬜ Pending | ~1 day |
| 3 | HMM regime | ⬜ Pending | ~2-3 days |
| 4 | Memory auto-write | ⬜ Pending | Parallel |
| 5 | Karpathy loop | ⬜ Pending | ~2-3 days |
| 6 | TradingView | ⬜ Pending | Parallel |
| 7 | Python executor | ⬜ Pending | Last |

---

## 🎓 Key Decisions (Locked)

✅ **FreqAI = The signal brain** (Phase 1)
- Replaces N8N → Groq call
- Supports LightGBM, XGBoost, PyTorch, RL, custom models
- Can call any external API (Groq, Gemini, DeepSeek)

✅ **This is a fluid system**
- Tools dropped: OpenRouter, Dify
- Tools being retired: N8N (after Phase 1)
- Always optimize for moving the brain forward

✅ **Multi-tenant SaaS shape from day one**
- Signal-as-a-Service architecture (one brain, many users)
- Phase 1 = single user (Gaurav), multi-tenant-shaped code
- Phase 2+ = add signup, billing, dashboard

---

## 💰 Cost Ceiling

**Target: $3–5/month total**

| Service | Cost |
|---|---|
| Oracle Free Tier | Free |
| Groq (6000 req/day) | Free |
| Gemini 2.5 Flash | Free tier |
| DeepSeek | Near-free |
| CoinGecko, CryptoPanic, DefiLlama | Free tier |
| TradingView | Free (1 alert) |

**Zero paid infra.**

---

## 📊 Memory Vault Structure

```
finbuddy_memory/
├── CONTEXT.md              ← Master hub (injected into AI prompts)
├── SERVER_SETUP.md         ← Setup instructions
├── regimes/
│   ├── current.md          ← Current regime (UNKNOWN)
│   └── history.md          ← Regime transitions (empty)
├── strategies/
│   ├── winners.md          ← Validated strategies (0 yet)
│   └── graveyard.md        ← Failed strategies (0 yet)
├── signals/
│   └── log.md              ← Signal audit trail (empty)
├── research/
│   ├── 2026-04-27-planning-session.md
│   └── 2026-04-27-live-audit.md  ← Latest audit
└── scripts/
    ├── memory_writer.py    ← Auto-write pipeline (Phase 4)
    └── setup.sh            ← Auto-commit cron setup
```

---

## 🔧 How to Use This

1. **For full context:** Read `CLAUDE.md` in repo root
2. **For current task:** Read `tasks/phase-0-foundation.md`
3. **For memory state:** Check `finbuddy_memory/CONTEXT.md`
4. **For architecture:** Read `docs/ADR-001-multi-tenant-architecture.md`
5. **For decisions:** Check `finbuddy_memory/research/2026-04-27-live-audit.md`

---

## 🎬 Next Action

**Begin Phase 1: FreqAI Brain Development**

Phase 0 is complete. All foundation tasks verified:
- ✅ Trade Event Handler wired and active
- ✅ Telegram enabled in FreqTrade
- ✅ Pairlist audit complete (scam tokens blacklisted)
- ✅ N8N workspace clean (2 active workflows)
- ✅ User config ready

**Next:** Read `tasks/phase-1-freqai-brain.md` to begin building the FreqAI signal brain that will replace N8N's Groq calls with LightGBM + custom LLM layer.

---

*This file serves as the master reference for FinBuddy project state in Cowork context.*  
*For detailed session logs, see `finbuddy_memory/research/` directory.*
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
