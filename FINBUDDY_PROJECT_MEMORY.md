# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** ✅ Phase 0 Complete — Phase 1 In Progress (Task 1.2 complete)  
**Last Updated:** 2026-05-01 (Task 1.2 committed by Perplexity AI)

---

## 🧠 What Is FinBuddy?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product

---

## 🚀 Current State

| Component | Status |
|---|---|
| **FreqTrade** | ✅ Running, dry-run, FinBuddyFreqAI strategy |
| **LightGBM (FreqAI)** | ✅ Live — training per pair, predicting &-s_close |
| **N8N v4 Pipeline** | 🔴 Disabled — FreqAI is now sole signal source |
| **Groq AI** | ✅ Wired via FinBuddyLLMModel (Task 1.2 complete) |
| **FinBuddyLLMModel** | ✅ Committed — awaiting deployment + activation |
| **Strategy Registry** | ✅ rsi_macd_ai_v1 → replaced by FinBuddyFreqAI |
| **Memory Vault** | ✅ Obsidian structure ready |
| **Phase 1** | 🟡 In Progress — Task 1.3 (backtest) remaining |

---

## 📋 Phase 1 Status

- [x] Task 1.1 — FinBuddyFreqAI.py — LightGBM ML brain live (2026-04-30)
- [x] Task 1.2 — FinBuddyLLMModel.py — Groq LLM confirmation layer (2026-05-01)
- [ ] Task 1.3 — Walk-forward backtest (win rate >50%, Sharpe >0.5, drawdown <20%, PF >1.2)
- [ ] Registry — mark rsi_macd_ai_v1 as `validated` after backtest passes

---

## 🎯 Quick Links

| What | Where |
|---|---|
| **Full project context** | `CLAUDE.md` in repo root |
| **Phase tasks** | `tasks/phase-0-foundation.md` through `tasks/phase-7-executor.md` |
| **Memory vault** | `finbuddy_memory/` (Obsidian vault) |
| **Strategy registry** | `strategies/registry.json` |
| **FreqAI strategy** | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` |
| **LLM model** | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` |
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
Name       : FinBuddyFreqAI
ML Model   : LightGBMRegressor (FreqAI)
LLM Layer  : FinBuddyLLMModel → Groq Llama 3.3 70B (confidence > 0.6%)
Timeframe  : 15 minutes
Target     : &-s_close > 0.8% (3-candle = 45 min prediction)
Blend      : LightGBM 60% + LLM 40%
Status     : Live (dry-run) — PENDING walk-forward backtest
```

---

## 🗺️ 7-Phase Roadmap

| Phase | Focus | Status | ETA |
|---|---|---|---|
| 0 | Foundation | ✅ 5/5 Complete | Done (2026-04-27) |
| 1 | FreqAI brain | 🟡 Task 1.3 remaining | ~1 day |
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
- LightGBM trains on OHLCV + 14 TA indicators
- FinBuddyLLMModel adds Groq LLM confirmation on high-confidence signals
- Can call any external API (Groq, Gemini, DeepSeek)

✅ **This is a fluid system**
- Tools dropped: OpenRouter, Dify, N8N (now disabled)
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

## 🎬 Next Action

**Task 1.3 — Walk-Forward Backtest**

Task 1.2 complete. FinBuddyLLMModel.py committed to gaurav branch.

**Before activating FinBuddyLLMModel, complete these steps on the server:**
1. `cd /home/ubuntu/var/www/html/trade/freqtrade && git pull`
2. Set `GROQ_API_KEY` in docker-compose.yml environment section
3. Add `freqtrade/user_data/freqaimodels/` to docker-compose volumes
4. In `config.json`: change `"freqaimodel": "FinBuddyLLMModel"`
5. `docker restart freqtrade`
6. Run Task 1.3 backtest to validate

**Next:** Run `tasks/phase-1-freqai-brain.md` → Task 1.3 backtest command.

---

*This file serves as the master reference for FinBuddy project state.*  
*For detailed session logs, see session_log files in repo root.*
