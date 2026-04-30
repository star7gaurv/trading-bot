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
Mode       : Dry-run on Binance, 15m timeframe, ~20 pairs (VolumePairList)
Confidence : ≥ 65% required to act
Backtest   : PENDING walk-forward validation
Status     : Active (N8N v4 pipeline — running every 15 min)
First Trade: BTC/USDT @ 67,206.72 USDT (April 4, 2026 dry-run)
```

---

## Build Roadmap (current phase status, updated 2026-04-27)

| Phase | Focus | Status | Blockers |
|---|---|---|---|
| 0 | Foundation — fix loose ends | ✅ **COMPLETE (5/5)** | None — all tasks verified done |
| 1 | FreqAI as signal brain | 🟡 Ready to Start | None — Phase 0 complete |
| 2 | External data enrichment | ⬜ Pending | All 6 sources approved & ready |
| 3 | HMM 5-regime engine | ⬜ Pending | Will unlock regime detection |
| 4 | Obsidian auto-write pipeline | ⬜ Pending | memory_writer.py → git auto-commit |
| 5 | Karpathy auto-research loop | ⬜ Pending | Will enable self-improvement |
| 6 | TradingView webhook | ⬜ Pending | Pine Script integration |
| 7 | Python signal executor | ⬜ Pending | Multi-tenant shape, ccxt integration |

Full task details in `tasks/` directory. Start with `tasks/phase-0-foundation.md`.

---

## Key Architecture Decisions (Locked)

**FreqAI is the signal brain** — replaces N8N → Groq call. Runs inside FreqTrade. Supports LightGBM, XGBoost, PyTorch, RL, and custom models that call external APIs.

**N8N is being retired** — transitional tool only. Exit: once FreqAI passes walk-forward backtest and goes live. Do NOT retire before then.

**Custom files survive FreqTrade upgrades** — user_data/ is a Docker volume mount. Upgrades only change the container image. Strategies, FreqAI models, configs all persist.

**This is a fluid system** — tools and models can be dropped or added freely. We dropped OpenRouter (→ Groq), dropped Dify. We will drop N8N. Always optimize for what moves the brain forward.

---

## Signal Pipeline (Current — N8N v4)
```
Binance OHLCV (15m)
    ↓
N8N v4: Calculate RSI(14), MACD(12,26,9), ATR(14)
         (runs every 15 minutes, context-aware)
    ↓
Groq Llama 3.3 70B (free, ~200ms, 6000 req/day)
    ↓
If confidence ≥ 65%:
    → FreqTrade /forceenter or /forceexit (API call)
    → Telegram notification (N8N bot: 7799143446:...)
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

## System State (as of 2026-04-27, updated via Cowork audit)
| Component | Status | Notes |
|---|---|---|
| FreqTrade | ✅ Running | Dry-run mode, AiGuardrailStrategy, API @ port 8080 |
| N8N v4 pipeline | ✅ Running | **v4 (not v3)** — running every 15 min, calling Groq |
| Groq signal AI | ✅ Live | Free tier, Llama 3.3 70B, ~200ms response |
| Trade Event Handler | ⚠️ Wired, errors | Config correct but has runtime error (workflow_failed 2026-04-26) |
| FreqAI | ❌ Empty | Installed in FreqTrade, ready for Phase 1 |
| HMM Engine | ❌ Not built | Phase 3 blocker — regime = UNKNOWN |
| Karpathy Loop | ❌ Not built | Phase 5 — auto-research pipeline |
| Obsidian auto-write | ❌ Not wired | Phase 4 — memory_writer.py pending |
| TradingView webhook | ❌ Not set up | Phase 6 — Pine Script alerts |
| Python Executor | ❌ Not built | Phase 7 — multi-tenant signal receiver |
| Telegram in FreqTrade | ✅ Active | Enabled with token 8557119080:... in config.json |
| Pairlist audit | ✅ Complete | D/USDT, CHIP, SOMI, ZBT blacklisted, verified in config |
| N8N cleanup | ✅ Complete | Only 2 active workflows remain: v4 loop + Trade Event Handler |

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
