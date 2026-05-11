# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Claude Code  
**Date:** 2026-05-11  
**For:** Claude Code (next session)  
**Branch:** `master`

---

## ✅ Where We Are — Current State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI.py` **v18 code** |
| Live FreqAI identifier | `finbuddy_v17_sym_1778353539` (v17 models, v18 stoploss logic) |
| Enter tags in Telegram | `freqai_lgbm_v18_long` / `freqai_lgbm_v18_short` |
| FreqAI model | `FinBuddyLLMModel` (LightGBM + Grok-3-mini screen) |
| Pairs | 25, 1h TF, futures isolated |
| Walk-forward | ⏸️ Paused — strategy architecture needs fixing before it's worth running |

### Key v18 Code Changes (shipped 2026-05-10, commits `840fad4`, `65b8064`)
1. **`custom_stoploss` is now ACTIVE** — v17 had two bugs making it a no-op (both `>0` checks discarded valid negative stops + trail activated at wrong level). Fixed in v18.
2. **datasieve `Pipeline.features_in` shim** — monkey-patch at module load. Prevents `AttributeError` in FreqAI backtesting when training fails mid-fold.
3. **K_MULT / ML_THRESHOLD via ENV VARs** (`FREQAI_K_MULT`, `FREQAI_ML_THRESHOLD`, default 2.0 / 0.60)

---

## ❌ v18 Campaign — Completed 2026-05-10, 0/24 PASS

**24 runs**: k_mult∈{1.0,1.5,2.0} × label_period∈{12,24} × ml_threshold∈{0.60,0.65} × bull+bear windows.

| Metric | All 24 runs | Target |
|---|---|---|
| Win Rate | 61–64% ✅ | >50% |
| Max Drawdown | 1.57–4.60% ✅ | <20% |
| Sharpe | −0.12 to −4.88 ❌ | >0.5 |
| Profit Factor | 0.83–0.996 ❌ | >1.2 |

**Root cause — fee drag eats the edge:**
- Trade count: ~1,700/yr (4.6/day at max 4 positions)
- Fee drag: 1,700 × $144 avg stake × 0.08% round-trip ≈ **$196/yr** on $10k wallet
- Gross profit best case (k=1.0, bull): ~$195 → net: **−$9**
- Losers held 2× longer than winners (14h vs 7h avg) → extra funding fee drag on losing positions

**Grid was inert**: Sweeping k_mult, label_period, ml_threshold cannot fix a structural R:R problem.

**Results CSV**: `_autobacktest_v18_results.csv` (committed)

---

## 🔬 Next: v19 — Asymmetric Barriers

**The fix**: Split `K_MULT` into separate `K_TP` and `K_SL`:

```python
K_TP = float(os.getenv("FREQAI_K_TP", "2.0"))  # take-profit barrier: 2×ATR
K_SL = float(os.getenv("FREQAI_K_SL", "1.0"))  # stop-loss barrier:  1×ATR
```

**Why it works**: At 62% WR → theoretical PF = (0.62 × 2.0) / (0.38 × 1.0) = **3.26** — far above fee drag. Break-even WR drops from 52.5% → 35%.

**Training labels** must match: "L" fires only when price reaches +K_TP×ATR before −K_SL×ATR. Sparser signal, but each one confirms a real move.

**`custom_stoploss` changes needed**:
- Initial stop: `stoploss_from_open(-K_SL×ATR, current_profit, ...)`
- Trail lock: activates when `current_profit > K_TP×ATR`, locks at `+K_TP×ATR` from open

**Proposed v19 grid**: K_TP ∈ {1.5, 2.0, 2.5} × K_SL ∈ {0.8, 1.0} × ml_threshold ∈ {0.60, 0.65, 0.70} = 18 combos × 2 windows = **36 runs**

**Campaign runner**: `scripts/autobacktest_v18.py` (rename/update to v19). Update `autobacktest_v18_grid.json`. Change ENV VAR names from `FREQAI_K_MULT` → `FREQAI_K_TP` + `FREQAI_K_SL` in both strategy and grid runner.

---

## 📁 Key Files

| File | Purpose |
|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | Active strategy — v18 code |
| `freqtrade/user_data/config.json` | Live bot config (identifier: `finbuddy_v17_sym_1778353539`) |
| `freqtrade/user_data/backtest_config.json` | Backtest-only config (1h, 5 pairs, no secrets) |
| `scripts/autobacktest_v18.py` | Grid campaign runner — reuse/fork for v19 |
| `scripts/autobacktest_v18_grid.json` | Grid definition — update for v19 |
| `_autobacktest_v18_results.csv` | v18 results with corrected PF values |

---

## ⚠️ Hard-Learned Rules for Backtesting

1. **Always `docker-compose run --rm --no-deps`** — never `docker exec` for backtesting. Running in the live container triggers datasieve state conflicts.
2. **Download needs `--prepend` to fill backwards** — `download-data` only appends to file end. DOGE needed `--prepend 20230901-20240115` to cover FreqAI's 90-day warmup before the bull window.
3. **Config path inside container**: only `./user_data:/freqtrade/user_data` is mounted. Use `/freqtrade/user_data/backtest_config.json`, not `/freqtrade/scripts/...`.
4. **After campaign: always `--reparse`** — running process has old parser in memory. Run `python3 scripts/autobacktest_v18.py --reparse` after campaign completes to regenerate CSV with fixed parser.
5. **Profit factor field**: FreqTrade 2026 reports `profit_factor` directly in the summary JSON. Do NOT compute from `profit_sum`/`loss_sum` (they don't exist in this version).

---

## 🔴 What NOT To Do

- Do NOT run more v18 backtests — the grid is exhausted and inert. The issue is structural R:R, not parameter tuning.
- Do NOT restart walk-forward until v19 shows PF>1.2 in at least the bull window.
- Do NOT modify `finbuddy_memory/` contents manually — owned by cron scripts.

---

*End of handoff — 2026-05-11*
