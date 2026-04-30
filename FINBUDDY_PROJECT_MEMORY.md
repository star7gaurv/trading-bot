# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟡 Phase 1 In Progress — Task 1.2 NEEDS REVIEW  
**Last Updated:** 2026-05-01 by Perplexity AI

---

## 🧠 What Is FinBuddy?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product

---

## 🚀 Current State

| Component | Status | Who Verified |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run, FinBuddyFreqAI | Claude Code (2026-04-30) |
| **LightGBM (FreqAI)** | ✅ Live — training per pair | Claude Code (2026-04-30) |
| **N8N v4 Pipeline** | 🔴 Disabled — FreqAI is sole signal source | Claude Code (2026-04-30) |
| **FinBuddyLLMModel.py** | ⚠️ Committed to GitHub — NOT deployed | Perplexity AI (2026-05-01) |
| **Groq LLM Layer** | ⚠️ Code ready — NOT live on server yet | Perplexity AI (2026-05-01) |
| **Walk-forward Backtest** | ⬜ Blocked on Task 1.2 deploy | — |

---

## ⚠️ Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ NEEDS REVIEW | Code written by Perplexity AI, in GitHub, NOT yet on server |
| 🟡 IN PROGRESS | Being actively worked on |
| ⬜ PENDING | Not started |

---

## 🗺️ 7-Phase Roadmap

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundation | ✅ 5/5 Complete (2026-04-27) |
| 1 | FreqAI brain | 🟡 Task 1.2 ⚠️ NEEDS REVIEW, 1.3–1.4 pending |
| 2 | External data | ⬜ Pending |
| 3 | HMM regime | ⬜ Pending |
| 4 | Memory auto-write | ⬜ Pending |
| 5 | Karpathy loop | ⬜ Pending |
| 6 | TradingView | ⬜ Pending |
| 7 | Python executor | ⬜ Pending |

---

## 💬 Who Does What

| Tool | Can Do | Cannot Do |
|---|---|---|
| **Perplexity AI** | Write + commit code to GitHub, update docs, read files, run Python in sandbox | SSH into server, docker restart, read live logs |
| **Claude Code** | SSH into server, deploy, docker commands, live log checking, fix runtime errors | — |

**Workflow:** Perplexity writes → commits to `gaurav` branch → Claude Code pulls → reviews → deploys → verifies → updates status to ✅ COMPLETE

---

## 🎯 Quick Links

| What | Where |
|---|---|
| **Handoff note for Claude Code** | `CLAUDE_HANDOFF.md` ← READ THIS FIRST |
| **Full project context** | `CLAUDE.md` |
| **Phase 1 tasks** | `tasks/phase-1-freqai-brain.md` |
| **FreqAI strategy** | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` |
| **LLM model (needs review)** | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` |
| **Strategy registry** | `strategies/registry.json` |
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
ML Model   : LightGBMRegressor (live, training per pair)
LLM Layer  : FinBuddyLLMModel → Groq Llama 3.3 70B
             Status: CODE READY — NOT YET DEPLOYED
Timeframe  : 15 minutes
Target     : &-s_close > 0.8% (3-candle / 45 min prediction)
Blend      : LightGBM 60% + LLM 40%
Status     : Dry-run RUNNING with LightGBM only
             Upgrade to LLM blend pending Task 1.2 deployment
```

---

## 🎃 Next Action for Claude Code

1. Read `CLAUDE_HANDOFF.md` — full step-by-step
2. `git pull origin gaurav` on the server
3. Review + deploy `FinBuddyLLMModel.py`
4. Verify Groq calls appear in FreqTrade logs
5. Run Task 1.3 backtest
6. Update this file — mark Task 1.2 as ✅ COMPLETE after live verification
7. Delete `CLAUDE_HANDOFF.md` after all steps done

---

## 🎓 Key Decisions (Locked)

✅ FreqAI = The signal brain (LightGBM trains locally, Groq confirms remotely)  
✅ This is a fluid system — N8N dropped, always optimize for brain forward  
✅ Multi-tenant SaaS shape from day one (Phase 2+ adds signup, billing, dashboard)  
✅ Cost ceiling: $0–5/month — zero paid infra  

---

*Always update this file after completing any task on the server.*  
*Last updated: Perplexity AI — 2026-05-01 01:00 IST*
