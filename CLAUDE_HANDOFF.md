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

## 📈 Round 4 Results (v9) — Run 2026-05-02

**v9 changes vs v8:**
1. `trailing_stop = False` (framework trailing OFF; custom_stoploss owns the trail)
2. Short entry now requires `btc_4h_below_ema50 == 1` (macro-gated)

### 🐂 BULL — `20240101-20250101` (Market: +122.88%)
```
Total Trades      : 57   (24W / 33L)   ← was 112 in R3
Long / Short      : 31 / 26            ← was 31 / 81 (shorts -68%) ✅
Final Balance     : 992.83 USDT
Absolute P&L      : -7.17 USDT          ← was -33.05 (much better)
Total Profit %    : -0.72%

--- Acceptance ---
Win Rate          : 42.1%   ❌  (basically flat vs R3 42.0%)
Sharpe (closed)   : -0.13   ❌  (was -0.78 — huge improvement)
Max Drawdown      : 2.34%   ✅  (was 4.64% — halved)
Profit Factor     : 0.89    ❌  (was 0.72)

--- Exit Reasons ---
exit_signal       : 19 | +1.02% | 94.7% WR  ← signal cohort still excellent
trailing_stop_loss: 38 | -0.60% | 15.8% WR  ← STILL CHOPPING
stop_loss         :  0 | (fallback never hit)
```

### 🐻 BEAR — `20250101-20260401` (Market: -39.27%)
```
Total Trades      : 92   (46W / 46L)   ← was 96
Long / Short      : 52 / 40
Final Balance     : 978.48 USDT
Absolute P&L      : -21.52 USDT         ← was -12.47 (regressed)
Total Profit %    : -2.15%

--- Acceptance ---
Win Rate          : 50.0%   ❌  (was 52.1% — slight regression)
Sharpe (closed)   : -0.37   ❌  (was -0.22 — REGRESSED)
Max Drawdown      : 4.92%   ✅  (was 4.72%)
Profit Factor     : 0.77    ❌  (was 0.87 — regressed)

--- Exit Reasons ---
exit_signal       : 32 | +0.80% | 93.8% WR
trailing_stop_loss: 60 | -0.61% | 26.7% WR
stop_loss         :  0 | (fallback never hit)
```

---

## 🔍 Round 4 — Hypothesis vs Reality

| Hypothesis | Result | Verdict |
|---|---|---|
| trailing_stop_loss drops from 79/62 → near zero | Got 38/60 | ❌ Did not happen |
| Bull shorts drop from 81 → ~20-30 | Got 26 | ✅ Hit dead center |
| WR recovers toward 60%+ on both | 42% / 50% | ❌ Did not happen |
| Bear Sharpe crosses -0.1 or goes positive | -0.37 | ❌ Regressed |

**Score: 1 of 4. Macro filter worked. Trailing fix didn't.**

### Why disabling framework trailing didn't fix the chop
- `custom_stoploss()` itself has a trailing arm: once profit > +1×ATR, it tightens to MFE − 1.5×ATR.
- Turning OFF the framework `trailing_stop` only removed the second trailing system. The Chandelier-style trail INSIDE custom_stoploss is still the dominant chop source.
- 60 bear-period trailing exits at -0.61% avg confirms it.

### Why bull improved sharply but bear didn't
- Bull benefit came almost entirely from the **macro-filter fix**: 81 → 26 shorts removed the bulk of alpha-bleed in a +122% bull market. Trade count nearly halved, smaller drawdown, smaller absolute loss.
- Bear had nothing to gain from that fix (BTC was below 4h EMA most of the period anyway, so v8 vs v9 short eligibility barely changed — 43 → 40 shorts). Without the trailing fix actually reaching the trailing arm, bear regressed slightly.

### Recommendations for Round 5 (v10)
The trailing arm inside `custom_stoploss()` is the next thing to touch, not the framework. Three options ranked by expected impact:

1. **Disable the trailing arm in custom_stoploss entirely** — return only the initial 2×ATR stop, never tighten. Single-screen change, isolates whether trailing is helping at all.
2. **Arm the trail later** — only start trailing after profit > +2×ATR (currently +1×ATR). Lets winners breathe past noise before locking in.
3. **Widen the trail** — use 3×ATR pullback instead of 1.5×ATR. Looser leash, fewer chops.

My pick: try **option 1 first** as a diagnostic. If trailing is net-negative we'll see PF flip immediately. If trailing is net-positive but mistuned, options 2/3 follow.

### Status of the four rounds
| | R1 (v6) | R2 (v7) | R3 (v8) | R4 (v9) |
|---|---|---|---|---|
| Bull Sharpe | -0.145 | -0.896 | -0.78 | **-0.13** |
| Bear Sharpe | -0.258 | -0.554 | -0.22 | -0.37 |
| Bull DD | 3.73% | 6.25% | 4.64% | **2.34%** |
| Bear DD | 8.23% | 7.10% | 4.72% | 4.92% |
| Bull P&L | -10 | -47 | -33 | **-7** |
| Bear P&L | -23 | -36 | -12 | -22 |
| exit_signal WR | 79% | 93.5% | 94% | 94% |

**Direction is correct.** Bull P&L from -47 → -7 over four rounds; bull DD from 6.25% → 2.34%. Signal cohort stable at 94% WR. The remaining lever is the trailing arm.

---

## 📈 Round 5 Results (v10) — Run 2026-05-02

**v10 changes vs v9 (docs-correctness rewrite of `custom_stoploss`):**
1. `return None` on missing data (was: `self.stoploss` → forced reset every candle)
2. Return positive floats throughout (was: negatives; same effect, but docs-aligned)
3. `trailing_stop = False` carried over from v9
4. **Both stops anchored to ENTRY price via `stoploss_from_open()`** — initial uses negative arg (loss-cap below open), trailing uses positive arg (profit-lock above open)

### 🐂 BULL — `20240101-20250101` (Market: +122.88%)
```
Total Trades      : 57   (33W / 24L)
Long / Short      : 32 / 25
Final Balance     : 1007.24 USDT      ← FIRST POSITIVE BALANCE
Absolute P&L      : +7.24 USDT        ← FIRST POSITIVE P&L
Total Profit %    : +0.72%

--- Acceptance ---
Win Rate          : 57.9%   ✅  (was 42.1% R4)
Sharpe (closed)   : +0.13   ❌  (was -0.13 — first POSITIVE Sharpe)
Max Drawdown      : 1.68%   ✅  (was 2.34% — all-time low)
Profit Factor     : 1.11    ❌  (was 0.89 — first time > 1.0)

--- Exit Reasons ---
exit_signal       : 13 | +0.38% | 92.3% WR
trailing_stop_loss: 41 | +0.04% | 51.2% WR  ← FLIPPED FROM CHOP TO PROFIT
stop_loss         :  3 | -0.89% |  0.0% WR  (helper-zero edge cases)

Long  | exit_signal      :  5 trades | 100%  WR | +0.50% avg
Short | exit_signal      :  8 trades | 87.5% WR | +0.30% avg
Long  | trailing_stop    : 24 trades | 50.0% WR | +0.07% avg
Short | trailing_stop    : 17 trades | 52.9% WR | -0.00% avg
Long  | stop_loss        :  3 trades |  0.0% WR | -0.89% avg
```

### 🐻 BEAR — `20250101-20260401` (Market: -39.27%)
```
Total Trades      : 87   (51W / 36L)
Long / Short      : 48 / 39
Final Balance     : 991.22 USDT
Absolute P&L      : -8.78 USDT        ← was -21.52 R4 (improved 60%)
Total Profit %    : -0.88%

--- Acceptance ---
Win Rate          : 58.6%   ✅  (was 50.0% R4)
Sharpe (closed)   : -0.15   ❌  (was -0.37 R4)
Max Drawdown      : 3.66%   ✅  (was 4.92% R4)
Profit Factor     : 0.91    ❌  (was 0.77 R4)
Max Consec Wins   : 12              (was 7 R4)

--- Exit Reasons ---
exit_signal       : 22 | +0.36% | 81.8% WR
trailing_stop_loss: 63 | -0.17% | 52.4% WR  ← was 26.7% WR @ -0.61% R4
stop_loss         :  2 | -0.80% |  0.0% WR

Long  | exit_signal      : 13 trades | 100%  WR | +0.69% avg  ← perfect cohort
Short | exit_signal      :  9 trades | 55.6% WR | -0.13% avg
Long  | trailing_stop    : 34 trades | 55.9% WR | -0.02% avg
Short | trailing_stop    : 29 trades | 48.3% WR | -0.35% avg
```

---

## 🔍 Round 5 — The breakthrough round

**Score: 4 of 4 directional improvements.**

| | R4 v9 | R5 v10 | Δ |
|---|---|---|---|
| Bull WR | 42.1% | **57.9%** | +15.8pp |
| Bull Sharpe | -0.13 | **+0.13** | first positive Sharpe ever |
| Bull PF | 0.89 | **1.11** | first PF > 1 |
| Bull P&L | -7.17 | **+7.24** | first profitable round |
| Bull DD | 2.34% | **1.68%** | all-time low |
| Bear WR | 50.0% | **58.6%** | +8.6pp |
| Bear Sharpe | -0.37 | **-0.15** | better |
| Bear PF | 0.77 | **0.91** | better |
| Bear P&L | -21.52 | **-8.78** | 60% smaller loss |
| Bear DD | 4.92% | **3.66%** | better |

### Why anchoring to entry-price flipped the result
- v9's trailing arm returned `-(1.5 × atr_pct)` interpreted as "% from current price." As price ran up after entry, the stop chased upward at the same speed → it sat ~1.5×ATR below current price forever, never actually locking in profit, just absorbing every pullback.
- v10's trailing arm calls `stoploss_from_open(1.5 × atr_pct, current_profit, ...)` which returns a current-rate-relative number that places the stop at +1.5×ATR **above the OPEN** — a fixed price level. As current price moves up further, the % from current widens, so the stop appears to "trail," but it's actually locked at a fixed dollar level above entry.
- Result: the trailing cohort that lost -0.61% avg in R4 now makes +0.04% / -0.17% avg — the chop is gone, replaced by genuine profit-lock-in.

### Why the wider `stop_loss` fallback now hits 3-5 times
- The `stoploss_from_open(-2.0 × atr_pct, ...)` helper returns 0 when price has already breached the open-anchored target on the loss side. Freqtrade interprets `0` as "stop at current price" — i.e., immediate stop. That's correct: if the open-anchored stop is already breached, we should be out.
- 3-5 hard stops at -0.5% to -0.9% avg is a healthy, narrow tail. No more -3.6% blowouts like R1, no -1.6% chops like R2.

### Acceptance vs targets
| | Bull | Bear | Target |
|---|---|---|---|
| WR | 57.9% ✅ | 58.6% ✅ | > 50% |
| Sharpe | +0.13 ❌ | -0.15 ❌ | > 0.5 |
| DD | 1.68% ✅ | 3.66% ✅ | < 20% |
| PF | 1.11 ❌ | 0.91 ❌ | > 1.2 |

**2/4 pass on each leg.** Sharpe and PF are now within sight of the target — same direction, smaller gap. Not yet shippable to live capital but the trajectory is clean.

### Five-round trajectory
| | R1 v6 | R2 v7 | R3 v8 | R4 v9 | **R5 v10** |
|---|---|---|---|---|---|
| Bull Sharpe | -0.145 | -0.896 | -0.78 | -0.13 | **+0.13** |
| Bear Sharpe | -0.258 | -0.554 | -0.22 | -0.37 | **-0.15** |
| Bull DD | 3.73% | 6.25% | 4.64% | 2.34% | **1.68%** |
| Bear DD | 8.23% | 7.10% | 4.72% | 4.92% | **3.66%** |
| Bull P&L | -10 | -47 | -33 | -7 | **+7** |
| Bear P&L | -23 | -36 | -12 | -22 | **-9** |
| Bull WR | 63.0% | 48.2% | 42.0% | 42.1% | **57.9%** |
| Bear WR | 63.4% | 50.0% | 52.1% | 50.0% | **58.6%** |

### Recommendations for Round 6 (v11)
The signal works, the stop now works, the macro filter works. To cross the Sharpe > 0.5 / PF > 1.2 line, the remaining levers are:

1. **Walk-forward / out-of-sample validation first.** R5 numbers are still in-sample. Before tuning further, confirm the lift survives a held-out window. If it doesn't, we're overfitting; if it does, we have a real strategy.
2. **Tune the trailing trigger and width.** Currently arms at +1×ATR, locks at +1.5×ATR above entry. Worth a small grid: arm at {1.0, 1.5, 2.0}×ATR, lock at {1.5, 2.0, 2.5}×ATR.
3. **Position sizing.** All trades use 200 USDT stake. Volatility-scaled stake (smaller in high-ATR regimes) would reduce dollar damage from the tail of stop_loss + losing trailing trades without changing logic.
4. **Re-label with triple-barrier.** Biggest single research unlock if Sharpe plateaus here. The path-blind `mean(next 3 closes)` label is still the architectural ceiling.

My pick: option 1 first (validation), then option 2 (small grid). Don't relabel until the in-sample lift is confirmed real.

---

## 🤝 Handoff to Perplexity — Walk-Forward Validation In Progress

**Written by:** Claude Code
**Date:** 2026-05-03
**For:** Perplexity AI (next session)
**Status:** Walk-forward backtest running on server; results pending.

### What's running right now
A single Freqtrade backtest with FreqAI walk-forward training:
- `train_period_days = 180` (6 months training)
- `backtest_period_days = 30` (test window = 1 month, retrain monthly)
- `identifier = finbuddy_walkforward_v1` (separate model cache from R5 results)
- Range: `20240315-20260415` → ~25 monthly test windows
- Strategy: v10 unchanged (no parameter tuning between windows — same `custom_stoploss`, same macro short-gate, same entry/exit thresholds)
- Pairs: BTC/ETH/SOL/BNB/XRP USDT:USDT
- Process: background task `bhim8u0tk` on server

Why this matters: R5's +7 USDT bull and -9 USDT bear are still in-sample because we hand-tuned v6 → v10 against those exact windows. Walk-forward simulates "what would v10 have done if we deployed it cold each month using only the prior 6 months of training data?"

### Result parser
`scripts/walkforward_parse.py` — reads the latest backtest-result ZIP and reports per-month: trade count, WR%, Sharpe, P&L%, avg trade %. Run it after the backtest completes:
```
sg opc -c "python3 scripts/walkforward_parse.py"
```

### Decision tree for what comes next

When the parser output lands:

**Pass criteria (proceed to v11 tuning):**
- ≥ 60% of windows have WR > 50%
- Average monthly Sharpe > 0
- No single month accounts for > 40% of cumulative P&L
- Both bull-regime months (2024-04 → 2024-12) and bear-regime months (2025-Q1 → 2026-Q1) show positive median behavior

**Fail criteria (escalate to Perplexity for triple-barrier redesign):**
- Cumulative P&L concentrated in 1–2 lucky months
- Positive Sharpe in < 50% of windows
- A clear regime where v10 systematically loses (e.g., all 2025-Q3 months negative)

### If we fail OOS — your job, Perplexity

The label `&-s_close = mean(next 3 closes) / current_close - 1` is the architectural problem. It is **path-blind**: the model is rewarded only for the average of the forward window, regardless of how much drawdown the path takes to get there. Every parameter tweak we've made (v6→v10) has been treating symptoms; this is the disease.

The redesign is **triple-barrier labeling** (López de Prado). For each candidate entry, label by which of three barriers hits first within `label_period_candles`:
- Upper barrier: take-profit at +k×ATR → label `+1`
- Lower barrier: stop-loss at -k×ATR → label `-1`
- Time barrier: window expires before either → label by sign of final return

The model now learns to *refuse* setups whose path is bad even when the mean is okay — exactly the pathology our 79/62 trailing chops in v8/v9 exposed.

When you take this on:
1. Replace `set_freqai_targets()` to emit the categorical label (or a directional regression on the realized first-touch outcome).
2. Retrain on the same windows — expect WR to drop a bit but Sharpe and PF to rise as the model stops taking trash setups.
3. Re-run walk-forward on v11 with the new label. Same `train_period_days=180, backtest_period_days=30`.

### What's already pushed for you

`gaurav` branch:
- v10 strategy with `stoploss_from_open()` — see `freqtrade/user_data/strategies/FinBuddyFreqAI.py`
- 5 rounds of futures backtest results — full table in this file, `## 📈 Round History`
- Walk-forward runner config — `freqtrade/user_data/backtest_config.json` already has the 180/30 settings
- Result parser — `scripts/walkforward_parse.py`
- All memory files synced to v10 / R5 state (CLAUDE.md, FINBUDDY_PROJECT_MEMORY.md, finbuddy_memory/CONTEXT.md, graveyard.md, winners.md)

### Server ops state (just so you don't trip on it)
- ubuntu user is now in the `opc` group; `freqtrade/user_data` is group-owned + `g+w` + setgid. Both ubuntu (uid 1001) and the container's ftuser (uid 1000 = host opc) can write. Existing SSH sessions need `newgrp opc` or re-login to pick up the group.
- `XAI_API_KEY` lives in `freqtrade/.env` (gitignored), referenced as `${XAI_API_KEY}` in `docker-compose.yml`. Compose auto-loads `.env` from the compose-file dir.
- FreqAI `.pkl` model artifacts are gitignored — won't show up as dirty in git status anymore.
- Live dry-run bot is still on the live `finbuddy_lgbm_v1` identifier (separate from `finbuddy_walkforward_v1` used for this run).

*Written by Claude Code — 2026-05-03. Walk-forward result will be appended below this section once it lands.*

---

## 🔴 Walk-Forward Result — v10 FAILED OOS

**Run:** `20240315-20260415`, `train_period_days=180`, `backtest_period_days=30`
**Identifier:** `finbuddy_walkforward_v1`
**Result file:** `backtest-result-2026-05-03_16-53-34.zip`

### Aggregate
- 280 trades, WR 58.2% ✓, Drawdown 4.44% ✓
- **Sharpe (closed): -0.67** ❌ (was +0.13 / -0.15 in R5)
- **Total P&L: -23.14 USDT** ❌ (was +7.24 / -8.78 in R5)

### Per-window breakdown (test month = close_date month)
```
Month        N  Wins  Losses    WR%   Sharpe     P&L%     Avg%
----------------------------------------------------------------------
2024-04      1     1       0  100.0    +0.00    +3.75   +3.750   ← 1 trade
2024-06      2     0       2    0.0    -4.96    -1.73   -0.866
2024-08      4     2       2   50.0    +0.20    +0.67   +0.167
2024-09      2     0       2    0.0    -3.52    -0.95   -0.474
2024-11      2     0       2    0.0    -7.38    -6.66   -3.330
2024-12     53    27      26   50.9    -0.92    -8.45   -0.159
2025-01     49    30      19   61.2    -0.24    -1.59   -0.032
2025-02     23    17       6   73.9    +0.97    +7.12   +0.310   ← only winner
2026-03    129    79      50   61.2    -0.15    -1.18   -0.009
2026-04     15     7       8   46.7    -0.89    -2.57   -0.171
----------------------------------------------------------------------
OVERALL    280   163     117   58.2    -0.67   -11.58   -0.041
```

### Verdict against pass/fail criteria
| Criterion | Threshold | Actual | Verdict |
|---|---|---|---|
| Months WR > 50% | ≥ 60% of months | **44%** (4/9) | ❌ |
| Avg monthly Sharpe > 0 | > 0 | **-1.88** | ❌ |
| No month dominates P&L | < 40% from any one | 2025-02 alone: +7.12 vs cumulative -11.58 (only positive month with mass) | ❌ |
| Positive Sharpe months | ≥ 50% | **22%** (2/9) | ❌ |

**4/4 fail criteria triggered.** The R5 in-sample lift does not survive OOS.

### Two anomalies worth flagging
1. **Sparse months.** Of 25 expected test windows, only 10 produced ≥1 trade and only 4 produced substantial trade counts (2024-12, 2025-01, 2025-02, 2026-03). The other 15 months are silent. Either v10's filters (macro short-gate, ATR floor, 1h trend) are vastly too restrictive when the training window changes, OR something in the FreqAI training cadence skipped predictions during those months. Worth investigating but does not change the conclusion.
2. **2026-03 cluster (129 trades, 61.2% WR, near-zero Sharpe).** Almost half of all OOS trades happen in a single month, and even that "good WR" month is a -1.18% loser. Confirms the strategy is taking trash setups when it does fire.

### What this proves
**The label is the architectural problem, not the stop.** Five rounds of stop-tuning got us to a beautiful in-sample R5, but cold deployment loses money. The mean-of-next-3-closes target is path-blind by construction — the model is trained to ignore the drawdown leg, then the realized stops absorb all the path damage and the model "looks right" on average while every trade limps to break-even.

This was the diagnosis from the Round 1 review I wrote earlier in this session. Five iterations didn't fix it because we were treating the symptom (stops) instead of the cause (label).

---

## 🚨 Escalation to Perplexity — Triple-Barrier Label Redesign

**You're up.**

The escalation criteria from earlier in this file are met. Cease v10/v11 stop tuning. The next move is a label rewrite, not another parameter pass.

### Concrete spec for v11 label
Replace `set_freqai_targets()` in `freqtrade/user_data/strategies/FinBuddyFreqAI.py`. Current implementation:
```python
def set_freqai_targets(self, dataframe, metadata, **kwargs):
    label_period = self.freqai_info["feature_parameters"]["label_period_candles"]
    dataframe["&-s_close"] = (
        dataframe["close"].shift(-label_period).rolling(label_period).mean()
        / dataframe["close"]
    ) - 1
    return dataframe
```

This produces a path-blind regression target. Replace with **triple-barrier labeling** (López de Prado, *Advances in Financial Machine Learning* ch. 3):

For each candle `t`:
- Set TP barrier at `close[t] * (1 + k_tp * atr_pct[t])`
- Set SL barrier at `close[t] * (1 - k_sl * atr_pct[t])`
- Set time barrier at `t + label_period_candles`
- Look forward in `[t+1, t+label_period_candles]` and label by which barrier hits first:
  - `+1` if TP hits first → take-profit reached
  - `-1` if SL hits first → stopped out
  - `0` if time barrier expires before either → label by sign of final return

Suggested starting params: `k_tp = 2.0`, `k_sl = 1.0`, `label_period_candles = 12` (3 hours on 15m, longer than current 3 to give the path time to resolve).

Two model-output options:
- **Categorical (recommended):** Switch FreqAI model to a classifier (`LightGBMClassifier`). Output is class probabilities. Entry rule: `&-s_label_proba_+1 > 0.55`.
- **Regression on outcome:** Keep regressor, target is the realized P&L at first-touch. Less elegant but compatible with current entry logic (`&-s_close > 0.010` style).

### Validation plan for v11 (mandatory)
Once the label is rewritten:
1. Re-run the same walk-forward harness (already in place: `train_period_days=180, backtest_period_days=30, identifier=finbuddy_walkforward_v1`). Purge cache first: `sudo rm -rf freqtrade/user_data/models/finbuddy_walkforward_v1`.
2. Run `python3 scripts/walkforward_parse.py` — same parser, same metrics, same pass/fail bar.
3. **Pass criteria:** ≥ 60% months with WR > 50%, avg monthly Sharpe > 0, no single month > 40% of cumulative P&L.

Do NOT run another in-sample bull/bear pair until v11 passes walk-forward. The five-round in-sample march was theatre.

### Files for context
- `freqtrade/user_data/strategies/FinBuddyFreqAI.py` — strategy v10
- `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` — current FreqAI model (LightGBMRegressor + xAI Grok confirmation). For categorical label, fork to `FinBuddyLLMClassifierModel.py`.
- `freqtrade/user_data/backtest_config.json` — already configured for walk-forward
- `scripts/walkforward_parse.py` — result parser
- `finbuddy_memory/strategies/graveyard.md` — v6/v7/v8/v9 retirement entries; add v10 once v11 ships

### What you should NOT do
- Don't tune the stop further. The stop is not the bug — five rounds proved that.
- Don't try yet another parameter grid on the existing label. Same dead end.
- Don't deploy v11 to dry-run without passing walk-forward. Live capital must wait for OOS validation.

*Written by Claude Code — 2026-05-03. Walk-forward verdict appended.*

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
