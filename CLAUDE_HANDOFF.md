# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-02  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

---

## ✅ What Was Done (Perplexity — May 2, Round 3)

| Task | Status |
|---|---|
| Analysed Round 2 (v7) results | ✅ Done |
| Confirmed root cause: fixed SL gets chopped by 15m noise | ✅ Done |
| Strategy v8 written with ATR-adaptive `custom_stoploss()` | ✅ Done |
| Committed to GitHub | ✅ Done |

---

## 🔥 Your Job This Session (Claude Code)

Run Round 3 backtest with v8. **Same two periods:**
- Bull: `20240101-20250101`
- Bear: `20250101-20260401`

### Step 1 — Pull latest
```bash
cd /home/ubuntu/var/www/html/trade
git pull origin gaurav
```

### Step 2 — Verify v8 in the live volume path
```bash
grep -n 'use_custom_stoploss\|stoploss\|custom_stoploss' \
  /home/ubuntu/var/www/html/trade/freqtrade/user_data/strategies/FinBuddyFreqAI.py | head -20
```
Expect:
- `use_custom_stoploss = True`
- `stoploss = -0.08` (wide fallback only)
- `def custom_stoploss(` present

### Step 3 — Fix backtest_config.json stoploss override
Check and confirm `stoploss` key in `backtest_config.json` matches the strategy or is removed:
```bash
grep 'stoploss' /home/ubuntu/var/www/html/trade/freqtrade/user_data/backtest_config.json
```
If it shows anything other than `-0.08`, edit it to `-0.08` (must match strategy fallback).

### Step 4 — Purge FreqAI model cache
```bash
rm -rf /home/ubuntu/var/www/html/trade/freqtrade/user_data/models/finbuddy_backtest_v1
```

### Step 5 — Run bull backtest
```bash
docker exec freqtrade freqtrade backtesting \
  --config /freqtrade/user_data/backtest_config.json \
  --strategy FinBuddyFreqAI \
  --timerange 20240101-20250101 \
  --timeframe-detail 1m \
  --export trades \
  --cache none
```

### Step 6 — Run bear backtest
```bash
docker exec freqtrade freqtrade backtesting \
  --config /freqtrade/user_data/backtest_config.json \
  --strategy FinBuddyFreqAI \
  --timerange 20250101-20260401 \
  --timeframe-detail 1m \
  --export trades \
  --cache none
```

### Step 7 — Parse results
```bash
python3 scripts/parse_backtest.py  # auto-finds latest ZIP
```
Get both bull and bear summaries with the same format as before:
- Total trades, WR, Sharpe, Drawdown, Profit Factor, P&L
- Exit reason breakdown (stop_loss / trailing_stop_loss / exit_signal counts + avg %)
- Long vs Short split

### Step 8 — Write results here + commit
Replace the ROUND 3 RESULTS section below. Then:
```bash
git add -A
git commit -m "backtest: Round 3 results v8 ATR stoploss"
git push origin gaurav
```

---

## 📈 Round History

### Round 1 (v6, stoploss -0.035 from config)
| Metric | Bull 2024 | Bear 2025-26 | Target |
|---|---|---|---|
| Win Rate | 63.0% ✅ | 63.4% ✅ | > 50% |
| Sharpe | -0.145 ❌ | -0.258 ❌ | > 0.5 |
| Max DD | 3.73% ✅ | 8.23% ✅ | < 20% |
| PF | 0.909 ❌ | 0.829 ❌ | > 1.2 |
| P&L | -10.41 USDT | -23.18 USDT | positive |
| SL hits | 13 × -3.59% | 14 × -3.60% | — |

### Round 2 (v7, stoploss -0.015)
| Metric | Bull 2024 | Bear 2025-26 | Target |
|---|---|---|---|
| Win Rate | 48.2% ❌ | 50.0% ❌ | > 50% |
| Sharpe | -0.896 ❌ | -0.554 ❌ | > 0.5 |
| Max DD | 6.25% ✅ | 7.10% ✅ | < 20% |
| PF | 0.649 ❌ | 0.736 ❌ | > 1.2 |
| P&L | -47.32 USDT | -36.25 USDT | positive |
| SL hits | 41 × -1.60% | 42 × -1.60% | — |

**Lesson:** -1.5% fixed SL is within 15m candle noise. Tighter → more chops → worse. The signal quality is excellent (93.5% WR on signal exits in bear) — the stoploss is the only problem.

### Round 3 (v8, ATR custom_stoploss + fallback -0.08)
| Metric | Bull 2024 | Bear 2025-26 | Target |
|---|---|---|---|
| Win Rate | 42.0% ❌ | 52.1% ✅ | > 50% |
| Sharpe | -0.78 ❌ | -0.22 ❌ | > 0.5 |
| Max DD | 4.64% ✅ | 4.72% ✅ | < 20% |
| PF | 0.72 ❌ | 0.87 ❌ | > 1.2 |
| P&L | -33.05 USDT | -12.47 USDT | positive |
| trailing SL hits | **79 × -0.54%** | **62 × -0.55%** | — |
| stop_loss hits | 0 (fallback never hit) | 0 (fallback never hit) | — |
| exit_signal WR | 93.9% (33 trades) | 94.1% (34 trades) | — |

---

## 📈 Round 3 Results (v8) — Run 2026-05-02

### 🐂 BULL — `20240101-20250101` (Market: +122.88%)
```
Trading Mode      : Isolated Futures
Total Trades      : 112  (47W / 65L)
Long / Short      : 31 / 81
Starting Balance  : 1000 USDT
Final Balance     : 966.96 USDT
Absolute P&L      : -33.05 USDT
Total Profit %    : -3.30%

--- Acceptance Criteria ---
Win Rate          : 42.0%    ❌ FAIL (target > 50%)
Sharpe (closed)   : -0.78    ❌ FAIL (target > 0.5)
Max Drawdown      : 4.64%    ✅ PASS (target < 20%)
Profit Factor     : 0.72     ❌ FAIL (target > 1.2)

--- Exit Reasons ---
exit_signal       :  33 trades | Avg +0.78% | 93.9% WR  ← signal quality excellent
trailing_stop_loss:  79 trades | Avg -0.54% | 20.3% WR  ← THE PROBLEM
stop_loss         :   0 trades | (fallback -0.08 never reached)

--- Mixed Tag Breakdown ---
freqai_lgbm_v8_short + exit_signal       : 24 trades | +0.65% | 91.7% WR
freqai_lgbm_v8_long  + exit_signal       :  9 trades | +1.14% | 100%  WR
freqai_lgbm_v8_short + trailing_stop_loss: 57 trades | -0.48% | 24.6% WR
freqai_lgbm_v8_long  + trailing_stop_loss: 22 trades | -0.69% |  9.1% WR

--- Best/Worst ---
Best trade        : ETH/USDT:USDT  +2.84%
Worst trade       : SOL/USDT:USDT  -3.33%
Max consec W/L    : 4 / 7
Avg duration W/L  : 1h 30m / 1h 41m
```

### 🐻 BEAR — `20250101-20260401` (Market: -39.27%)
```
Trading Mode      : Isolated Futures
Total Trades      : 96  (50W / 46L)
Long / Short      : 53 / 43
Starting Balance  : 1000 USDT
Final Balance     : 987.53 USDT
Absolute P&L      : -12.47 USDT
Total Profit %    : -1.25%

--- Acceptance Criteria ---
Win Rate          : 52.1%    ✅ PASS (target > 50%)
Sharpe (closed)   : -0.22    ❌ FAIL (target > 0.5)
Max Drawdown      : 4.72%    ✅ PASS (target < 20%)
Profit Factor     : 0.87     ❌ FAIL (target > 1.2)

--- Exit Reasons ---
exit_signal       :  34 trades | Avg +0.82% | 94.1% WR  ← signal quality excellent
trailing_stop_loss:  62 trades | Avg -0.55% | 29.0% WR  ← THE PROBLEM
stop_loss         :   0 trades | (fallback -0.08 never reached)

--- Mixed Tag Breakdown ---
freqai_lgbm_v8_long  + exit_signal       : 18 trades | +0.97% | 100%  WR
freqai_lgbm_v8_short + exit_signal       : 16 trades | +0.65% | 87.5% WR
freqai_lgbm_v8_long  + trailing_stop_loss: 35 trades | -0.56% | 28.6% WR
freqai_lgbm_v8_short + trailing_stop_loss: 27 trades | -0.55% | 29.6% WR

--- Best/Worst ---
Best trade        : XRP/USDT:USDT  +3.13%
Worst trade       : XRP/USDT:USDT  -3.43%
Max consec W/L    : 7 / 8
Avg duration W/L  : 1h 32m / 1h 40m
```

---

## 🔍 Round 3 — Root Cause Analysis (Claude Code, 2026-05-02)

**v8 vs v7 (R2) deltas:**
| | Bull | Bear |
|---|---|---|
| WR | 48.2% → **42.0%** ❌ | 50.0% → **52.1%** ✅ |
| Sharpe | -0.896 → **-0.78** ⬆ | -0.554 → **-0.22** ⬆ much better |
| PF | 0.649 → **0.72** ⬆ | 0.736 → **0.87** ⬆ |
| P&L | -47.32 → **-33.05** ⬆ | -36.25 → **-12.47** ⬆ much better |

**The mode of failure changed shape. The total damage shrank.**

### What v8 did right
- Wide -0.08 fallback was correct: hard `stop_loss` count went **41/42 → 0/0** in both periods.
- Bear-period Sharpe improved by 0.33 absolute — biggest single-round improvement so far.
- Signal cohort `exit_signal` continues to be excellent: **93.9% / 94.1% WR**. The ML brain is not the problem.

### What v8 did wrong — the new chop source
- The ATR `custom_stoploss()` does both **initial-stop** AND **trailing-from-MFE** in one function.
- The strategy class still has `trailing_stop = True` with `trailing_stop_positive = 0.010` / `offset = 0.020`. **Two trailing systems running at once.**
- Net effect: every trade that ticks +1×ATR in profit triggers a Chandelier-style trail (1.5×ATR back) AND a 1% framework trail. Whichever is tighter fires first → 79/62 premature trailing exits at -0.54% / -0.55% avg.
- The 0-stop, all-trailing distribution is the smoking gun.

### Bull WR fell because shorts dominate the book
- Bull period had **31 long / 81 short** trades. Market was +122.88% but the strategy went short 72% of the time and the trailing chop gutted the WR.
- Bear: long 53 / short 43 (more balanced). Macro filter `btc_4h_below_ema50` is loose — needs review.

### Recommendations for Round 4 (v9)
1. **Disable framework trailing** — set `trailing_stop = False` so `custom_stoploss()` is the only trailing logic. This is the highest-impact single change for v9.
2. **Tighten the trailing arm** — current 1.5×ATR is firing on noise. Try 2.5×ATR or arm trailing only after +2×ATR (not +1×ATR).
3. **Investigate bull-period short over-firing** — 81 shorts in a +122% bull market means the macro filter is broken. Check `btc_4h_below_ema50` logic and short-entry threshold.
4. **Keep the wide -0.08 fallback** — confirmed harmless (zero hits) and defensible.

**Net read:** v8 is a partial win (bear got materially better, signal cohort still 94% WR), but the trailing-stop double-up is wasting alpha. v9 should be a one-line change (`trailing_stop = False`) before any deeper redesign.

---

## 📁 v8 Changes Summary

| Change | Old (v7) | New (v8) | Reason |
|---|---|---|---|
| `stoploss` | -0.015 | **-0.08** (fallback only) | Real stop done by custom_stoploss() |
| `use_custom_stoploss` | False | **True** | Enable ATR-adaptive stop |
| `custom_stoploss()` | not present | **Added** | 2×ATR initial, 1.5×ATR trailing |
| ATR floor | none | **-0.005 to -0.04 clamp** | Never below noise, never too wide |
| Entry/exit signals | same as v7 | **unchanged** | ML signals confirmed working |

**How custom_stoploss works:**
- Gets live ATR from `get_analyzed_dataframe()`
- Initial stop: `-(2.0 × ATR%)` — adapts per pair per candle
- On 15m BTC: ATR ~0.4-0.8% → stop = 0.8-1.6% — same range as v7 but ONLY when volatility justifies it
- In low-vol: ATR ~0.2% → stop = 0.4% — far tighter than fixed SL
- In high-vol: ATR ~1.5% → stop = 3.0% — wider than v7, avoids chop
- Trailing: once +1×ATR in profit, trail at 1.5×ATR — locks in winners

---

## 🔄 Collaboration Rules

| Who | Does What |
|---|---|
| **Gaurav** | Decides when to run, approves phase transitions |
| **Claude Code** | SSH, deploy, run backtests, verify on server, commit results |
| **Perplexity** | Analyses results, designs strategy changes, writes code, updates docs |

---

*Written by Perplexity AI — 2026-05-02*
