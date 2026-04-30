# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** ✅ Phase 0 Complete (5 of 5) — Phase 1 Unlocked  
**Last Updated:** 2026-04-27 (verification and task file synchronization)

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
