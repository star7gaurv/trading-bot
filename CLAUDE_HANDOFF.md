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

### Round 3 (v8 — ATR custom_stoploss) — FILL IN BELOW

---

## 📈 Round 3 Results (v8 — fill in after running)

### 🐂 BULL — `20240101-20250101`
```
[FILL IN AFTER RUNNING]
```

### 🐻 BEAR — `20250101-20260401`
```
[FILL IN AFTER RUNNING]
```

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
