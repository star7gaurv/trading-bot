# Strategy Graveyard
> Strategies that were tested and failed. Kept here so we never repeat the same mistake.
> Written by the research loop after a strategy is demoted.
> Winning strategies → [[winners]]  |  Back to hub → [[../CONTEXT]]

---

## Format
```
### Strategy Name
- **Reason failed:** ...
- **Regime it failed in:** ...
- **Date demoted:** ...
- **Key lesson:** ...
```

---

### FinBuddyFreqAI v3 — Stoploss -0.03 run (2026-05-01)
- **Stoploss:** -0.03
- **Trades:** 148 | Win rate: 57.4% ✅ | Sharpe: -1.58 ❌ | Drawdown: 17.87% ✅ | Profit factor: 0.52 ❌
- **Reason failed:** 44 stop_loss exits at -3.19% avg = -281 USDT destroyed all profits. Stoploss too tight for 4-hour avg trade duration.
- **Regime it failed in:** Bear market — BTC/market fell -47.55% during test period (2025-02-01 to 2026-04-01)
- **Date:** 2026-05-01
- **Key lesson:** Stoploss exits at -3% avg mean the position moves against entry before the ML signal fires exit. Entry threshold (0.008) is not selective enough.

### FinBuddyFreqAI v3 — Stoploss -0.035 run (2026-05-01)
- **Stoploss:** -0.035
- **Trades:** 141 | Win rate: 60.3% ✅ | Sharpe: -1.40 ❌ | Drawdown: 17.50% ✅ | Profit factor: 0.54 ❌
- **Reason failed:** 36 stop_loss exits at -3.69% avg = -265 USDT. Slightly looser stoploss barely changed outcome — root issue is bad entries, not stoploss level. Entry signal fires during counter-trend moves.
- **Regime it failed in:** Bear market — BTC/market fell -47.55% during test period (2025-02-01 to 2026-04-01)
- **Date:** 2026-05-01
- **Fix needed:** Raise ML entry threshold from 0.008 → 0.012 (stronger signal required), or add 1h trend filter (only enter if 1h EMA slope positive). Exit signal trades had 79.8% win rate — the ML signal is good, entries are just too permissive.

### FinBuddyFreqAI v4 — ML threshold 0.012 + 1h EMA-50 trend filter (2026-05-01)
- **Stoploss:** -0.035
- **Trades:** 24 | Win rate: 58.3% ✅ | Sharpe: -0.15 ❌ | Drawdown: 4.97% ✅ | Profit factor: 0.68 ❌
- **Reason failed:** Only 24 trades in 14-month period — filters over-tuned. 1h EMA-50 trend filter eliminates most entries in the bearish test window. Exit signal trades: 81.8% win rate — ML signal confirmed good. 8 stop_loss exits at -3.69% still dominate losses.
- **Regime it failed in:** Bear market — BTC/market fell -47.55% during test period (2025-02-01 to 2026-04-01)
- **Date:** 2026-05-01
- **Key lesson:** Threshold 0.012 + 1h EMA-50 filter too strict for bear market. Cuts valid trades along with bad ones. Improvement direction: threshold 0.010, or shorter 1h EMA-20, or separate bull/bear thresholds.

### Grid Search Round 3 — 144 combos, no winner (2026-05-02)
- **Grid:** stoploss [-0.02/-0.025/-0.03] × trailing_offset [0.018/0.020/0.022/0.025] × ml_exit_threshold [-0.001/-0.002/-0.003] × ml_threshold [0.009/0.011] × atr_threshold [0.002/0.003]
- **All 144 combos FAIL.** Best: SL=-0.025, trail=0.020, ml_exit=-0.001, ml=0.011, atr=0.002 → 48.3% WR, Sharpe -0.401, DD 5.3%, PF 0.472
- **Pattern 1 — trailing_offset is another dead lever:** Same metrics across different trailing_offset values (0.018→0.025 all give Sharpe -0.401 at best settings). Trailing stop activates but doesn't improve reward:risk in this bear market.
- **Pattern 2 — ml_exit_threshold also dead:** Faster exit (-0.001) vs slower (-0.003) produces identical or near-identical results. The ML model doesn't catch the reversal fast enough to change outcomes.
- **Pattern 3 — Bear market is the structural problem:** The test period 2025-02-01 to 2026-04-01 saw BTC fall -47.55%. No long-only strategy tuned on these params can be profitable in a sustained bear market. This is not a parameter problem.
- **192 total combos across 3 rounds — none passed.** The strategy architecture (15m entries, 4h-trained ML) is sound but requires correct market conditions.
- **Key lesson:** Stop tuning parameters in bear market data. Either (a) add regime filter to skip bear entries, or (b) re-test with bull market period (2024-01 to 2025-01). The ML signal is validated at 79-81% WR on signal exits — the strategy works, just not in a -47% market.
- **Date:** 2026-05-02

### Grid Search Round 2 — 36 combos, no winner (2026-05-01)
- **Grid:** stoploss [-0.02/-0.025/-0.03] × roi_multiplier [0.06/0.08/0.10] × ml_threshold [0.009/0.011] × atr_threshold [0.002/0.003]
- **All 36 combos FAIL.** Best: stoploss=-0.03, roi=0.10, ml=0.009, atr=0.002 → 60.8% WR, Sharpe -0.236, DD 9.2%, PF 0.815
- **Pattern 1 — roi_multiplier has ZERO effect:** Trades using same stoploss+ml+atr combo are identical regardless of roi. FreqAI exits via ML signal `&-s_close` before ROI ceiling is ever hit. roi_multiplier is a dead lever in this architecture.
- **Pattern 2 — stoploss is the only structural lever:** Best stoploss is -0.03 (wider = more room for winners to develop). Tighter -0.02 cuts winners short and tanks Sharpe to -0.82.
- **Pattern 3 — Sharpe remains deeply negative at all settings:** Best Sharpe -0.174 (ml=0.011, sl=-0.025, roi=0.10). Even though WR hits 60-65%, the avg loser is still much larger than avg winner in absolute USDT terms.
- **Root diagnosis confirmed:** The ML signal fires exits correctly (79-81% WR on signal exits) but stop_loss exits occur BEFORE the ML exit signal fires — meaning entries are happening at bad timing relative to the 4h candle cycle.
- **Key lesson:** Parameter tuning within this architecture cannot fix the problem. Need structural change: (a) trailing stop instead of fixed SL, (b) entry timing aligned to HTF candle close, or (c) separate bull/bear regime strategies.
- **Date:** 2026-05-01

### Grid Search Round 1 — 12 combos, no winner (2026-05-01)
- **Grid:** ml_threshold [0.009/0.010/0.011] × ema_1h [20/35] × rsi_ceil [68/72]
- **All 12 combos FAIL.** Best: ml=0.009, ema=20, rsi=68 → 65.1% WR, Sharpe -0.18, PF 0.854
- **Pattern:** ml_threshold dominates — 83 trades at 0.009, 51 at 0.010, 29-30 at 0.011. WR drops below 50% at 0.011. EMA and RSI patches had minimal effect (possible patch failure due to opc file ownership).
- **Sharpe negative for all combos** — stop_loss exits still destroying profit even with 1h trend filter. Exit signal win rate good but stop_loss exits at ~-3.5% avg dominate.
- **Key lesson:** The grid range was too narrow. Need either: (a) wider stoploss like -0.05 to give trades more room, (b) trailing stop-only exits (remove fixed stoploss), or (c) structurally different entry logic (regime detection).

---

### FinBuddyFreqAI v6 — Spot, futures-ready rewrite (retired 2026-05-02)
- **Backtest:** Futures R1. Bull: 73 trades, WR 63.0%, Sharpe -0.145, PF 0.91, P&L -10 USDT. Bear: 82 trades, WR 63.4%, Sharpe -0.258, PF 0.83, P&L -23 USDT.
- **Reason failed:** 13/14 stop-loss hits at -3.59% per round destroyed P&L. Avg loser >> avg winner.
- **Key lesson:** A -3.5% fixed stop with -0.4% to -0.5% avg winner is a 7:1 reward:risk against you. Either widen winners or tighten stops — but tightening is the trap (see v7).

### FinBuddyFreqAI v7 — Stoploss tightened to -1.5% (retired 2026-05-02)
- **Backtest:** Futures R2. Bull: 85 trades, WR 48.2%, Sharpe -0.896, P&L -47 USDT. Bear: 96 trades, WR 50.0%, Sharpe -0.554, P&L -36 USDT.
- **Reason failed:** -1.5% stop is inside the noise floor of 15m BTC. 41/42 stop hits per round, WR collapsed from 63% to 48%. Tightening did the opposite of what was needed.
- **Key lesson:** A fixed % stop is wrong when ATR varies. Need ATR-adaptive sizing (which became v8).

### FinBuddyFreqAI v8 — ATR-based custom_stoploss() (retired 2026-05-02)
- **Backtest:** Futures R3. Bull: 112 trades, WR 42.0%, Sharpe -0.78, P&L -33 USDT. Bear: 96 trades, WR 52.1%, Sharpe -0.22, P&L -12 USDT.
- **Reason failed:** Two trailing systems running simultaneously — framework `trailing_stop=True` AND a Chandelier trail inside `custom_stoploss()`. Whichever was tighter fired first. 79/62 `trailing_stop_loss` exits at -0.55% avg avg replaced the SL chops.
- **Key lessons:**
  1. Freqtrade docs explicitly warn: don't combine `trailing_stop` with custom_stoploss.
  2. `dataframe.iloc[-1]` inside `custom_stoploss()` has off-by-one lookahead concerns across FT versions.
  3. Returning `self.stoploss` as a fallback resets a previously tightened stop on every candle — must return `None` ("no desire to change").

### FinBuddyFreqAI v9 — `trailing_stop=False` + macro short-gate (retired 2026-05-02)
- **Backtest:** Futures R4. Bull: 57 trades, WR 42.1%, Sharpe -0.13, P&L -7 USDT. Bear: 92 trades, WR 50.0%, Sharpe -0.37, P&L -22 USDT.
- **What worked:** Macro short-gate (`btc_4h_below_ema50 == 1`) cut bull shorts from 81 → 26, halved trade count, halved DD.
- **Reason failed (bear):** Disabling framework trailing only removed *one* of two trailing systems. The Chandelier trail INSIDE `custom_stoploss()` was still chasing current price down. 60 bear trailing exits at -0.61% avg.
- **Key lesson:** A current-rate-relative trailing stop chases price up indefinitely without ever locking in a fixed dollar floor. Need entry-anchored stops via `stoploss_from_open()` (which became v10).

---

## ✅ Active (not retired): FinBuddyFreqAI v10 — see [[winners]]
