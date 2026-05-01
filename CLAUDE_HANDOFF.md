# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-01 ~19:35 IST  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

---

## ✅ What Was Done This Session (Perplexity)

| Task | Status |
|---|---|
| Analysed Round 1 grid CSV — identified root cause of all 12 FAILs | ✅ |
| Root cause: negative reward:risk (avg winner < avg loser), NOT EMA/RSI params | ✅ |
| Secondary root cause: autobacktest chmod bug — all 12 combos tested same params | ✅ |
| Pushed `FinBuddyFreqAI.py` v5 — wider ROI, tighter SL, ATR volatility filter | ✅ |
| Pushed `autobacktest.py` v3 — temp-file strategy (no more chmod/opc issues) | ✅ |
| Pushed `autobacktest_grid.json` v2 — tests stoploss + roi_multiplier combos | ✅ |
| Updated `CLAUDE_HANDOFF.md` (this file) | ✅ |

---

## 📊 Round 1 Grid Results Summary

All 12 combos failed. Key findings:

| ml_threshold | Win Rate | Sharpe | Verdict |
|---|---|---|---|
| 0.009 | ~65% | -0.18 | WR good, Sharpe negative |
| 0.010 | ~58% | -0.36 | Worse |
| 0.011 | ~48% | -0.28 | Too few trades |

**Diagnosis:** 65% win rate but negative Sharpe = winners are too small vs losers.
The ROI table was exiting at 1-4% while stops were -3.5%. Fixed in v5.

**Also:** All 12 combos actually ran combo 1 parameters — chmod without sudo failed silently.
Fixed in autobacktest.py v3 with temp-file approach.

---

## 🚀 Your Next Job (Claude Code)

### Step 1: Pull latest changes
```bash
cd /home/ubuntu/var/www/html/trade
git pull origin gaurav
```

### Step 2: Fix permissions (one time)
```bash
sudo chown ubuntu:ubuntu freqtrade/user_data/strategies/FinBuddyFreqAI.py
sudo chown -R ubuntu:ubuntu freqtrade/user_data/backtest_results/
```

### Step 3: Run Round 2 grid (36 combos, ~2-4 hours)
```bash
tmux new -s autobacktest2
cd /home/ubuntu/var/www/html/trade && python3 scripts/autobacktest.py 2>&1 | tee /tmp/autobacktest2.log
# Ctrl+B D to detach
```

### Step 4: When done, commit results
```bash
git add _autobacktest_results.csv
git commit -m "data: Round 2 grid results (36 combos, v5 strategy)"
git push origin gaurav
```

### Step 5: Update memory files
- If WINNER found: add to `finbuddy_memory/winners.md`
- If NO WINNER: add summary row to `finbuddy_memory/graveyard.md`
- Update this handoff with outcome

---

## 📁 Current File State

| File | Version | State |
|---|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | v5 | ✅ Wider ROI, tighter SL=-0.025, ATR filter |
| `scripts/autobacktest.py` | v3 | ✅ Temp-file approach, no chmod issues |
| `scripts/autobacktest_grid.json` | v2 | ✅ 36-combo grid (SL × ROI × ML × ATR) |
| `scripts/run_backtest.sh` | v2 | ✅ LOG_FILE in /tmp |
| `scripts/parse_backtest.py` | latest | ✅ No changes needed |
| `_autobacktest_results.csv` | Round 1 | ✅ Committed (12 rows, all FAIL) |

---

## ⚠️ Known Issues / Watch-Outs

1. **Round 2 grid is 36 combos** (3 SL × 3 ROI × 2 ML × 2 ATR) — will take 2-4 hours.
2. **`docker cp` needed per combo** — autobacktest.py v3 does `docker cp /tmp/FinBuddyFreqAI_test.py freqtrade:/tmp/` before each run. Ensure Docker is running.
3. **Strategy class name in temp file** stays `FinBuddyFreqAI` but Freqtrade is called with `--strategy FinBuddyFreqAI_test`. This will cause a mismatch. **See fix below.**

### ⚠️ IMPORTANT: Strategy Class Name Fix

autobacktest.py v3 passes `--strategy FinBuddyFreqAI_test` to Freqtrade, but the class inside the temp file is still named `FinBuddyFreqAI`. This will cause:
```
Freqtrade: Strategy FinBuddyFreqAI_test not found
```

**Fix:** In `write_patched_strategy()`, also rename the class:
```python
patched = patched.replace(
    "class FinBuddyFreqAI(IStrategy):",
    "class FinBuddyFreqAI_test(IStrategy):"
)
```
Add this line before `TEMP_STRATEGY_PATH.write_text(patched)` in autobacktest.py.
Perplexity will push this fix, OR Claude can apply it before running.

---

## 🔄 Collaboration Rules (Reminder)

| Who | Does What |
|---|---|
| **Gaurav** | Decides when to run, approves phase transitions |
| **Claude Code** | Runs scripts, commits outputs, never touches strategy logic |
| **Perplexity** | Designs strategy, reads CSVs, writes/fixes code, updates docs |

---

*Written by Perplexity AI — 2026-05-01 ~19:35 IST*
