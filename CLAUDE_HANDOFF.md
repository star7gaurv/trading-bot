# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Claude Code  
**Date:** 2026-05-02  
**For:** Perplexity AI (next session)  
**Branch:** `gaurav`

---

## ✅ What Was Done This Session (Claude Code — May 2, 2026)

| Task | Status |
|---|---|
| Switched FreqTrade to futures mode (trading_mode: futures, margin_mode: isolated) | ✅ Done |
| Fixed log permission issue preventing container startup | ✅ Done |
| Strategy: `can_short = True`, `startup_candle_count = 400` | ✅ Done |
| Strategy: `enter_short` + `exit_short` added | ✅ Done |
| `backtest_config.json` updated for futures (pairs, pricing) | ✅ Done |
| `parse_backtest.py` format bug fixed | ✅ Done |
| Futures walk-forward backtest: bull + bear periods | ✅ Done |
| All changes committed and pushed to `gaurav` branch | ✅ Done |

---

## 🔥 Your Job This Session (Perplexity)

Read the backtest results below and design Round 2 fixes. The WR is healthy (63%) but Sharpe and Profit Factor both fail. The root cause is clear — see analysis below.

---

## 📊 Futures Backtest Results — Round 1 (2026-05-02)

### Strategy: FinBuddyFreqAI v6 | 5 pairs: BTC/ETH/SOL/BNB/XRP USDT:USDT | 15m | Isolated Futures

---

### 🐂 BULL PERIOD — `20240101-20250101` (Market: +122.88%)

```
Trading Mode      : Isolated Futures
Pairs             : BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT, BNB/USDT:USDT, XRP/USDT:USDT
Starting Balance  : 1000 USDT
Final Balance     : 989.59 USDT
Absolute P&L      : -10.41 USDT
Total Profit %    : -1.04%
CAGR %            : -1.04%

--- Acceptance Criteria ---
Win Rate          : 63.0%     threshold > 50%   ✅ PASS
Sharpe (closed)   : -0.145    threshold > 0.5   ❌ FAIL
Max Drawdown      : 3.73%     threshold < 20%   ✅ PASS
Profit Factor     : 0.909     threshold > 1.2   ❌ FAIL

--- Trade Stats ---
Total Trades      : 73  (46W / 27L)
Long Trades       : 37  |  P&L: +3.19 USDT (+0.32%)
Short Trades      : 36  |  P&L: -13.60 USDT (-1.36%)
Avg Duration      : 3h 50m
Avg Stake         : 197.97 USDT

--- Exit Reasons ---
exit_signal       : 46 trades | Avg +0.48% | 69.6% WR
trailing_stop_loss: 14 trades | Avg +1.41% | 100% WR
stop_loss         : 13 trades | Avg -3.59% |   0% WR  ← PROBLEM

--- By Entry Tag ---
freqai_lgbm_v6_long  + exit_signal       : 24 trades | +0.77% avg | 79.2% WR
freqai_lgbm_v6_long  + trailing_stop     :  6 trades | +1.36% avg | 100% WR
freqai_lgbm_v6_short + trailing_stop     :  8 trades | +1.44% avg | 100% WR
freqai_lgbm_v6_short + exit_signal       : 22 trades | +0.16% avg | 59.1% WR
freqai_lgbm_v6_short + stop_loss         :  6 trades | -3.59% avg |   0% WR
freqai_lgbm_v6_long  + stop_loss         :  7 trades | -3.59% avg |   0% WR

--- Drawdown ---
Max Drawdown      : 37.93 USDT (3.73%)
Drawdown Duration : 261 days
Drawdown Start    : 2024-03-15
Drawdown End      : 2024-12-02
```

---

### 🐻 BEAR PERIOD — `20250101-20260401` (Market: -39.27%)

```
Trading Mode      : Isolated Futures
Pairs             : BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT, BNB/USDT:USDT, XRP/USDT:USDT
Starting Balance  : 1000 USDT
Final Balance     : 976.82 USDT
Absolute P&L      : -23.18 USDT
Total Profit %    : -2.32%
CAGR %            : -1.86%

--- Acceptance Criteria ---
Win Rate          : 63.4%     threshold > 50%   ✅ PASS
Sharpe (closed)   : -0.258    threshold > 0.5   ❌ FAIL
Max Drawdown      : 8.23%     threshold < 20%   ✅ PASS
Profit Factor     : 0.829     threshold > 1.2   ❌ FAIL

--- Trade Stats ---
Total Trades      : 82  (52W / 30L)
Long Trades       : 56  |  P&L: -33.07 USDT (-3.31%)
Short Trades      : 26  |  P&L: +9.89 USDT (+0.99%)
Avg Duration      : 4h 27m

--- Exit Reasons ---
exit_signal       : 62 trades | Avg +0.43% | 74.2% WR
trailing_stop_loss:  6 trades | Avg +2.22% | 100% WR
stop_loss         : 14 trades | Avg -3.60% |   0% WR  ← PROBLEM

--- By Entry Tag ---
freqai_lgbm_v6_long  + exit_signal       : 39 trades | +0.37% avg | 76.9% WR
freqai_lgbm_v6_long  + trailing_stop     :  5 trades | +2.42% avg | 100% WR
freqai_lgbm_v6_short + exit_signal       : 23 trades | +0.52% avg | 69.6% WR
freqai_lgbm_v6_short + trailing_stop     :  1 trade  | +1.20% avg | 100% WR
freqai_lgbm_v6_short + stop_loss         :  2 trades | -3.60% avg |   0% WR
freqai_lgbm_v6_long  + stop_loss         : 12 trades | -3.60% avg |   0% WR

--- Drawdown ---
Max Drawdown      : 85.99 USDT (8.23%)
Drawdown Duration : 261 days
Drawdown Start    : 2025-03-02
Drawdown End      : 2025-11-19
```

---

## 🔍 Root Cause Analysis

### Problem 1: Stop-loss hits are destroying P&L
- Every stop-loss exit = -3.59% to -3.60% (hard floor at -3.5%, fees push to -3.6%)
- Bull: 13 stop-losses × -3.59% = -93 USDT total loss from stops alone
- Bear: 14 stop-losses × -3.60% = -100 USDT total loss from stops alone
- Exit signals and trailing stops are profitable — stops are the ONLY loss source

### Problem 2: Short signals under-firing in bear market
- Bear period (market -39.27%): only 26 shorts vs 56 longs — should be inverted
- Current short conditions are too restrictive:
  - `close < ema_200` — in a bear, price is below 200 EMA but this might conflict with other filters
  - `close_1h <= ema_50_1h` — 1h EMA might lag too much
  - `rsi_14 > 32` + `bb_pct > 0.10` — possibly filtering out good short entries

### What IS working
- Win rate: 63%+ in both bull AND bear — signal quality is confirmed good
- Trailing stop exits: 100% win rate, +1.4–2.2% avg — when trades run in our direction, we capture well
- Exit signal: 69-74% WR at +0.43–0.48% avg — ML exit timing is solid
- Drawdown: 3.73% bull / 8.23% bear — well within limits, capital is protected
- Shorts working when they fire: +9.89 USDT in bear even with only 26 trades

---

## 🎯 Suggested Round 2 Levers (for Perplexity to evaluate)

1. **Tighten stoploss** from -3.5% to -2.0% or -1.5%
   - Reduces avg loser from -3.59% toward -2.0%
   - Risk: more premature stops on valid trades

2. **Loosen short entry filter** — relax one or more of:
   - Remove `close < ema_200` requirement (too slow to trigger in early bear)
   - Change `close_1h <= ema_50_1h` to `close_1h < ema_50_1h * 1.01` (small buffer)
   - Lower RSI floor from `rsi_14 > 32` to `rsi_14 > 20`

3. **Add BTC trend filter** — only allow shorts when BTC 4h is below its 50 EMA
   - Avoids shorting alts in a local BTC bounce

4. **Raise ML threshold for longs in bear** — if BTC trend is down, require stronger long signal (`&-s_close > 0.015` instead of `> 0.010`)

---

## 📁 Current File State

| File | Version | State |
|---|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | v6 | ✅ futures-ready — `can_short=True`, `startup=400`, long+short signals |
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | v2 | ✅ Deployed — xAI Grok waterfall |
| `freqtrade/user_data/backtest_config.json` | futures | ✅ futures mode, USDT:USDT pairs |
| `scripts/backtest_config.json` | futures | ✅ same as above (canonical source) |
| `scripts/parse_backtest.py` | fixed | ✅ format bug fixed |
| `scripts/autobacktest.py` | v4.1 | ✅ ready to repurpose for futures grid |

---

## 🔄 Collaboration Rules

| Who | Does What |
|---|---|
| **Gaurav** | Decides when to run, approves phase transitions |
| **Claude Code** | SSH, deploy, config changes, run scripts, verify on server |
| **Perplexity** | Designs strategy, writes code, updates docs, commits to GitHub |

---

*Written by Claude Code — 2026-05-02*
