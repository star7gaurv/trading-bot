# FinBuddy Deep Audit — May 4 2026

**Auditor:** Claude (compassionate-clarke worktree)
**Branch:** `gaurav` (worktree)
**Scope:** strategy / freqai model / backtest pipeline / risk engine / config / live dry-run / memory / security

> Headline: **the v11 strategy currently fires zero trades anywhere — backtest or live.**
> Two independent bugs each kill all signals. The grid CSV that `promote_best_config.py`
> reads is therefore pure noise and a "winner" promoted off it would be meaningless.

---

## CRITICAL (must fix before live trading)

### C1. Strategy reads classifier proba under the wrong column names → 0 trades on any run
- **File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py:436-437` and `:538-539`
- **Problem:** Strategy looks for `&-s_label_proba_+1`, `&-s_label_proba_1`, `&-s_label_proba_-1`. FreqAI's `LightGBMClassifier` actually emits the per-class probability columns named after the **stringified class label only** (no `&-s_label_proba_` prefix). Verified by inspecting `models/finbuddy_backtest_v11/backtesting_predictions/cb_btc_*_prediction.feather` — its columns are: `['date', '&-s_label', '&-s_label_mean', '&-s_label_std', '-1.0', '1.0', 'do_predict']`. There is no `&-s_label_proba_*` column anywhere.
- **Effect:** `proba_long` and `proba_short` both default to `pd.Series(0.0)`, so `proba_long > 0.55` is always False. Confirmed by `_autobacktest_results.csv`: 25 of 25 most-recent runs returned `trades=0`. Live dry-run would behave the same once the model issue (C2) is fixed.
- **Fix:** Read `dataframe["1.0"]` for long-class proba and `dataframe["-1.0"]` for short-class proba (the classes correspond to the float32 labels `1.0` and `-1.0` written by `set_freqai_targets`). Keep a `.get(...)` fallback so the early candles (before first training window) don't KeyError.
- **Status:** APPLIED in this commit.

### C2. Live config points at `FinBuddyLLMModel` (a Regressor) but v11 strategy needs a Classifier
- **File:** `freqtrade/user_data/config.json:167` (`"freqaimodel": "FinBuddyLLMModel"`)
- **Problem:** `FinBuddyLLMModel` inherits from `LightGBMRegressor` and produces a single regression target `&-s_close`. v11 strategy expects per-class probability columns from `LightGBMClassifier`. With this combination the strategy gets neither `&-s_close` nor any class column → 0 entries forever (compounding C1).
- **Fix:** Set `"freqaimodel": "LightGBMClassifier"` in `user_data/config.json` (matches what `scripts/backtest_config.json` already uses). The `FinBuddyLLMModel` waterfall design needs to be rewritten as a Classifier subclass before it can be re-enabled; documented as HIGH H1.
- **Status:** APPLIED in this commit.

### C3. Telegram bot token committed to the repo
- **File:** `freqtrade/user_data/config.json:94` (`"token": "8557119080:AAH9KPMI..."`)
- **Problem:** `CLAUDE.md` explicitly states "tokens intentionally NOT committed to repo config.json — live only on server". The token is currently in git history. Anyone with read access to the repo can hijack the FreqTrade Telegram bot (post fake messages, read trade activity).
- **Fix:** Strip the token from the committed file (replace with empty string + `_comment` to load from env / fill on server). The user must rotate the token via @BotFather and re-paste it into the *server-side only* `config.json`. A history rewrite (filter-repo / BFG) is also recommended but out of scope for an automated fix.
- **Status:** APPLIED in this commit (token redacted in repo file). Token rotation is a manual user action — flagged in next-action list.

### C4. Backtest grid producing only zero-trade rows pollutes promotion pipeline
- **File:** `_autobacktest_results.csv` (current run lines 16–25), upstream cause = C1
- **Problem:** `scripts/promote_best_config.py:85-89` falls back to "highest Sharpe with trades >= 30" when no row passes thresholds; with the current dataset every row has 0 trades, so `select_best` returns `None` and exits 0 — but as soon as C1+C2 are fixed and the grid yields any row with ≥30 trades, `promote_preset()` will write whatever the topmost row says, even if Sharpe is negative. The fallback path has no minimum-Sharpe floor.
- **Fix (deferred to HIGH):** add a hard floor `sharpe > 0` to the fallback branch before promoting. Documented as H4. Not auto-fixed because it changes behavior of an already-running pipeline; user should review.
- **Status:** flagged in High; the more urgent move is to drop existing zero-trade rows after C1/C2 land. Recommended manual step: `> _autobacktest_results.csv` (truncate) before re-running the grid.

### C5. Live dry-run flooded with `KeyError` on dynamic pairlist members
- **File (effect):** docker logs `freqtrade --tail 80` shows repeated `KeyError: 'NAORIS/USDT:USDT'`, `'ORDI/USDT:USDT'`, "Empty candle (OHLCV) data for pair LAB/USDT:USDT", etc. Strategy crashes at `populate_indicators` line 207 (`bb["upperband"] - bb["lowerband"]`) for these pairs.
- **Root cause:** `freqtrade/user_data/config.json:57-90` uses `VolumePairList { number_assets: 30 }` against Binance Futures. Many top-by-volume futures pairs have <`startup_candle_count=400` × 15m of history, so the dataframe is empty and FreqAI's `update_historic_data` raises `KeyError` before indicators are computed.
- **Fix:** switch live to `StaticPairList` with the same 5 pairs the backtest uses (`BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT`, `BNB/USDT:USDT`, `XRP/USDT:USDT`), or keep `VolumePairList` but tighten with `AgeFilter { min_days_listed: 30 }`. Auto-fix is risky (changes pair universe) — flagged for user.
- **Status:** documented; not auto-applied. Manual: edit `pair_whitelist` + replace `pairlists` with `[{"method":"StaticPairList"}]`.

---

## HIGH (fix this week)

### H1. `FinBuddyLLMModel` is a Regressor; v11 needs a Classifier subclass
- **File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py:46-50, 83`
- The waterfall design (xAI Grok → Groq → raw LGBM) is sound, but the base class must change to `LightGBMClassifier` and the `predict()` blend logic must operate on class probabilities (e.g. nudge `1.0`/`-1.0` columns toward CONFIRM/REJECT) instead of a regression scalar `&-s_close`. Until this is rewritten, `freqaimodel` must stay `LightGBMClassifier` (C2).

### H2. `_get_current_regime()` resolves to a path that doesn't exist inside the container
- **File:** `FinBuddyFreqAI.py:144-153`
- `self.config["user_data_dir"]` inside the docker container is `/freqtrade/user_data`; `../../finbuddy_memory/regimes/current.json` resolves to `/finbuddy_memory/regimes/current.json` (root), which is not bind-mounted. Regime is therefore always silently NEUTRAL → `_REGIME_MULTIPLIERS["NEUTRAL"]=1.0` → no Phase-3 sizing benefit. Fix: bind-mount `finbuddy_memory/` into the container or move `current.json` under `user_data/`.

### H3. `label_period_candles=3` (config) ≠ docstring's design value `12`
- **File:** `freqtrade/user_data/config.json:151` and `scripts/backtest_config.json:82` vs strategy docstring lines 35, 273
- With `period=3` (45 min) and `k_tp=2.0`/`k_sl=1.0`, almost every label resolves on the time-barrier branch with very small returns; the classifier sees noisy targets. Either bump config to `12` or update the docstring. Recommendation: set `12`, re-train.

### H4. `promote_best_config.py` fallback has no minimum Sharpe / PF floor
- **File:** `scripts/promote_best_config.py:85-89`
- `select_best`'s fallback only requires `trades >= 30`. After C1+C2 land, a strategy with negative Sharpe could still be top-ranked and promoted. Add `sharpe > 0` and `profit_factor > 1.0` floors to the fallback path.

### H5. `set_freqai_targets` writes `0` then `NaN` over the tail — order of operations is fine but `np.zeros` initializer means rows whose loop body never runs (none, given the range) silently default to 0
- **File:** `FinBuddyFreqAI.py:293-319`
- Currently safe (loop covers `range(n - label_period)` and the tail is overwritten with `NaN`), but defensively initializing with `np.nan` makes the contract explicit. Low risk, light fix.

### H6. `RiskEngine` not wired into the strategy
- **File:** `freqtrade/user_data/scripts/risk_engine.py` exists; `FinBuddyFreqAI.py` never imports it.
- `custom_stake_amount` only applies regime sizing, not Kelly-light position sizing or liquidation-buffer guards. Phase 9 is "scaffolded" but not load-bearing. Wire `RiskEngine.position_size()` into `custom_stake_amount` and `RiskEngine.liquidation_guard()` into `confirm_trade_entry`.

### H7. PATCH_RULES regex for `ml_threshold` may patch unintended `0.55` literals if any are added later
- **File:** `scripts/autobacktest.py:104-106`
- The regex `(proba_long\s*>\s*)0\.55|(proba_short\s*>\s*)0\.55` is fine *today* (only the entry thresholds match), but is brittle: any new `0.55` literal next to `proba_long`/`proba_short` will be patched. Anchoring on a unique sentinel comment (e.g. `# ML_ENTRY_THRESHOLD`) is safer.

### H8. `informative_timeframes` is not a real Freqtrade hook
- **File:** `FinBuddyFreqAI.py:68`
- Freqtrade uses `informative_pairs()` method (or `@informative` decorators) to register higher-tf data. The class attribute `informative_timeframes` is ignored by the framework; 1h/4h/1d data only loads because `dp.get_pair_dataframe()` is called inside `populate_indicators`. This works but is fragile (no warm-up guarantee, no caching). Implement `def informative_pairs(self)` returning `[("BTC/USDT:USDT","1d"),("BTC/USDT:USDT","4h"),(metadata['pair'],"1h")]`.

---

## MEDIUM (fix this month)

- **M1.** `freqtrade/user_data/strategies/AiGuardrailStrategy.py` is retired per CLAUDE.md but still in the directory — delete to avoid accidental restart.
- **M2.** `include_corr_pairlist: ["BTC/USDT"]` in `user_data/config.json:148` uses spot-format symbol while `trading_mode=futures`. Should be `"BTC/USDT:USDT"` to match the live whitelist format. Backtest config does this correctly already.
- **M3.** `webhook.url` in `user_data/config.json:118` points to `https://n8n.star7gaurav.in/webhook/freqtrade-events`, but N8N has been disabled per CLAUDE.md. Either disable the webhook block or repoint to the executor.
- **M4.** `process_throttle_secs: 5` (config.json:113) is aggressive for a 15m timeframe — bumps CPU on Oracle Free Tier needlessly. 30–60s is plenty.
- **M5.** Strategy v11 doc says default `label_period_candles=12` — see H3.
- **M6.** `_REGIME_MULTIPLIERS["CRASH"]=0.0` makes `custom_stake_amount` return `0.0`, which Freqtrade treats as "skip" but also logs warnings; consider using `min_stake` for CRASH or rejecting at `confirm_trade_entry` for a cleaner audit trail.
- **M7.** `FinBuddyLLMModel.predict` mutates `pred_df.at[..., '&-s_close']` after a per-pair, per-tick LLM call with up to 8s timeout. In live mode this can block the throttle loop on a slow Grok response. Move LLM scoring off the hot path (precompute on a 5-min cron, write JSON, read in `populate_indicators`).
- **M8.** `_get_tradingview_signal()` reads a JSON file every `populate_indicators` call (`FinBuddyFreqAI.py:173-191`) — fine for now but should cache by mtime.
- **M9.** `phase8_futures_setup.py` is purely informational; no exit code differentiation when a fail is detected — add `sys.exit(1)` on hard mismatch so it can run in CI.

---

## LOW / NICE TO HAVE

- **L1.** `set_freqai_targets` Python `for` loop at `FinBuddyFreqAI.py:295` is O(n × label_period). Workable today (~2M ops on 5 pairs × 1y × 15m × 12), but a NumPy vectorized version (`high.rolling(label_period).max()` etc.) would 10× the speed.
- **L2.** `requests` import is wrapped in `try/except ImportError` (FinBuddyLLMModel.py:52-55) but Freqtrade base image always ships with it — dead branch.
- **L3.** `autobacktest.py` cleanup at end (`os.unlink(TEMP_STRATEGY_PATH)`) doesn't run if `main()` raises mid-loop; wrap in `finally`.
- **L4.** Old `experiments/` and `session_log_*.md` files at repo root could be moved to `archive/`.
- **L5.** `parse_backtest.py` not audited here (out of explicit scope but feeds the CSV — quick scan recommended).
- **L6.** `_autobacktest_results.csv` lives at repo root — should be in `experiments/` or `finbuddy_memory/research/`.

---

## WHAT IS WORKING WELL

- **Triple-barrier label** (`set_freqai_targets`) is correctly implemented per López de Prado: TP/SL price thresholds derived from per-bar ATR%, scanned forward bar-by-bar with proper precedence (whichever barrier is hit first wins), time-barrier sign-of-return fallback, NaN tail. This is the right architecture.
- **`custom_stoploss` (v10 carryover)** is correct: returns `None` on missing data, anchors to entry via `stoploss_from_open`, and the lock-at-+1.5×ATR trailing branch is gated by `current_profit > atr_pct`. The Round 5 in-sample lift (Sharpe -0.78 → +0.13) tracks back to this and is real.
- **BTC MA200 macro gate** (`btc_macro_bull`) is wired correctly into both long and short branches with an env-var ablation switch (`BTC_MA200_GATE`).
- **`autobacktest.py` v4** uses `/tmp` temp files for the patched strategy + docker-cp'd patched config — clean separation, no in-place edits to source. Good DRY discipline.
- **`scripts/promote_best_config.py`** structurally is good — separates select / walk-forward / promote, writes audit artifacts (JSON + Markdown) before mutating the strategy.
- **`RiskEngine`** has a real self-test (`_selftest()`) with 9 cases covering edge inputs. Just needs to be wired into the strategy (H6).
- **Phase-7 cron infrastructure** is up: data fetcher, HMM regime, memory writer, executor, karpathy loop all firing on schedule per `CLAUDE_HANDOFF.md`.
- **Backtest config (`scripts/backtest_config.json`)** is internally correct (futures + isolated + LightGBMClassifier + sane stake) — once C1 lands, the grid should produce real numbers.

---

## RECOMMENDED NEXT 3 TASKS IN PRIORITY ORDER

1. **Re-run the grid after C1+C2 land.** Truncate `_autobacktest_results.csv`, drop `freqtrade/user_data/models/finbuddy_backtest_v11/` so models retrain on the fixed targets, run `BACKTEST_TIMERANGE=20240101-20250101 python3 scripts/autobacktest.py`. The signal "did the proba columns finally light up" is whether `trades` per row is > 0. Goal: at least one row crossing all four acceptance thresholds.
2. **Rotate the Telegram bot token via @BotFather** (token `8557119080:...` is now public). Paste the new token only into the *server-side* `freqtrade/user_data/config.json` and add `freqtrade/user_data/config.json` to a server-only mechanism (`.env` + envsubst, or `config.private.json` git-ignored, merged at startup). Tighten gitignore so this can't recur.
3. **Switch the live dry-run to `StaticPairList`** with the same 5 pairs the backtester uses, retrain FreqAI, and verify zero `KeyError` in `docker logs freqtrade` for one full hour. Only after that should H6 (RiskEngine wiring) and H1 (LLM Classifier rewrite) proceed.

---

_Generated 2026-05-04 — Claude (compassionate-clarke worktree)._

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[research/README]]*
