# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Claude Code  
**Date:** 2026-05-12  
**For:** Claude Code (next session)  
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI.py` **v19 code** |
| Live FreqAI identifier | `finbuddy_v19_asym_1778575138` |
| FreqAI model | `FinBuddyLLMModel` **v5** (LightGBM + LLM screen, auto-confirm ≥0.90) |
| Pairs | 25, 1h TF, futures isolated |
| Regime | NEUTRAL (since 2026-05-04) |
| Live P&L | +$11 USDT, PF=1.39, WR=60.8% (54 closed trades) |
| Bot status | ✅ Running — retraining all 25 pairs on new v19 identifier |

---

## 🔧 What Was Built This Session (2026-05-12)

### v19 — Asymmetric Barriers (commit `ed02369`)

**Root cause fixed**: v18 0/24 FAIL was structural. Symmetric 1:1 R:R + 1,700 trades/yr fee drag (~$196/yr) exactly cancelled gross edge (best PF=0.996). No grid parameter could fix it.

**Changes:**
1. `K_MULT` split → `FREQAI_K_TP` (default 2.0) + `FREQAI_K_SL` (default 1.0)
2. `custom_stoploss`: initial stop at K_SL×ATR (tight, cuts losers fast); trail locks at K_TP×ATR once profit > K_TP×ATR
3. `set_freqai_targets`: asymmetric TP/SL barriers in labeling — more labels resolve within lp=6 (tighter SL=1×ATR hits sooner)
4. `feature_engineering_std` → `feature_engineering_standard` (NOW ACTIVE) — adds day_of_week, hour_of_day, raw OHLCV
5. Enter tags: `freqai_lgbm_v19_long` / `freqai_lgbm_v19_short`
6. `config.json` identifier bumped → forced full retrain on restart

**Theoretical PF at 62% WR:**
- K_TP=2.0 / K_SL=1.0 → PF = **3.26** (vs PF≈1 with symmetric)
- Break-even WR drops from 52.5% → **33%** (massive margin above fee drag)

---

## 🔬 Next: Run v19 Campaign

**Command:**
```bash
cd /home/ubuntu/var/www/html/trade
python scripts/autobacktest_v19.py
```

**Grid**: K_TP∈{1.5,2.0,2.5} × K_SL∈{0.8,1.0} × ml_threshold∈{0.60,0.65,0.70} = **36 runs**  
**Duration**: ~6h on Oracle Free Tier (36 isolated docker-compose runs)  
**Results**: `_autobacktest_v19_results.csv` + Telegram notifications every 6 runs  

**Run bull window first to get early signal:**
```bash
python scripts/autobacktest_v19.py --window bull
```

**If bull passes:** run bear window, then walk-forward, then Phase 10.  
**If bull fails:** check CSV for best combo — identify which parameter is still wrong.

---

## 📁 Key Files

| File | Purpose |
|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | Active strategy — **v19 code** |
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | LLM model v5 — auto-confirm fix |
| `freqtrade/user_data/config.json` | Live bot config — identifier `finbuddy_v19_asym_1778575138` |
| `freqtrade/user_data/backtest_config.json` | Backtest-only config |
| `scripts/autobacktest_v19.py` | **v19 campaign runner** |
| `scripts/autobacktest_v19_grid.json` | **v19 grid definition** |
| `scripts/autobacktest_v18.py` | v18 runner (reference only — do not re-run) |
| `_autobacktest_v18_results.csv` | v18 results (all 24 FAIL — archived) |

---

## ⚠️ Hard-Learned Rules for Backtesting

1. **Always `docker-compose run --rm --no-deps`** — never `docker exec` (live container triggers datasieve state conflicts)
2. **`--prepend` flag** when filling historical data backwards
3. **Config path inside container**: `/freqtrade/user_data/backtest_config.json`
4. **After campaign: `--reparse`** to regenerate CSV with fixed parser
5. **PF field**: use `s.get("profit_factor")` directly — FreqTrade 2026 reports it directly
6. **feature_engineering_standard** is now ACTIVE — any new identifier will train with the 5 extra features. Do NOT revert to `_std` without bumping identifier again.

---

## 🔴 Do NOT

- Run v18 backtests — grid exhausted, structural R:R was wrong
- Restart walk-forward until v19 bull window shows PF > 1.2
- Remove `feature_engineering_standard` without bumping identifier (feature-count crash)
- Modify `finbuddy_memory/` contents manually — owned by cron scripts

---

## 📊 v18 Results (archived — do not re-run)

24 runs, 0 PASS. WR 61–64% ✅ and DD 1.57–4.60% ✅ across all combos.  
Sharpe −0.12 to −4.88 ❌ and PF 0.83–0.996 ❌ across all combos.  
Root: fee drag + symmetric 1:1 R:R. Grid (k_mult / label_period / ml_threshold) was inert.

---

*End of handoff — 2026-05-12*
