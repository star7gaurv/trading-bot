# Planning Session — April 27, 2026

> Full architecture and roadmap planning session via Cowork.
> These decisions shape the next several months of building.

---

## Decisions Made

### FinBuddy Is an Autonomous AI Brain (Not a Bot)
Locked framing. FinBuddy observes markets, forms hypotheses, tests them, promotes winners, retires losers, and improves itself. FreqTrade executing trades is just the hands. The brain is the product.

### This Is a Fluid System
Nothing is sacred except the core idea. Tools and models can be dropped, swapped, or added freely. We already dropped OpenRouter and Dify. We will drop N8N. Always optimize for what moves the brain forward.

### FreqAI = The Signal Brain
FreqAI is already installed inside FreqTrade but completely empty. It supports:
- LightGBM, XGBoost, CatBoost (tabular ML — fast, great baseline)
- PyTorch MLP (neural nets for complex patterns)
- Reinforcement Learning via Stable Baselines3 (learns from trade outcomes directly)
- Custom `IFreqaiModel` that can call ANY external API (Groq, Gemini, DeepSeek)

Custom files in `user_data/` survive FreqTrade Docker upgrades — `user_data/` is a volume mount.

### N8N Will Be Retired After Phase 1
N8N was a rapid prototyping tool. Once FreqAI is validated and live, N8N's jobs are covered:
- Signal generation → FreqAI
- Telegram → FreqTrade native config
- Cron/orchestration → Python scripts
Exit point: FreqAI passes walk-forward backtest → deactivate N8N signal workflow → monitor 1 week → shut down.

### Free External Data Sources Approved
- Alternative.me Fear & Greed Index
- CoinGecko (market cap, dominance, social)
- CryptoPanic (news sentiment, bullish/bearish)
- DefiLlama (DeFi TVL — macro signal)
- Google Trends via pytrends
- TradingView webhooks (Pine Script alerts → server)

---

## 7-Phase Build Roadmap

| Phase | Focus |
|---|---|
| 0 | Foundation — wire Trade Event Handler, Telegram, pairlist audit, N8N cleanup |
| 1 | FreqAI brain — LightGBM + custom LLM confirmation layer |
| 2 | External data enrichment — all free sources |
| 3 | HMM 5-regime engine — CRASH/BEAR/NEUTRAL/BULL/EUPHORIA |
| 4 | Obsidian auto-write pipeline — memory_writer.py + git auto-commit |
| 5 | Karpathy auto-research loop — Gemini → DeepSeek → backtest → promote |
| 6 | TradingView webhook integration |
| 7 | Python signal executor — multi-tenant shape |

Full task files in `tasks/` directory. Start with Phase 0.

---

## What Claude Code Should Do When You SSH In

1. Read `CLAUDE.md` — full project context and all decisions
2. Read `tasks/TASKS.md` — phase overview and working rules
3. Start with `tasks/phase-0-foundation.md` — Task 0.1 (Trade Event Handler)
4. Phase 0 is all quick wins — clear the backlog before building new things
5. After Phase 0: move to `tasks/phase-1-freqai-brain.md`

---

*This note was auto-created from the Cowork planning session.*
*→ Full session log: session_log_2026-04-27.md in repo root*

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[research/README]]*
