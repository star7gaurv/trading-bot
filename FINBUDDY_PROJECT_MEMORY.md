# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟡 Phase 1 In Progress — Task 1.2 + 1.3 scripts NEED REVIEW  
**Last Updated:** 2026-05-01 14:02 IST by Perplexity AI

---

## 🧠 What Is FinBuddy?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them via walk-forward backtest
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product

---

## 🤖 AI Model Stack (Decided 2026-05-01)

> **Rule:** Never hardcode API keys. Always use environment variables.

| Model | Provider | Env Var | Cost | Role in FinBuddy |
|---|---|---|---|---|
| **grok-3-mini** | xAI | `XAI_API_KEY` | $0.10/M | ✅ **Task 1.2 — real-time signal confirmation** |
| **grok-3** | xAI | `XAI_API_KEY` | $2/M | Optional upgrade later |
| **claude-sonnet-4-5** | Anthropic | `ANTHROPIC_API_KEY` | $3/$15 per M | ✅ **Phase 5 — write strategy code improvements** |
| **gemini-2.5-flash** | Google | `GEMINI_API_KEY` | Free tier | ✅ **Phase 5 — read full backtest logs (1M context)** |
| **deepseek-chat** | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M | ✅ **Phase 5 — bulk hypothesis generation** |

### Why each model was chosen

**Grok-3-Mini → Task 1.2 (Signal Confirmation)**
- Only model trained on real-time X/Twitter data — knows live market sentiment
- Fast, cheap, OpenAI-compatible API (drop-in replacement)
- 60 req/min free tier — more than enough (~5–20 calls/hour for FinBuddy)
- Hard timeout 4s in code; falls back to raw LGBM signal on failure

**Claude Sonnet → Phase 5 (Strategy Code Writing)**
- Best model in the world for writing reliable, bug-free Python code
- Understands FreqTrade/FreqAI strategy structure deeply
- Does not hallucinate API calls or FreqAI method signatures
- Used for step 3 of the Karpathy loop: writing actual code changes
- Already used indirectly — Claude Code (which deploys everything on server) runs on Sonnet

**Gemini 2.5 Flash → Phase 5 (Backtest Log Analysis)**
- 1M token context window — can ingest entire backtest JSONs + strategy code in one call
- Free tier is very generous for weekly Phase 5 runs
- Best for step 1: reading and summarizing what went wrong in backtests

**DeepSeek → Phase 5 (Hypothesis Generation)**
- Cheapest available (~$0.01/M tokens), strong reasoning
- Best for step 2: generating 5+ hypotheses per week ("what if we add RSI filter?")
- Bulk usage without worrying about cost

### Phase 5 Karpathy Loop — how models work as a team
```
Every week (automated):
  Step 1: Gemini 2.5 Flash  → reads full backtest logs, finds weak spots
  Step 2: DeepSeek          → generates 5 improvement hypotheses
  Step 3: Claude Sonnet     → writes the actual strategy/model code changes
  Step 4: FreqTrade         → backtests new code automatically
  Step 5: parse_backtest.py → if metrics improve → promote to live
```

### API client setup for FinBuddyLLMModel.py (Task 1.2 — Grok)
```python
import openai  # xAI is OpenAI-compatible

client = openai.OpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1"
)

response = client.chat.completions.create(
    model=os.getenv("GROK_MODEL", "grok-3-mini"),
    messages=[{"role": "user", "content": prompt}],
    max_tokens=50,
    timeout=5
)
```

### Tools available on xAI API (Grok-specific, not available on others)
- `web_search_preview` — live web search
- `x_search` — real-time X/Twitter search

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
| **Backtest script (Task 1.3)** | ⚠️ In GitHub — NOT run yet | Perplexity (2026-05-01) |
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
| 5 | Karpathy loop | ⬜ Not started | Gemini + DeepSeek + Claude Sonnet |
| 6 | TradingView | ⬜ Not started | — |
| 7 | Python executor | ⬜ Not started | — |

---

## 📦 What Perplexity Built (2026-05-01)

### Task 1.2 — FinBuddyLLMModel.py (Grok layer)
| File | Purpose |
|---|---|
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | Custom FreqAI model: LightGBM + Grok-3-Mini blended signal |

### Task 1.3 — Backtest Scripts
| File | Purpose |
|---|---|
| `scripts/run_backtest.sh` | One-command backtest runner with pre-flight checks |
| `scripts/backtest_config.json` | Isolated backtest config (no live keys, Telegram off) |
| `scripts/parse_backtest.py` | Auto-reads result JSON, prints PASS/FAIL with color |
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
| **Perplexity AI** | Write + commit code/docs to GitHub | SSH, docker restart, live logs |
| **Claude Code** | SSH, deploy, docker, live verification | — |

**Workflow:** Perplexity writes → marks ⚠️ NEEDS REVIEW → Claude Code deploys → verifies → marks ✅ COMPLETE

---

*Last updated: Perplexity AI — 2026-05-01 ~14:02 IST*
