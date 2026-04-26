# FinBuddy — Session Log
**Date:** April 27, 2026
**Interface:** Cowork (Claude desktop app)
**Who:** Gaurav

---

## Session Summary

This was a planning and architecture session — no code was written or deployed. Everything decided here shapes the next several months of building.

---

## Key Decisions Made

### 1. Project Name is FinBuddy — Permanently
The old name "Jarvis" is retired forever. Never use it. The project is called **FinBuddy** everywhere — in code, docs, conversation, memory, and git commits.

### 2. FinBuddy Is NOT a Bot
Critical framing correction. FinBuddy is an **autonomous, self-evolving AI brain for crypto trading**. FreqTrade placing orders is just the hands. The brain observes markets, forms hypotheses, tests them, promotes winners, retires losers, and improves itself continuously. This distinction must be preserved in all future context and documentation.

### 3. This Is a Fluid System
Nothing is sacred except the core idea. Tools, models, workflows, and components can be dropped, swapped, or added at any time. We already dropped OpenRouter (→ Groq) and Dify. We will drop N8N. Always optimize for what moves the brain forward, not what preserves existing work.

### 4. FreqTrade CAN and SHOULD Be the Brain (via FreqAI)
Question asked: Can FreqTrade itself be the brain, not a separate system?
Answer: YES. FreqAI (already installed, sitting empty) is a full ML research and training framework baked into FreqTrade. It supports LightGBM, XGBoost, CatBoost, PyTorch, and Reinforcement Learning natively. Most importantly, you can write a fully custom `IFreqaiModel` class that calls any external API (Groq, Gemini, anything) inside `fit()` and `predict()`. FreqAI becomes the signal brain.

**Will upgrades erase custom files?**
NO. FreqTrade runs in Docker. `user_data/` is a mounted volume. Upgrades only change the FreqTrade core image. Custom strategies, FreqAI models, configs — all survive upgrades permanently.

### 5. N8N Will Be Retired After Phase 1
Question asked: Do we really need N8N?
Answer: No, not long-term. N8N was the right rapid-prototyping tool to get the first dry-run trade opened. But as FreqAI takes over signal generation, FreqTrade handles Telegram natively, and Python scripts handle the Karpathy loop and data fetching — N8N becomes a 200MB Docker container doing jobs that are handled better elsewhere.

**Exit plan:**
- Keep N8N running through Phase 0 and Phase 1 (it's still the live signal pipeline)
- When FreqAI passes walk-forward backtest and goes live → N8N's primary job is gone
- Turn on FreqTrade's native Telegram (Phase 0, Task 0.2)
- Deactivate N8N signal workflow
- Monitor for 1 week
- Shut down N8N container, free the RAM

### 6. Free External Data Sources to Integrate
All free, no paid APIs:
- **Alternative.me Fear & Greed Index** — single API call, completely free
- **CoinGecko** — market cap dominance, social data, free tier
- **CryptoPanic** — news headlines with bullish/bearish tags, free API key
- **DefiLlama** — total DeFi TVL, completely free, no auth
- **Google Trends via pytrends** — search interest as leading indicator, free
- **TradingView webhooks** — Pine Script alerts fire webhooks to our server, free tier = 1 alert

### 7. AI Models to Integrate into FreqAI
**Native FreqAI (no extra install):**
- LightGBM — start here, fast, great for tabular data
- XGBoost — good ensemble partner
- CatBoost — handles categorical features
- PyTorch MLP — neural net for complex patterns
- Reinforcement Learning (Stable Baselines3) — learns from trade outcomes

**External API calls (inside custom IFreqaiModel):**
- Groq Llama 3.3 70B — signal confirmation layer (free)
- Gemini 2.5 Flash — deep research in Karpathy loop (free tier)
- DeepSeek R1 — nightly strategy reasoning (near-free)
- Claude Sonnet 4.6 — Pine Script writing, strategy promotion (sparingly)

---

## Project Task Structure Created

Full task breakdown created in `tasks/` directory:

| Phase | File | Focus |
|---|---|---|
| 0 | `tasks/phase-0-foundation.md` | Fix loose ends — Trade Event Handler, Telegram, pairlist, N8N cleanup |
| 1 | `tasks/phase-1-freqai-brain.md` | FreqAI as signal brain — LightGBM + custom LLM model |
| 2 | `tasks/phase-2-data-enrichment.md` | Free external data — Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends, TradingView |
| 3 | `tasks/phase-3-hmm-regime.md` | HMM 5-regime engine — CRASH/BEAR/NEUTRAL/BULL/EUPHORIA |
| 4 | `tasks/phase-4-obsidian-memory.md` | Complete Obsidian vault auto-write pipeline |
| 5 | `tasks/phase-5-karpathy-loop.md` | Self-improving research loop — Gemini → DeepSeek → backtest → promote |
| 6 | `tasks/phase-6-tradingview.md` | TradingView webhook receiver and Pine Script alerts |
| 7 | `tasks/phase-7-executor.md` | Python Signal-as-a-Service executor for multi-tenant shape |

---

## Files Created/Updated This Session

| File | Action | Notes |
|---|---|---|
| `CLAUDE.md` | Created | Full master project context for Claude Code |
| `tasks/TASKS.md` | Created | Master task index |
| `tasks/phase-0-foundation.md` | Created | Foundation cleanup tasks |
| `tasks/phase-1-freqai-brain.md` | Created | FreqAI brain tasks |
| `tasks/phase-2-data-enrichment.md` | Created | External data tasks |
| `tasks/phase-3-hmm-regime.md` | Created | HMM engine tasks |
| `tasks/phase-4-obsidian-memory.md` | Created | Obsidian vault tasks |
| `tasks/phase-5-karpathy-loop.md` | Created | Karpathy loop tasks |
| `tasks/phase-6-tradingview.md` | Created | TradingView tasks |
| `tasks/phase-7-executor.md` | Created | Python executor tasks |
| `session_log_2026-04-27.md` | Created | This file |

---

## What Claude Code Should Do Next (When You SSH In)

1. Read `CLAUDE.md` — full project context
2. Read `tasks/TASKS.md` — phase overview and rules
3. Start with `tasks/phase-0-foundation.md` — Task 0.1 (Trade Event Handler webhook URL)
4. Phase 0 is all quick wins, nothing complex — clear the backlog before building new things

---

## Current System State (as of this session)

| Component | Status |
|---|---|
| FreqTrade | ✅ Running, dry-run, AiGuardrailStrategy |
| N8N v3 pipeline | ✅ Running (will be retired after Phase 1) |
| Groq Llama 3.3 70B | ✅ Live signal AI |
| Trade Event Handler | ❌ Imported but not activated |
| FreqAI | ❌ Installed, completely empty |
| HMM Engine | ❌ Not built |
| Karpathy Loop | ❌ Not built |
| Obsidian Vault | ⚠️ Structure created, auto-write not wired |
| TradingView webhook | ❌ Not set up |
| Python Executor | ❌ Not built |
| Telegram in FreqTrade | ❌ Not wired into config |
