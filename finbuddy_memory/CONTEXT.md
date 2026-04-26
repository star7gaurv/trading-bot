# FinBuddy — Master Context
> Injected into every AI prompt before signal generation.
> Auto-written by memory_writer.py (not yet wired — currently updated manually).
> Last updated: 2026-04-27 (Cowork planning session)

---

## What FinBuddy Is
FinBuddy is an **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
The brain observes markets, forms hypotheses, tests them, promotes winners, retires losers.
FreqTrade is just the hands (execution). The brain is the product.

---

## Current Regime
→ [[regimes/current]]

```
Regime     : UNKNOWN
Confidence : —
Since      : —
Note       : HMM engine not yet built (Phase 3)
```

---

## Active Strategy
```
Strategy   : rsi_macd_ai_v1
Description: RSI(14) + MACD(12,26,9) signals confirmed by Groq Llama 3.3 70B
Mode       : Dry-run on Binance, 15m timeframe, ~20 pairs
Confidence : ≥ 65% required to act
Backtest   : PENDING walk-forward validation
Status     : Active (N8N v3 pipeline)
```

---

## Build Roadmap (current phase status)

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundation — fix loose ends | 🔴 In Progress |
| 1 | FreqAI as signal brain | ⬜ Pending |
| 2 | External data enrichment | ⬜ Pending |
| 3 | HMM 5-regime engine | ⬜ Pending |
| 4 | Obsidian auto-write pipeline | ⬜ Pending |
| 5 | Karpathy auto-research loop | ⬜ Pending |
| 6 | TradingView webhook | ⬜ Pending |
| 7 | Python signal executor | ⬜ Pending |

Full task details in `tasks/` directory. Start with `tasks/phase-0-foundation.md`.

---

## Key Architecture Decisions (Locked)

**FreqAI is the signal brain** — replaces N8N → Groq call. Runs inside FreqTrade. Supports LightGBM, XGBoost, PyTorch, RL, and custom models that call external APIs.

**N8N is being retired** — transitional tool only. Exit: once FreqAI passes walk-forward backtest and goes live. Do NOT retire before then.

**Custom files survive FreqTrade upgrades** — user_data/ is a Docker volume mount. Upgrades only change the container image. Strategies, FreqAI models, configs all persist.

**This is a fluid system** — tools and models can be dropped or added freely. We dropped OpenRouter (→ Groq), dropped Dify. We will drop N8N. Always optimize for what moves the brain forward.

---

## Signal Pipeline (Current — N8N v3)
```
Binance OHLCV (15m)
    ↓
N8N: calculate RSI(14), MACD(12,26,9), ATR(14)
    ↓
Groq Llama 3.3 70B (free, ~200ms, 6000 req/day)
    ↓
If confidence ≥ 65%:
    → FreqTrade forceenter / forceexit
    → Telegram notification
```

## Signal Pipeline (Target — FreqAI)
```
Binance OHLCV + external data (Fear & Greed, CoinGecko, CryptoPanic, DefiLlama)
    ↓
FreqAI: LightGBM trains on rolling 30-day window
    ↓
Custom IFreqaiModel: LightGBM signal + Groq confirmation layer
    ↓
HMM regime filter (CRASH = no entry, BEAR = half size)
    ↓
ATR-based position sizing (Turtle 2% rule)
    ↓
FreqTrade executes + Telegram (native)
```

---

## Free External Data Sources (Approved)
- Alternative.me Fear & Greed Index — market sentiment (no auth)
- CoinGecko — BTC dominance, market cap, social data (free tier)
- CryptoPanic — news sentiment, bullish/bearish tags (free API key)
- DefiLlama — total DeFi TVL (no auth)
- Google Trends via pytrends — search interest as leading indicator (free)
- TradingView webhooks — Pine Script alerts → server (free = 1 alert)

---

## AI Model Assignment
| Task | Model | Cost |
|---|---|---|
| Trade signals | Groq Llama 3.3 70B | Free |
| Deep research | Gemini 2.5 Flash | Free tier |
| Nightly reasoning | DeepSeek R1 | Near-free |
| Social sentiment | Grok 4.1 Fast | TBD |
| Pine Script + promotion | Claude Sonnet 4.6 | Sparingly |

---

## System State (as of 2026-04-27)
| Component | Status |
|---|---|
| FreqTrade | ✅ Running, dry-run, AiGuardrailStrategy |
| N8N v3 pipeline | ✅ Running (temporary — retiring after Phase 1) |
| Groq signal AI | ✅ Live |
| Trade Event Handler | ❌ Not activated (Phase 0, Task 0.1) |
| FreqAI | ❌ Installed, empty (Phase 1) |
| HMM Engine | ❌ Not built (Phase 3) |
| Karpathy Loop | ❌ Not built (Phase 5) |
| Obsidian auto-write | ❌ Not wired (Phase 4) |
| TradingView webhook | ❌ Not set up (Phase 6) |
| Python Executor | ❌ Not built (Phase 7) |
| Telegram in FreqTrade | ❌ Not configured (Phase 0, Task 0.2) |

---

## Risk Flags
- None active.

## Recent Insights
- No Karpathy research cycles run yet — will populate once Phase 5 is active.

## What's Working
→ [[strategies/winners]]
- Nothing walk-forward validated yet.

## What Failed
→ [[strategies/graveyard]]
- Nothing retired yet.

## Signal History
→ [[signals/log]]

## Regime Transition Log
→ [[regimes/history]]

---

*Read by the AI pipeline before every signal generation call.*
*For full project context → see CLAUDE.md in repo root.*
*For task details → see tasks/ directory.*
*Server setup → [[SERVER_SETUP]]*
