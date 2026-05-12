# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Claude Code  
**Date:** 2026-05-12  
**For:** Claude Code (next session)  
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI.py` **v18 code** |
| Live FreqAI identifier | `finbuddy_v17_sym_1778353539` |
| FreqAI model | `FinBuddyLLMModel` **v5** (LightGBM + LLM screen, auto-confirm fix) |
| Pairs | 25, 1h TF, futures isolated |
| Regime | NEUTRAL (since 2026-05-04) |
| Walk-forward | ⏸️ Paused — wait for v19 |

---

## 🔧 What Was Fixed This Session (2026-05-12)

### Fix 1 — LLM over-filtering (commit `1010c2f`)

**Problem:** `FinBuddyLLMModel` was blocking 91% of all signals — including 90%+ confidence ML predictions. Root cause: `CONFIDENCE_THRESHOLD=0.05` sent every signal above 55% probability to the LLM. In NEUTRAL market, LLM returned REJECT/HOLD almost always.

**Fix (v5):**
- `AUTO_CONFIRM_THRESHOLD=0.40` — proba ≥ 0.90 bypasses LLM entirely (auto-confirms)
- `COOLDOWN_SECONDS` reduced 3600 → 1800 (30-min sticky veto)
- Pass rate immediately improved: 8.8% → 54.5%

### Fix 2 — `feature_engineering_std` dead code documented

**Problem:** Function was misnamed (`_std` instead of `_standard`) — FreqTrade never called it. It also referenced `_get_tradingview_signal()` which doesn't exist.

**Decision:** Left as dead code (`feature_engineering_std`) with a clear comment explaining why it MUST NOT be renamed until v19 identifier bump (activating it now would add 5 new `%-` features and cause feature-count mismatch crash on all existing models).

**When to activate:** In v19 strategy update, along with the new identifier that forces full retrain.

---

## ❌ v18 Campaign — Completed, 0/24 PASS

**Root cause — fee drag on symmetric 1:1 R:R:**
- 1,700 trades/yr × $144 avg stake × 0.08% round-trip ≈ $196/yr fee drag
- Symmetric barriers K_TP=K_SL=K_MULT → gross edge exactly cancelled by fees
- Losers held 2× longer than winners → extra funding fee drag

Grid was inert: k_mult, label_period, ml_threshold cannot fix structural R:R.

---

## 🔬 Next: v19 — Asymmetric Barriers

**The fix**: Split `K_MULT` into `K_TP` and `K_SL`:

```python
K_TP = float(os.getenv("FREQAI_K_TP", "2.0"))  # take-profit: 2×ATR
K_SL = float(os.getenv("FREQAI_K_SL", "1.0"))  # stop-loss:   1×ATR
```

At 62% WR → theoretical PF = (0.62×2.0)/(0.38×1.0) = **3.26**

**v19 grid**: K_TP∈{1.5,2.0,2.5} × K_SL∈{0.8,1.0} × ml_threshold∈{0.60,0.65,0.70} = 18 combos × 2 windows = **36 runs**

**Code changes needed for v19:**
1. Strategy: add `K_TP`/`K_SL` ENV VARs, update `set_freqai_targets(k_tp, k_sl)`, update `custom_stoploss` trail/initial logic
2. Strategy: rename `feature_engineering_std` → `feature_engineering_standard` (NOW safe because new identifier forces full retrain)
3. Campaign runner: rename/fork `autobacktest_v18.py` → `autobacktest_v19.py`, update grid JSON
4. Bump FreqAI identifier (e.g. `finbuddy_v19_asym_<timestamp>`)

---

## 📁 Key Files

| File | Purpose |
|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | Active strategy — v18 code |
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | LLM model v5 — auto-confirm fix |
| `freqtrade/user_data/config.json` | Live bot config |
| `freqtrade/user_data/backtest_config.json` | Backtest-only config |
| `scripts/autobacktest_v18.py` | Campaign runner — fork for v19 |
| `scripts/autobacktest_v18_grid.json` | Grid definition — update for v19 |
| `_autobacktest_v18_results.csv` | v18 results (all 24 FAIL) |

---

## ⚠️ Hard-Learned Rules for Backtesting

1. **Always `docker-compose run --rm --no-deps`** — never `docker exec` (live container triggers datasieve state conflicts)
2. **`--prepend` flag** when filling historical data backwards
3. **Config path inside container**: `/freqtrade/user_data/backtest_config.json`
4. **After campaign: always `--reparse`** to regenerate CSV with fixed parser
5. **PF field**: use `s.get("profit_factor")` directly — `profit_sum`/`loss_sum` don't exist in FreqTrade 2026

---

## 🔴 Do NOT

- Run more v18 backtests — grid is exhausted and the structural R:R is wrong
- Restart walk-forward until v19 shows PF>1.2 in bull window
- Rename `feature_engineering_std` → `feature_engineering_standard` without bumping identifier
- Modify `finbuddy_memory/` contents manually — owned by cron scripts

---

*End of handoff — 2026-05-12*
