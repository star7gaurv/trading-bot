# 🤝 FinBuddy — Handoff Note for Perplexity

**Written by:** Claude Code  
**Date:** 2026-05-01 ~20:00 IST  
**For:** Perplexity AI (next session)  
**Branch:** `gaurav`

---

## ✅ What Was Done This Session (Claude Code)

| Task | Status |
|---|---|
| Pulled Perplexity's commit 68b54ae | ✅ |
| Fixed class name mismatch in autobacktest.py (FinBuddyFreqAI → FinBuddyFreqAI_test) | ✅ |
| Fixed ml_threshold regex (closing paren missing in pattern) | ✅ |
| Discovered stoploss/roi_multiplier patches had zero effect (backtest_config.json override) | ✅ |
| Fixed: write_patched_config() patches config + docker cp to container per combo | ✅ |
| Ran Round 2: 36 combos completed — all FAIL | ✅ |
| Committed results CSV, updated graveyard.md | ✅ |

---

## 📊 Round 2 Grid Results — Full Analysis

**Grid:** stoploss [-0.02/-0.025/-0.03] × roi_multiplier [0.06/0.08/0.10] × ml_threshold [0.009/0.011] × atr_threshold [0.002/0.003]

**Best combo:** stoploss=-0.03, roi=0.10, ml=0.009, atr=0.002 → **60.8% WR, Sharpe -0.236, DD 9.2%, PF 0.815**

### Key Findings

**Finding 1: roi_multiplier is a DEAD LEVER**
All combos with same stoploss+ml+atr produce identical metrics regardless of roi (0.06, 0.08, 0.10).
FreqAI exits via ML signal `&-s_close < -0.003` before the ROI ceiling is ever reached.
Do NOT include roi_multiplier in future grids — it has zero effect in this architecture.

**Finding 2: Stoploss is the only structural lever that works**
| stoploss | best WR | best Sharpe | PF |
|---|---|---|---|
| -0.02 | 54.8% | -0.82 | 0.57 |
| -0.025 | 59.3% | -0.38 | 0.73 |
| -0.03 | 60.8% | -0.24 | 0.82 |

Trend: wider stoploss → better Sharpe. The -0.03 sweet spot lets winners develop.
But even -0.03 is not enough — Sharpe is still deeply negative.

**Finding 3: Sharpe is structurally negative — parameter tuning cannot fix it**
Best Sharpe across all 36 combos: **-0.174** (ml=0.011, sl=-0.025, roi=0.10, atr=0.002/0.003).
Even at 59-61% win rate, avg USDT loss > avg USDT win.
This means stop_loss exits happen BEFORE the ML signal fires the exit — the position moves against entry, then ML catches up and signals exit, but the damage is done.

**Finding 4: ml=0.011 gives too few trades**
ml=0.011 → 29 trades in 14 months. Too sparse for meaningful statistics.
ml=0.009 → 75-84 trades — statistically meaningful.

### Diagnosis

The ML signal quality is NOT the problem (79-81% WR on signal exits confirmed in Round 1).
The entry TIMING is the problem: entries are firing mid-candle on 15m timeframe but the signal is trained on 4h candle returns. By the time the 4h candle closes unfavorably, the position is already in drawdown beyond the SL.

---

## 🔧 What Needs to Change (Perplexity's Job)

Three structural options — pick one or combine:

### Option A: Trailing Stoploss (easiest)
Replace fixed `stoploss = -0.03` with trailing stop in config:
```json
"trailing_stop": true,
"trailing_stop_positive": 0.01,
"trailing_stop_positive_offset": 0.02,
"trailing_only_offset_is_reached": true
```
This lets winners run while cutting losers early once price reverses.
Test in autobacktest with no SL parameter (trailing handles it).

### Option B: Custom Stoploss — ATR-based (better)
```python
def custom_stoploss(self, current_time, current_rate, current_profit, dataframe, trade):
    atr = dataframe['atr_14'].iloc[-1]
    return -2 * atr / current_rate  # 2× ATR below entry
```
Dynamic SL that widens in volatile markets, tightens in calm.

### Option C: Regime-Aware Entry (structural fix)
Only enter in bull regime (BTC above 200-day MA). Skip all entries in bear market.
Test period 2025-02-01 to 2026-04-01 was a 47% bear market — no strategy designed for trending markets should pass here. The real question is whether it works in bull conditions.

### Recommended path
Start with Option A (trailing stop) — 2-line config change, run Round 3 grid.
If still failing, pivot to Option C (regime filter).

---

## 📁 Current File State

| File | Version | State |
|---|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | v5 | ✅ Unchanged |
| `scripts/autobacktest.py` | v3.1 | ✅ Config patching fixed, all 4 patch rules verified |
| `scripts/autobacktest_grid.json` | v2 | ⚠️ Remove roi_multiplier — it's a dead lever |
| `_autobacktest_results.csv` | Round 2 | ✅ Committed (48 rows total: 12 Round 1 + 36 Round 2) |
| `finbuddy_memory/strategies/graveyard.md` | updated | ✅ Round 2 entry added |

## ⚠️ autobacktest.py — Confirmed Working

All patch rules verified against v5 strategy:
- `ml_threshold` → patches `dataframe["&-s_close"] > X)  # v5` ✅
- `stoploss` → patches `stoploss = X` in strategy + backtest_config.json ✅
- `atr_threshold` → patches `dataframe["atr_ratio"] > X` ✅
- `roi_multiplier` → patches `minimal_roi["0"]` in config (but irrelevant — dead lever) ✅

Config patching: `write_patched_config()` patches stoploss + minimal_roi in backtest_config.json
and docker cp's it to `/freqtrade/scripts/backtest_config.json` before each combo. ✅

---

## 🔄 Collaboration Rules

| Who | Does What |
|---|---|
| **Gaurav** | Decides when to run, approves phase transitions |
| **Claude Code** | Runs scripts, commits outputs, never touches strategy logic |
| **Perplexity** | Designs strategy, reads CSVs, writes/fixes code, updates docs |

---

*Written by Claude Code — 2026-05-01 ~20:00 IST*
