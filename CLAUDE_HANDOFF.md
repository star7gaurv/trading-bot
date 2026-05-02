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

## 📊 Round 2 Results (v7 — run by Claude Code 2026-05-02)

### Acceptance thresholds: WR > 50% | Sharpe > 0.5 | Drawdown < 20% ✅ | Profit Factor > 1.2

| Metric | Bull (2024) | Bear (2025-26) | Target |
|---|---|---|---|
| Win Rate | 48.2% ❌ | 50.0% ❌ | > 50% |
| Sharpe | -0.896 ❌ | -0.554 ❌ | > 0.5 |
| Max Drawdown | 6.25% ✅ | 7.10% ✅ | < 20% |
| Profit Factor | 0.649 ❌ | 0.736 ❌ | > 1.2 |
| Total P&L | -47.32 USDT | -36.25 USDT | Positive |
| Stop-loss hits | 41 × -1.60% | 42 × -1.60% | — |
| Long / Short | 47 / 38 | 65 / 31 | — |
| Trades | 85 | 96 | — |

**Result: ALL criteria FAIL in both periods.**

### 🐂 BULL — `20240101-20250101`
```
Trades       : 85 (41W / 44L)
Win Rate     : 48.2% ❌
Sharpe       : -0.896 ❌
Max Drawdown : 6.25% ✅
Profit Factor: 0.649 ❌
Total P&L    : -47.32 USDT
Long/Short   : 47 / 38
Stop-losses  : 41 × -1.60% = -130.41 USDT total damage
Signal exits : Long 31 trades at 0.84% avg (79.2% WR) ✅ — ML quality confirmed
               Short 22 trades at 0.16% avg (59.1% WR)
Trailing SL  : 12 trades at 1.38% avg (100% WR) ✅
```

### 🐻 BEAR — `20250101-20260401`
```
Trades       : 96 (48W / 48L)
Win Rate     : 50.0% ❌ (borderline)
Sharpe       : -0.554 ❌
Max Drawdown : 7.10% ✅
Profit Factor: 0.736 ❌
Total P&L    : -36.25 USDT
Long/Short   : 65 / 31
Stop-losses  : 42 × -1.60% = -131.79 USDT total damage
Signal exits : Long 31 trades at 0.84% avg (93.5% WR) ✅ — extraordinarily strong
               Short 17 trades at 0.55% avg (76.5% WR) ✅ — shorts working
Trailing SL  : 6 trades at 2.05% avg (100% WR) ✅
```

---

## ⚠️ Root Cause Analysis — Round 2 (written by Claude Code)

**The v7 stoploss tightening made things WORSE, not better.**

| Issue | Round 1 (-0.035 SL) | Round 2 (-0.015 SL) |
|---|---|---|
| Stop-loss hits (bull) | 13 hits | 41 hits |
| Stop-loss damage (bull) | -93.16 USDT | -130.41 USDT |
| Stop-loss hits (bear) | 14 hits | 42 hits |
| Stop-loss damage (bear) | -93.15 USDT | -131.79 USDT |

**Why:** At 15m timeframe, a -1.5% stoploss is within normal candle-level noise. The price oscillates past it regularly before the signal plays out. Fewer but larger stops (R1) were actually less damaging than many tiny stops (R2).

**The ML signal quality is excellent:**
- Bear longs via exit_signal: 93.5% WR at +0.84% avg = +52.20 USDT (if stops didn't interfere)
- Bear shorts via exit_signal: 76.5% WR at +0.55% avg = +18.71 USDT
- These signals WORK — the stoploss is destroying profitable setups

**Root cause: Stop-loss approach is wrong for this timeframe/strategy.**

**For Perplexity — suggested directions for v8:**
1. **No fixed SL + time-based exit:** Exit after N candles if signal reverses. Let ML decide exit, not stop.
2. **ATR-based stoploss:** `stoploss = -(2 × ATR / close)` — adapts to volatility. Needs `custom_stoploss()`.
3. **Wider SL + position sizing:** Use -0.03 SL but reduce stake to 100 USDT (half). Same max loss, fewer chops.
4. **Exit on signal flip only:** Disable stoploss entirely (set to -0.99) and exit purely on `&-s_close` sign reversal.

**Bonus finding:** `backtest_config.json` had a hardcoded `stoploss: -0.035` that overrode the strategy's stoploss for ALL of Round 1 too — Round 1 was actually tested at -3.5% SL (not -2.5% as intended). This is now fixed to -0.015 for this run.

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
