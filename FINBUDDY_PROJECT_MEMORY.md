# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟡 Phase 1 In Progress — Task 1.2 + 1.3 scripts NEED REVIEW  
**Last Updated:** 2026-05-01 13:57 IST by Perplexity AI

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

| Model | Provider | API Base | Env Var | Role in FinBuddy |
|---|---|---|---|---|
| **grok-3-mini** | xAI (Elon Musk) | `https://api.x.ai/v1` | `XAI_API_KEY` | ✅ **Primary — Task 1.2 signal confirmation** |
| **grok-3** | xAI | `https://api.x.ai/v1` | `XAI_API_KEY` | Optional upgrade when free credits allow |
| **gemini-2.5-flash** | Google | Gemini API | `GEMINI_API_KEY` | ✅ **Phase 5 — Karpathy research loop** |
| **deepseek-chat** | DeepSeek | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` | ✅ **Phase 5 — hypothesis generator (ultra cheap)** |

### Why This Stack?
- **Grok-3-Mini for signal confirmation:** Trained on real-time X/Twitter data — knows current market sentiment better than any other model. Fast, cheap, OpenAI-compatible API.
- **Gemini 2.5 Flash for research:** 1M token context — can read entire backtest logs + strategy code in one call. Free tier very generous.
- **DeepSeek for hypothesis gen:** Cheapest available (~$0.01/M tokens), surprisingly strong reasoning. Good for bulk Phase 5 hypothesis generation.

### xAI API curl example (for reference):
```bash
curl https://api.x.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -d '{
    "model": "grok-3-mini",
    "messages": [{"role": "user", "content": "Your message here"}],
    "max_tokens": 500,
    "stream": false
  }'
```

### Tools available on xAI API:
- `web_search_preview` — live web search
- `x_search` — real-time X/Twitter search (unique to Grok)

### FinBuddyLLMModel.py — use this client setup:
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

### Free tier limits (xAI as of 2026-05):
- $25 free credits on signup
- 60 requests/minute
- More than enough for FinBuddy's signal confirmation calls (~5-20/hour)

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

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundation | ✅ 5/5 Complete (2026-04-27) |
| 1 | FreqAI brain | 🟡 Task 1.2 ⚠️, 1.3–1.4 pending |
| 2 | External data | ⚠️ Code ready — needs cron install |
| 3 | HMM regime | ⬜ Not started |
| 4 | Memory auto-write | ⚠️ Code ready — needs cron install |
| 5 | Karpathy loop | ⬜ Not started (uses Gemini + DeepSeek) |
| 6 | TradingView | ⬜ Not started |
| 7 | Python executor | ⬜ Not started |

---

## 📦 What Perplexity Built (2026-05-01)

### Option C — Task 1.3 Backtest Scripts
| File | Purpose |
|---|---|
| `scripts/run_backtest.sh` | One-command backtest runner with pre-flight checks |
| `scripts/backtest_config.json` | Isolated backtest config (no live keys, Telegram off) |
| `scripts/parse_backtest.py` | Auto-reads result JSON, prints PASS/FAIL with color |
| `scripts/README.md` | Script usage guide |

### Option A — Phase 2 External Data Fetchers
| File | Source | Features Added to FreqAI |
|---|---|---|
| `scripts/phase2/fetch_fear_greed.py` | Alternative.me | `ext_fear_greed`, `ext_fear_greed_regime`, `ext_fear_greed_trend_7d` |
| `scripts/phase2/fetch_coingecko.py` | CoinGecko | `ext_btc_dominance`, `ext_btc_dom_normalized`, `ext_mcap_signal` |
| `scripts/phase2/fetch_cryptopanic.py` | CryptoPanic | `ext_news_sentiment`, `ext_news_bull_ratio`, `ext_news_bear_ratio` |
| `scripts/phase2/fetch_defillama.py` | DefiLlama | `ext_defi_tvl_billions`, `ext_defi_tvl_signal_24h`, `ext_defi_tvl_signal_7d` |
| `scripts/phase2/fetch_google_trends.py` | pytrends | `ext_trends_btc`, `ext_trends_contrarian`, `ext_trends_7d_change` |
| `scripts/phase2/external_data_aggregator.py` | All 5 combined | `ext_composite_score` (-1 to +1) |

### Option B — Phase 4 Memory Auto-Writer
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
| **Server** | Oracle Free Tier, 140.245.17.121 |
| **FreqTrade UI** | https://trade.star7gaurav.in |

---

## 💬 Who Does What

| Tool | Can Do | Cannot Do |
|---|---|---|
| **Perplexity AI** | Write + commit code/docs to GitHub | SSH, docker restart, live logs |
| **Claude Code** | SSH, deploy, docker, live verification | — |

**Workflow:** Perplexity writes → marks ⚠️ NEEDS REVIEW → Claude Code deploys → verifies → marks ✅ COMPLETE

---

*Last updated: Perplexity AI — 2026-05-01 ~13:57 IST*
