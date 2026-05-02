# FinBuddy — Master Context
> Injected into every AI prompt before signal generation.
> Auto-written by memory_writer.py (not yet wired — currently updated manually).
> Last updated: 2026-05-02 (Step 5 complete — Futures mode live)

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
Strategy   : FinBuddyFreqAI (AiGuardrailStrategy → pending futures rewrite)
Mode       : Dry-run on Binance FUTURES (USDT-M Perpetual)
Timeframe  : 5m (primary)
Pairs      : 22 futures pairs (BTC/USDT:USDT, ETH/USDT:USDT + 20 others)
Trading    : Long + Short enabled (can_short = True)
Margin     : Isolated
Leverage   : Conservative 2–5x
FreqAI     : ✅ Training per-pair on rolling window
LLM Layer  : ✅ FinBuddyLLMModel loaded — xAI Grok-3-mini [PRIMARY] → LGBM fallback
Confidence : ≥ 65% required to act
Backtest   : PENDING walk-forward on futures
Status     : Bot RUNNING (dry-run), futures mode confirmed
```

---

## Build Roadmap (current phase status)

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundation — fix loose ends | ✅ Complete |
| 1 | FreqAI as signal brain (futures long+short) | 🔄 In Progress — Step 5 done |
| 2 | External data enrichment | ⬜ Pending |
| 3 | HMM 5-regime engine | ⬜ Pending |
| 4 | Obsidian auto-write pipeline | ⬜ Pending |
| 5 | Karpathy auto-research loop | ⬜ Pending |
| 6 | TradingView webhook | ⬜ Pending |
| 7 | Python signal executor | ⬜ Pending |

Full task details in `tasks/` directory.

---

## Key Architecture Decisions (Locked)

**FreqAI is the signal brain** — runs inside FreqTrade. Supports LightGBM + custom models that call external APIs (Grok).

**N8N is permanently retired** — disabled as of 2026-05-02. FreqAI is sole signal source.

**Futures-first architecture** — trading_mode: futures, margin_mode: isolated, all pairs in COIN/USDT:USDT format. Spot is secondary module, Phase 8.

**Custom files survive FreqTrade upgrades** — user_data/ is a Docker volume mount. Strategies, FreqAI models, configs all persist.

**IMPORTANT — Freqtrade dev docs rules (must follow):**
- Always use `INTERFACE_VERSION = 3` in all strategy files
- `startup_candle_count` must be >= max indicator lookback period (set ≥ 400)
- Never use `datetime.now()` in callbacks — use the `current_time` parameter
- Never use `iloc[-1]` or loops in `populate_*` — vectorized pandas only
- `can_short = True` is required at strategy class level for short signals to work
- `adjust_trade_position()` is the correct DCA method — needs `position_adjustment_enable: true` in config
- Custom stoploss for futures: always multiply by `trade.leverage`
- Environment variables override config.json which overrides strategy — never hardcode secrets
- `startup_candle_count` unstable candles are excluded from backtest automatically

---

## Signal Pipeline (Current — FreqAI + Grok)
```
Binance Futures OHLCV (5m, 22 pairs)
    ↓
FreqAI: LightGBM trains on rolling window per pair
    ↓
FinBuddyLLMModel: LightGBM signal → Grok-3-mini confirmation (xAI API)
    ↓
If confidence ≥ 65%:
    → enter_long = 1 OR enter_short = 1
    → Isolated margin, 2–5x leverage
    → ATR-based stoploss (custom_stoploss × leverage)
    → Telegram notification (native FreqTrade)
```

## Signal Pipeline (Target — Full Brain)
```
Binance Futures OHLCV + external data (Fear & Greed, CoinGecko, CryptoPanic, DefiLlama)
    ↓
FreqAI: LightGBM trains on rolling 30-day window
    ↓
FinBuddyLLMModel: LightGBM + Grok confirmation layer
    ↓
HMM regime filter (CRASH = no entry, BEAR = reduce size, BULL = full)
    ↓
ATR-based position sizing (Turtle 2% rule × leverage)
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
| Trade signals + real-time analysis | xAI Grok-3-mini | $0.10/M |
| Deep research + Pine Script | Claude Sonnet 4.6 | Sparingly |
| Bulk hypothesis generation | DeepSeek chat | ~$0.01/M |
| Large context research | Gemini 2.5 Flash | Free tier |

---

## System State (as of 2026-05-02 — Step 5 Complete)
| Component | Status |
|---|
---|
| FreqTrade | ✅ Running, dry-run, FUTURES mode, 22 pairs |
| FinBuddyLLMModel | ✅ Loaded — Grok-3-mini waterfall confirmed in logs |
| Futures config | ✅ trading_mode: futures, margin_mode: isolated |
| Pair format | ✅ All pairs in COIN/USDT:USDT format |
| Pairlist filters | ✅ VolumePairList + SpreadFilter + PriceFilter + RangeStabilityFilter + VolatilityFilter |
| API server | ✅ Running at 0.0.0.0:8080 |
| Telegram RPC | ✅ Active |
| FreqAI training | ✅ Downloading training data per pair |
| N8N pipeline | 🔴 Permanently disabled |
| HMM Engine | ❌ Not built (Phase 3) |
| Karpathy Loop | ❌ Not built (Phase 5) |
| Obsidian auto-write | ❌ Not wired (Phase 4) |
| Walk-forward backtest | ❌ Pending (next priority) |

---

## Risk Flags
- Futures leverage amplifies both gains AND losses — conservative 2–5x only
- Walk-forward backtest not yet run on futures — do NOT go live before validation
- Custom stoploss must multiply by `trade.leverage` or it will be too tight

## Recent Insights
- Step 5 success confirms infrastructure is solid — futures mode operational
- Bot ran cleanly after fixing pre-existing log permission issue (chmod 666/777)
- Next bottleneck: FinBuddyFreqAI.py strategy rewrite for futures long+short is NOT yet deployed

## What's Working
→ [[strategies/winners]]
- Nothing walk-forward validated yet on futures.

## What Failed
→ [[strategies/graveyard]]
- Spot strategy retired — structural long-bias failure in bear market (-47.55% BTC drop)

## Signal History
→ [[signals/log]]

## Regime Transition Log
→ [[regimes/history]]

---

*Read by the AI pipeline before every signal generation call.*
*For full project context → see CLAUDE.md in repo root.*
*For task details → see tasks/ directory.*
*Server setup → [[SERVER_SETUP]]*
