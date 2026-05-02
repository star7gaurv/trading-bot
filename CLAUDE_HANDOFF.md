# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-02  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

---

## ✅ What Was Done (Perplexity — May 2, 2026)

| Task | Status |
|---|---|
| Analysed Round 1 backtest results | ✅ Done |
| Identified root cause: stoploss too wide (-3.59% avg loss vs +0.45% avg win) | ✅ Done |
| Identified root cause 2: short filter too restrictive (26 shorts in -39% bear) | ✅ Done |
| Strategy v7 written and committed to GitHub | ✅ Done |

---

## 🔥 Your Job This Session (Claude Code)

Run Round 2 backtest with the new v7 strategy. **Same two periods as Round 1:**
- Bull: `20240101-20250101`
- Bear: `20250101-20260401`

Steps in order:

### Step 1 — Pull latest code
```bash
cd /path/to/trading-bot
git pull origin gaurav
```

### Step 2 — Verify v7 file is correct
Check these 4 things in `freqtrade/user_data/strategies/FinBuddyFreqAI.py`:
- `stoploss = -0.015` (was -0.025)
- `informative_timeframes = ["1h", "4h"]` (added 4h)
- Short entry: `rsi_14 > 20` (was > 32)
- Short entry: `close_1h < ema_50_1h * 1.02` (was strict <=)
- Short entry: no `close < ema_200` line (was removed)
- Long entry: dynamic threshold block using `btc_4h_below_ema50`

### Step 3 — Download 4h BTC data (needed for new BTC trend filter)
```bash
docker exec freqtrade freqtrade download-data \
  --pairs BTC/USDT:USDT \
  --timeframes 4h \
  --timerange 20230901- \
  --trading-mode futures \
  --exchange binance
```

### Step 4 — Run bull backtest
```bash
docker exec freqtrade freqtrade backtesting \
  --config /freqtrade/user_data/backtest_config.json \
  --strategy FinBuddyFreqAI \
  --timerange 20240101-20250101 \
  --timeframe-detail 1m \
  --export trades \
  --cache none
```

### Step 5 — Run bear backtest
```bash
docker exec freqtrade freqtrade backtesting \
  --config /freqtrade/user_data/backtest_config.json \
  --strategy FinBuddyFreqAI \
  --timerange 20250101-20260401 \
  --timeframe-detail 1m \
  --export trades \
  --cache none
```

### Step 6 — Parse both results
```bash
# Parse bull
python3 scripts/parse_backtest.py  # will auto-find latest result

# Rename bull result JSON, then parse bear
# (same as Round 1 workflow)
```

### Step 7 — Write results into this file
Replace the ROUND 2 RESULTS section below with the actual numbers. Same format as Round 1. Then commit.

### Step 8 — Commit everything
```bash
git add -A
git commit -m "backtest: Round 2 results v7 strategy"
git push origin gaurav
```

---

## 📊 Round 1 Results (reference — what we're trying to beat)

### Acceptance thresholds: WR > 50% ✅ | Sharpe > 0.5 | Drawdown < 20% ✅ | Profit Factor > 1.2

| Metric | Bull (2024) | Bear (2025-26) | Target |
|---|---|---|---|
| Win Rate | 63.0% ✅ | 63.4% ✅ | > 50% |
| Sharpe | -0.145 ❌ | -0.258 ❌ | > 0.5 |
| Max Drawdown | 3.73% ✅ | 8.23% ✅ | < 20% |
| Profit Factor | 0.909 ❌ | 0.829 ❌ | > 1.2 |
| Total P&L | -10.41 USDT | -23.18 USDT | Positive |
| Stop-loss hits | 13 × -3.59% | 14 × -3.60% | — |
| Short trades | 36 / 73 total | 26 / 82 total | — |

**Root cause:** 13-14 stop losses × -3.59% = ~-95 USDT per period. Winners only generated ~+80 USDT. reward:risk was 0.13:1.

---

## 📊 Round 2 Results (v7 — fill in after running)

### 🐂 BULL — `20240101-20250101`
```
[FILL IN AFTER RUNNING]
```

### 🐻 BEAR — `20250101-20260401`
```
[FILL IN AFTER RUNNING]
```

---

## 📁 v7 Changes Summary (what Perplexity changed)

| Change | Old | New | Reason |
|---|---|---|---|
| `stoploss` | -0.025 | **-0.015** | Avg loser -3.59% → ~-1.6%. Main lever. |
| Short RSI floor | `rsi_14 > 32` | **`rsi_14 > 20`** | Was blocking valid short entries |
| Short 1h trend | `close_1h <= ema_50_1h` | **`close_1h < ema_50_1h * 1.02`** | 2% buffer, less strict |
| Short ema_200 guard | `close < ema_200` | **removed** | Fires too late in early bear |
| Long ML threshold | always `> 0.010` | **`> 0.010` bull / `> 0.015` bear** | Reduces false longs in downtrend |
| BTC 4h filter | none | **added `btc_4h_below_ema50`** | Macro regime awareness |
| `informative_timeframes` | `["1h"]` | **`["1h", "4h"]`** | Needed for BTC 4h filter |

---

## 🔄 Collaboration Rules

| Who | Does What |
|---|---|
| **Gaurav** | Decides when to run, approves phase transitions |
| **Claude Code** | SSH, deploy, run backtests, verify on server, commit results |
| **Perplexity** | Analyses results, designs strategy changes, writes code, updates docs |

---

*Written by Perplexity AI — 2026-05-02*
