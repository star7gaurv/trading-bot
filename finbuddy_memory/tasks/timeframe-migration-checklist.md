# Timeframe Migration Checklist (15m → 1h) — COMPLETE dependency map

> Created 2026-06-20. Audited via full-repo grep. This is the authoritative "nothing missed" list.
> RULE: the live flip to 1h happens ONLY after a 1h backtest validates (do not flip on the IC glimmer).
> RECOMMENDED MECHANISM: centralize all candle-count constants as WALL-CLOCK derived from the
> timeframe (one source of truth) so changing `timeframe` propagates everywhere — this is what makes
> "missed a hardcoded constant" structurally impossible. See section C.

## A. Base timeframe declaration — MUST change (string "15m" → "1h")
- [ ] `freqtrade/user_data/config.json` → `"timeframe"`
- [ ] strategy `FinBuddyFreqAI_v23.py:97` → `timeframe = "15m"`
- [ ] new config `v23_regression_1h_di_config.json` (copy of the 15m one, edited) — referenced by brain
- [ ] `scripts/brain/hypothesis_gen.py`: SEED `timeframe`/`config_file` (158-159), `TF_CONFIG_MAP_V23` (389), choices lists (358/379)
- [ ] `scripts/brain/runner.py`: defaults `cfg.get("timeframe","15m")` (483) + `config_file` defaults (456/597/649)
- [ ] `scripts/walk_forward.py:519` default; `walkforward_daily.sh:70`, `walkforward_deep.sh:50`, `walkforward_monthly.sh:34` `--timeframe 15m`
- [ ] `strategies/registry.json` (3 entries) — registry metadata

## B. Informative-timeframe coupling — MUST rethink (base can't equal an informative TF)
- [ ] strategy `informative_pairs():124-126` — the `(pair,"1h")` line now EQUALS the base → REMOVE it; keep 4h/1d; the `(pair,"15m")` line becomes a *lower* TF (drop or keep as extra).
- [ ] config `include_timeframes: ['1h','4h']` (all v23 configs) — `1h` equals base → change to e.g. `['4h','1d']`.

## C. Candle-count constants that change MEANING at 1h (value stays, wall-clock ×4) — THE DANGEROUS GROUP
> Best fix: derive each from wall-clock so it auto-scales. Shown as: const — 15m value (wall-clock) → 1h value to preserve wall-clock.
- [ ] `startup_candle_count` 2400 (25d) → **720** (30d) [must also be ≥ ROLLING warmup; was capped by Binance 15m fetch, not an issue at 1h]
- [ ] `ROLLING` (z-score, set_freqai_targets:1452) 2880 (30d) → **720**
- [ ] `_CENTERING_WINDOW` 1920 (20d) → **480**  [COUPLING: must stay < startup_candle_count]
- [ ] `_CENTERING_MIN_PERIODS` 200 → scale to **~50** (keep ∝ ROLLING warmup)
- [ ] `label_period_candles` (config) 12 (3h) → **3** (3h) — or pick a deliberate 1h horizon; NOTE this is in _TRAIN_SHAPE_KEYS
- [ ] `FREQAI_META_HORIZON` default 24 (6h) → **6**; META_TP/SL_MULT are ATR-ratios (TF-agnostic ✓)
- [ ] rolling(96) high/low bb_pct (1210-1211) 1d → **24**
- [ ] rel-strength RSI windows (14,28,56) at 1332/1338 — 3.5/7/14h → decide (keep wall-clock ≈ 4,8,14 or keep RSI-natural)
- [ ] std_factor `rolling(100,min_periods=10)` (1580/1587) on predictions — window meaning changes; review
- [ ] bounce-guard RSI(56) "~1h horizon on 15m" (1754) → at 1h = 56h; rethink

## D. Time-based math — ALREADY SAFE (uses timeframe_to_seconds, auto-adjusts) — DO NOT TOUCH
- ✅ `custom_stoploss`/`custom_exit` candles_open (164, 261); reentry cooldown (1101). Verified TF-agnostic.

## E. BTC reference loader — MUST change
- [ ] `_load_btc_15m` / `_btc_15m_df` / `_load_btc_15m()` (365, 498-516, 525) loads BTC **15m** feather for rel-strength → load BTC **1h**. Rename for clarity.

## F. Data pipeline — mostly OK
- ✅ `download_data_daily.sh`/`backfill_historical_data.sh` already pull `15m 30m 1h 4h 1d` → 1h data exists (38 pairs, back to 2020 for majors).
- ✅ funding (8h) / OI (hourly) parquets: merge_asof still valid; OI aligns NATIVELY to 1h (better than 15m).
- ✅ regime parquet (build_historical_regime on BTC 4h) is independent of trading TF.
- [ ] Verify every whitelisted pair has ≥ (startup+train) 1h history before its window start (the historical NaN-crash cause).

## G. Dashboard
- [ ] `dashboard/streamer.py:623` candle fetch `"timeframe":"15m"` → "1h"
- ✅ `dashboard/system_health.py` `load_15m` = OS load average, NOT trading TF → DO NOT TOUCH (false match).

## H. Brain config & cache
- ✅ `timeframe` is already in `_TRAIN_SHAPE_KEYS` → 1h experiments get their OWN cache family automatically (no collision with 15m models).
- [ ] `backtest_config.json` is legacy 5m (label_period 72) — confirm unused or update separately.

## I. Apply-live recipe (when validated)
- [ ] Bump FreqAI identifier; flush `historic_predictions.pkl` + `pair_dictionary.json`; `docker-compose up -d` (NOT restart). All trained models retrain on 1h.

## J. Verification gates (no bug ships)
- [ ] After centralization: assert that at `timeframe="15m"` EVERY derived constant == its current hardcoded value (byte-identical live behavior). Unit test.
- [ ] `py_compile` + in-container module load.
- [ ] 1h smoke backtest (2 pairs, 2 weeks) trains + runs end-to-end, no NaN crash.
- [ ] IC gate already shows the 1h signal is `btc_vol_12` (volatility, not direction) — temper expectations.


## ✅ STATUS 2026-06-20: strategy CENTRALIZED (section C done in code)
FinBuddyFreqAI_v23.py now derives startup_candle_count / _Z_ROLLING / _CENTERING_WINDOW /
_DAY_CANDLES / _PRED_STD_WINDOW / _META_HORIZON_DEFAULT from `_CANDLES_PER_DAY =
86400//timeframe_to_seconds(timeframe)`. informative_pairs() and the BTC-ref feather path are
now timeframe-derived too. VERIFIED byte-identical at 15m (all 8 constants == prior hardcoded
values; informative order preserved). REMAINING for the actual 1h flip: create
v23_regression_1h_di_config.json (timeframe+include_timeframes+label_period_candles), flip
config.json/strategy timeframe, brain TF maps, WF scripts, dashboard:623, identifier bump+flush.
RSI/ATR indicator PERIODS (14/28/56) deliberately left TF-natural (documented choice).
