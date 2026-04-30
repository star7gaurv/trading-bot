# FinBuddy — Master Task Index

> This is the execution roadmap for building the FinBuddy autonomous AI brain.
> Each phase has its own file. Claude Code should read the relevant task file before starting work.
> Tasks within each phase are ordered — do them top to bottom unless marked [PARALLEL].

---

## Phase Overview

| Phase | File | Status | Description |
|---|---|---|---|
| 0 | [phase-0-foundation.md](phase-0-foundation.md) | ✅ Complete | Fix loose ends, clean up, wire everything together |
| 1 | [phase-1-freqai-brain.md](phase-1-freqai-brain.md) | 🔴 In Progress | Make FreqAI the signal brain — replace N8N Groq calls |
| 2 | [phase-2-data-enrichment.md](phase-2-data-enrichment.md) | ⬜ Pending | Feed free external data (sentiment, news, on-chain) into FreqAI |
| 3 | [phase-3-hmm-regime.md](phase-3-hmm-regime.md) | ⬜ Pending | Build 5-regime HMM engine, wire into strategy and memory vault |
| 4 | [phase-4-obsidian-memory.md](phase-4-obsidian-memory.md) | ⬜ Pending | Complete Obsidian vault auto-write pipeline |
| 5 | [phase-5-karpathy-loop.md](phase-5-karpathy-loop.md) | ⬜ Pending | Karpathy auto-research loop — self-improving brain |
| 6 | [phase-6-tradingview.md](phase-6-tradingview.md) | ⬜ Pending | TradingView webhook integration |
| 7 | [phase-7-executor.md](phase-7-executor.md) | ⬜ Pending | Python Signal-as-a-Service executor for multi-tenant |

---

## Rules for Claude Code Working on These Tasks

1. Read CLAUDE.md first — always
2. Read the phase file before starting any task in that phase
3. All new code goes in `freqtrade/user_data/` — never outside
4. Never touch `finbuddy_memory/` files manually — they are auto-generated
5. Every strategy change must have a walk-forward backtest plan
6. Keep things simple enough to debug from a mobile SSH session
7. After completing a task, update the status in this file and the phase file
8. Hard cost ceiling: $3–5/month — no paid APIs unless explicitly approved

---

## Current Focus
**Phase 0:** ✅ Complete  
**Phase 1:** 🔄 In Progress

What's done:
- FinBuddyFreqAI strategy running with TA signals + FreqAI LightGBM training
- Docker image: `develop_freqai` (LightGBM included)
- All config working: telegram, webhook, api_server, freqai all enabled
- N8N Trading Loop v4 disabled — FreqTrade is now autonomous signal source
- N8N Trade Event Handler still active (receives webhooks, sends Telegram)

What's remaining:
- Wire `set_freqai_targets()` + `&-s_close` ML predictions into entry/exit (Task 1.1 final step)
- Task 1.2: Custom FreqAI model with Groq LLM confirmation layer
- Task 1.3: Walk-forward backtest validation
