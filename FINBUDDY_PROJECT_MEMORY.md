# FinBuddy Project Hub

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟡 Phase 1 In Progress — Futures Live (Dry-Run), Walk-Forward Backtest Next  
**Last Updated:** 2026-05-02 15:55 IST by Perplexity AI — Step 5 Complete

---

## 🧠 What Is FinBuddy?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them via walk-forward backtest
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product
- **Primary market: Binance Futures (USDT-M Perpetual) — long AND short**
- Spot trading will be added later as a secondary module

---

## ✅ Step 5 Complete (2026-05-02)

**What Claude confirmed as live on server:**
- FreqTrade started cleanly — futures mode operational
- Pre-existing log permission bug fixed (chmod 666 on log files, chmod 777 on logs dir)
- `trading_mode: futures`, `margin_mode: isolated` confirmed in config
- All 22 pairs converted to `COIN/USDT:USDT` futures format
- Pairlist active: VolumePairList + SpreadFilter + PriceFilter + RangeStabilityFilter + VolatilityFilter
- `FinBuddyLLMModel` loaded ✅ — xAI Grok-3-mini [PRIMARY] → LGBM fallback waterfall confirmed in logs
- FreqAI downloading training data for futures candles
- API server running at `0.0.0.0:8080`, Telegram RPC active
- No fatal errors — bot is operational

**Commit:** `9f6b6ed` → `gaurav` branch

---

## 🚨 Strategic Pivot (2026-05-02)

### Why We Pivoted Away From Spot

Spot trading is structurally long-biased — you can only buy low, sell high. The 192-combo backtest failure across 3 rounds was not a strategy bug — it is an **architectural ceiling**. BTC fell -47.55% during the test period (2025-02-01 → 2026-04-01). No parameter tuning, no better ML model, no regime filter can fix a long-only strategy in a sustained -47% bear market. We were fighting physics.

**Root finding from Round 3:** ML signal quality is confirmed healthy (79–81% WR on signal-driven exits). The brain works. The market type was wrong.

### Why Futures (USDT-M Perp) Fixes This

| Feature | Spot | Futures (Perp) |
|---|---|---|
| Bear market | ❌ Can't profit | ✅ Short positions profit |
| Bull market | ✅ Works | ✅ Works (with leverage) |
| Sideways/range | ❌ Bleeds | ✅ Scalping + funding rates |
| Shorting | ❌ Not possible | ✅ Native |
| Leverage | ❌ None | ✅ 2–5x conservative use |
| Funding rate income | ❌ None | ✅ Passive when neutral |
| Market neutrality | ❌ | ✅ Long/short, delta-neutral |

---

## 🎯 Full Vision — All Crypto Market Modules

| Module | Type | Priority | Status |
|---|---|---|---|
| **Perp Futures (Long/Short)** | Directional | 🔥 Immediate | 🔄 In Progress |
| **Funding Rate Farming** | Passive income | ⚡ Phase 2 | ⬜ Pending |
| **Spot-Futures Basis Arb** | Market neutral | 🕐 Phase 7 | ⬜ Pending |
| **Statistical Arb (pair trading)** | Market neutral | 🕐 Phase 7 | ⬜ Pending |
| **Grid Trading** | Sideways/range | ⚡ Phase 5 | ⬜ Pending |
| **Spot Trading** | Long-only | 🕐 Phase 8 | ⬜ Secondary |
| **DCA / Accumulation** | Long-term | 🕐 Phase 8 | ⬜ Pending |
| **Options (hedging)** | Risk mgmt | 🕐 Future | ⬜ Advanced |

---

## 🧱 Core Engineering Principles

1. **Code over manual work:** Automate with cron/script; never waste AI tokens on repetitive tasks.
2. **AI for progress, not routine:** Use AI for design, debugging, monitoring, improvements.
3. **DRY & reusable design:** Shared logic in helpers/modules — no duplication across strategies.
4. **Documentation as memory:** All non-trivial behavior must be documented.
5. **Never hardcode secrets:** API keys always from environment variables, never committed files.

---

## 📚 Critical Freqtrade Rules (from develop docs — must follow)

These are rules from the official Freqtrade develop docs that directly impact our strategy code:

| Rule | Why It Matters |
|---|---|
| `INTERFACE_VERSION = 3` in every strategy | v2 strategies silently break in new versions |
| `can_short = True` at strategy class level | Without this, short signals are silently ignored |
| `startup_candle_count ≥ max_indicator_period` | Backtesting will use unstable (NaN-filled) candles without this |
| Never use `datetime.now()` in callbacks | Use `current_time` parameter — live vs backtest differ |
| Never use `iloc[-1]` or loops in `populate_*` | Must be vectorized pandas — loops break backtesting |
| Custom stoploss for futures: `return -0.04 * trade.leverage` | Without leverage multiply, stoploss is too tight |
| `adjust_trade_position()` for DCA | Requires `position_adjustment_enable: true` in config |
| Env vars override config.json override strategy | `FREQTRADE__EXCHANGE__KEY=...` format in Docker |
| Backtest flag `--enable-protections` | Includes cooldown/stoploss guard effects |
| `--timeframe-detail 1m` for precise SL/TP | Without this, stoploss fires may be imprecise in backtest |

---

## 🤖 AI Model Stack

> **Rule:** Never hardcode API keys. Always use environment variables.

| Model | Provider | Env Var | Cost | Role |
|---|---|---|---|---|
| **grok-3-mini** | xAI | `XAI_API_KEY` | $0.10/M | ✅ Real-time signal confirmation — PRIMARY |
| **grok-3** | xAI | `XAI_API_KEY` | $2/M | Optional upgrade if needed |
| **claude-sonnet-4-5** | Anthropic | `ANTHROPIC_API_KEY` | $3/$15/M | ✅ Claude Code — deploy, monitor, debug |
| **gemini-2.5-flash** | Google | `GEMINI_API_KEY` | Free tier | Future large-context research |
| **deepseek-chat** | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M | Future bulk hypothesis generation |

**Grok must have `x_search` and `web_search_preview` tools enabled on xAI API.**

---

## ⚠️ Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ NEEDS REVIEW | Code in GitHub, NOT yet deployed/verified on server |
| 🟡 IN PROGRESS | Actively being worked on |
| ⬜ PENDING | Not started |
| 🔴 RETIRED | Superseded — do not continue |

---

## 🚀 Current System State (as of 2026-05-02 — Step 5)

| Component | Status | Notes |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run | Futures mode, Oracle Free Tier |
| **Futures config** | ✅ Live | trading_mode: futures, margin_mode: isolated |
| **22 futures pairs** | ✅ Active | All in COIN/USDT:USDT format |
| **FinBuddyLLMModel** | ✅ Loaded | Grok-3-mini waterfall confirmed |
| **FreqAI** | ✅ Training | Downloading data per pair |
| **API Server** | ✅ 0.0.0.0:8080 | Accessible |
| **Telegram RPC** | ✅ Active | Native FreqTrade Telegram |
| **Log permissions** | ✅ Fixed | chmod 666/777 applied |
| **LightGBM (Task 1.1)** | ✅ Live | Keep — reuse for futures |
| **N8N pipeline** | 🔴 Permanently disabled | FreqAI is sole signal source |
| **FinBuddyFreqAI.py (futures rewrite)** | ⚠️ Pending | Must add `can_short=True` + short signals |
| **Walk-forward backtest** | ⬜ Not run | NEXT PRIORITY before going live |
| **HMM Engine** | ⬜ Not built | Phase 3 |
| **Karpathy Loop** | ⬜ Not built | Phase 5 |
| **Obsidian auto-write** | ⬜ Not wired | Phase 4 |

---

## 🗺️ Revised Roadmap (Post-Pivot, Post-Step-5)

### 🔥 Immediate Next Steps

| Step | Action | Owner | Status |
|---|---|---|---|
| **NEXT 1** | Verify FinBuddyFreqAI.py has `can_short=True`, short entry signals, `startup_candle_count ≥ 400` | Claude Code | ⬜ |
| **NEXT 2** | Run futures walk-forward backtest (2024-01-01 → 2025-01-01 bull + 2025-01-01 → 2026-04-01 bear) | Claude Code | ⬜ |
| **NEXT 3** | Parse backtest CSV — validate: Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2 | Perplexity reads CSV | ⬜ |
| **NEXT 4** | If validated: switch `dry_run: false` → go live with small stake ($10–20/trade) | Claude Code | ⬜ |
| **NEXT 5** | Install Phase 2 external data fetchers + cron jobs | Claude Code | ⬜ |

### Phase Roadmap

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundation | ✅ Complete |
| 1 | FreqAI brain — futures long+short | 🟡 Step 5 done, backtest pending |
| 2 | Funding rate farming module | ⬜ Pending |
| 3 | HMM 5-regime engine | ⬜ Pending |
| 4 | External data + cron install | ⬜ Code ready, crons pending |
| 5 | Grid trading module | ⬜ Pending |
| 6 | Memory auto-write + Karpathy loop | ⬜ Code ready, crons pending |
| 7 | Spot-futures basis arbitrage | ⬜ Pending |
| 8 | Spot trading module | ⬜ Secondary |
| 9 | TradingView webhook + Multi-executor | ⬜ SaaS buildout |

---

## 📦 What's Built & Committed

### Task 1.2 — FinBuddyLLMModel.py (Grok layer) — ✅ Deployed & Running
- `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py`
- LightGBM + Grok-3-mini blended signal — confirmed in logs

### Task 1.3 — Backtest Scripts — ⚠️ Repurpose for futures
- `scripts/run_backtest.sh`, `scripts/backtest_config.json`, `scripts/parse_backtest.py`, `scripts/tune_stoploss.sh`
- Must update `--trading-mode futures` flag and add short logic

### Phase 2 — External Data Fetchers — ⚠️ Committed, not installed
- `scripts/phase2/` — fear/greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends
- Still valid — external signals are market-type agnostic

### Phase 4 — Memory Auto-Writer — ⚠️ Committed, not installed
- `scripts/phase4/memory_writer.py` + `setup_cron.sh`
- Install after futures strategy is validated live

---

## 🎯 Quick Links

| What | Where |
|---|---|
| **Core collaboration rules** | `COLLABORATION_CONTRACT.md` |
| **🚨 Handoff for Claude Code** | `CLAUDE_HANDOFF.md` ← READ THIS FIRST |
| **Full project context** | `CLAUDE.md` |
| **Active strategy (needs futures rewrite verify)** | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` |
| **LLM model (deployed + running)** | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` |
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
| **Perplexity AI** | Design, write + commit code/docs to GitHub; define automation; read/parse CSVs | SSH, docker restart, live logs |
| **Claude Code** | SSH, deploy, monitor, run experiments, run backtests, verify deployments | Replace cron/scripts for repetitive tasks |

**Workflow:** Perplexity writes → marks ⚠️ NEEDS REVIEW → Claude Code deploys/verifies once → cron/scripts handle repetition → Claude monitors and improves.

---

*Last updated: Perplexity AI — 2026-05-02 15:55 IST — Step 5 complete, futures mode live, walk-forward backtest is next*
