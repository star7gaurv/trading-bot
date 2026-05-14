# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Claude Code  
**Date:** 2026-05-13  
**For:** Claude Code (next session)  
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI.py` **v20 code** — asymmetric barriers k_tp=2.0 / k_sl=1.0, 2x leverage, macro safety gates active, regime path fix active, fixed news/trends data fetchers. |
| Live FreqAI identifier | `finbuddy_v20_asym_1778575138` |
| FreqAI model | `FinBuddyLLMModel` **v5** (LightGBM + LLM screen, auto-confirm ≥0.90) |
| Pairs | 25, 1h TF, futures isolated |
| Regime | 🐻 BEAR |
| Live P&L | ~+$4 USDT (4 open shorts — now protected with ATR stops) |
| Bot status | ✅ Running — Optimized v20 with 2x leverage and macro safety gates |

---

## 🚨 CRITICAL BUG FIXED THIS SESSION (2026-05-13) — commit `21796ea`

**Bug**: `custom_stoploss` has been returning `None` for ALL trades (long and short) since v17.

**Root cause**: `stoploss_from_open()` ALWAYS returns `>= 0`. The guards were `< 0` → always False → always `None` → hard `-0.08` config stoploss fired for every loss.

**Evidence**: NEAR short #64 ran 7.4h to exactly -8.14% (hard stop + slippage). All 4 open shorts showed `sl=0.0000` before fix.

**Fix**: Changed both `< 0` guards to `> 0` (the `= 0` case means stop already breached — correctly discarded).

**Implication for previous backtests**: v17/v18/v19 also ran without ATR stops. Real PF with working stops would have been better. v20 campaign will be the first with ATR protection actually working.

---

## 🔧 What Was Built This Session (2026-05-12–13)

### v20 — Asymmetric Barriers (commit `ed02369`)

**Root cause fixed**: v19 0/24 FAIL was structural. Symmetric 1:1 R:R + 1,700 trades/yr fee drag (~$196/yr) exactly cancelled gross edge (best PF=0.996). No grid parameter could fix it.

**Changes:**
1. `K_MULT` split → `FREQAI_K_TP` (default 2.0) + `FREQAI_K_SL` (default 1.0)
2. `custom_stoploss`: initial stop at K_SL×ATR (tight, cuts losers fast); trail locks at K_TP×ATR once profit > K_TP×ATR
3. `set_freqai_targets`: asymmetric TP/SL barriers in labeling — more labels resolve within lp=6 (tighter SL=1×ATR hits sooner)
4. `feature_engineering_std` → `feature_engineering_standard` (NOW ACTIVE) — adds day_of_week, hour_of_day, raw OHLCV
5. Enter tags: `freqai_lgbm_v20_long` / `freqai_lgbm_v20_short`
6. `config.json` identifier bumped → forced full retrain on restart

**Theoretical PF at 62% WR:**
- K_TP=2.0 / K_SL=1.0 → PF = **3.26** (vs PF≈1 with symmetric)
- Break-even WR drops from 52.5% → **33%** (massive margin above fee drag)

---

## 🔬 Next: Run v20 Campaign

**Command:**
```bash
cd /home/ubuntu/var/www/html/trade
python scripts/autobacktest_v20.py
```

**Grid**: K_TP∈{1.5,2.0,2.5} × K_SL∈{0.8,1.0} × ml_threshold∈{0.60,0.65,0.70} = **36 runs**  
**Duration**: ~6h on Oracle Free Tier (36 isolated docker-compose runs)  
**Results**: `_autobacktest_v20_results.csv` + Telegram notifications every 6 runs  

**Run bull window first to get early signal:**
```bash
python scripts/autobacktest_v20.py --window bull
```

**If bull passes:** run bear window, then walk-forward, then Phase 10.  
**If bull fails:** check CSV for best combo — identify which parameter is still wrong.

---

## 📁 Key Files

| File | Purpose |
|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | Active strategy — **v20 code** |
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | LLM model v5 — auto-confirm fix |
| `freqtrade/user_data/config.json` | Live bot config — identifier `finbuddy_v20_asym_1778575138` |
| `freqtrade/user_data/backtest_config.json` | Backtest-only config |
| `scripts/autobacktest_v20.py` | **v20 campaign runner** |
| `scripts/autobacktest_v20_grid.json` | **v20 grid definition** |
| `scripts/autobacktest_v19.py` | v19 runner (reference only — do not re-run) |
| `_autobacktest_v19_results.csv` | v19 results (all 24 FAIL — archived) |

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
