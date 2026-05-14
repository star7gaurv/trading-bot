# Phase 1 — FreqAI as the Brain

> FreqAI is the primary signal intelligence. Trains on rolling market data (1h TF, 25 pairs, Binance Futures USDT-M), produces ML-powered long/short signals, confirmed by LLM layer.

**Reference:** [FreqAI Architecture Guide](../finbuddy_memory/research/2026-04-27-freqai-architecture-guide.md)  
**Official Docs:** https://www.freqtrade.io/en/stable/freqai/

---

## Status as of 2026-05-09 evening

- Task 1.1: ✅ COMPLETE
- Task 1.2: ✅ COMPLETE (FinBuddyLLMModel v3 active, LLM layer working)
- Task 1.3: ⏳ RUNNING — Walk-forward #5 (T190609) started 2026-05-09 19:06 UTC
- Task 1.4: ✅ COMPLETE

---

## Task 1.1 — Build FreqAI Strategy
**Status:** ✅ COMPLETE  
**File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py` (v17)

**Live configuration:**
- 1h TF, 25 pairs, Binance USDT-M perpetual, `can_short=True`
- Triple-barrier labeling: `k_tp=k_sl=2.0` (symmetric → P(L)=50% base rate)
- `label_period_candles=6` (6h window), `train_period_days=90`
- `custom_stoploss()`: 2.0×ATR initial, trail locks at +2.0×ATR once profit > 1×ATR
- `custom_exit()`: 24h time limit (24 × 1h candles)
- Regime kill-switches: CRASH/BEAR → no longs; BULL/EUPHORIA → no shorts
- Regime-aware exits: CRASH/BEAR → exit longs at 0.55, BULL/EUPHORIA → exit shorts at 0.55, NEUTRAL → 0.65 both
- Cluster cap: max 2 trades per MEGA_CAP (BTC/ETH/SOL/etc) or L2 (ARB/OP/etc) cluster
- Funding-rate long guard: blocks longs if BTC perp funding >0.05%/8h
- Enter tags: `freqai_lgbm_v17_long` / `freqai_lgbm_v17_short`
- Identifier: `finbuddy_v17_sym_1778353539`

---

## Task 1.2 — FinBuddyLLMModel (LLM Confirmation Layer)
**Status:** ✅ COMPLETE  
**File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` (v3)

**Architecture:**
```
Market data + indicators
      ↓
LightGBMClassifier.fit()   — 100% native FreqAI training, unchanged
      ↓
LightGBMClassifier.predict() — outputs "L"/"S" class + probabilities in "L"/"S" columns
      ↓
LLM confirmation (fires when confidence = |prob - 0.5| > 5% AND cooldown elapsed):
  → call_llm(context, task="signal") via central llm_client.py
  → CONFIRM → keep signal
  → REJECT/HOLD → zero out "L" and "S" proba to 0.5 (signal suppressed below 0.60 threshold)
  → all LLM fail → raw LightGBM passthrough (safe degradation)
```

**LLM provider chain (task="signal"):** nvidia-mistral-medium → nvidia-llama-70b → nvidia-kimi-k2 → openrouter-gpt-oss-20b → openrouter-gpt-oss-120b → openrouter-nemotron-120b

**Config:** `"freqaimodel": "FinBuddyLLMModel"` in config.json (active)  
**Keys:** `NVIDIA_API_KEY` + `OPENROUTER_API_KEY` in freqtrade/.env  
**Cooldown:** 60 min per pair

---

## Task 1.3 — Walk-Forward OOS Validation
**Status:** ⏳ RUNNING — Walk-forward #5 (T190609)

Walk-forward #5 is the first valid v17 run (symmetric barriers, correct per-fold identifiers, no lookahead bias).

**Run:** `FinBuddyFreqAI_2024-01-01_2026-04-01_20260509T190609`  
**Folds:** 21 (train 6mo / test 1mo / slide 1mo)  
**Monitor:** `tail -f ~/.finbuddy/logs/walk_forward.log`  
**Notify:** `walkforward_notify.py` Telegrams PASS/FAIL automatically when done

**Gate criteria (all must pass):**
- Win Rate > 50%
- Sharpe > 0.5
- Max Drawdown < 20%
- Profit Factor > 1.2

**Prior walk-forward history:**
| Run | Issue | Result |
|---|---|---|
| T130947 (before v17) | WR=42.5% = label base rate (k_sl=1.5 bias) | FAIL — root cause identified |
| T180455 (during v17 deploy) | Killed mid-run | N/A |
| T190609 (v17, current) | First clean symmetric-barriers run | ⏳ Running |

---

## Task 1.4 — Switch Dry Run to FinBuddyFreqAI
**Status:** ✅ COMPLETE  
Bot running `FinBuddyFreqAI` with `FinBuddyLLMModel` since 2026-04-30. 36 closed trades.

---

## Phase 1 Complete When
- [x] `FinBuddyFreqAI.py` v17 deployed, trading live (Task 1.1 ✅)
- [x] `FinBuddyLLMModel.py` v3 active, LLM confirmation working (Task 1.2 ✅)
- [ ] Walk-forward OOS passes all 4 criteria (Task 1.3 ⏳)
- [x] Dry run on `FinBuddyFreqAI` + `FinBuddyLLMModel` (Task 1.4 ✅)

**Remaining gate:** Walk-forward #5 results → if PASS, proceed to Phase 10.

---

## AI Models in FreqAI

| Model | Class | Role |
|---|---|---|
| LightGBM | `LightGBMClassifier` | Primary training model — fast, tabular, great baseline |
| XGBoost | `XGBoostClassifier` | Available, not currently used |
| PyTorch MLP | `PyTorchMLPRegressor` | Available for future experimentation |

## LLM Signal Confirmation (via llm_client.py)

| Provider | Models | Key |
|---|---|---|
| NVIDIA NIM | kimi-k2, mistral-medium, llama-70b, qwen3-coder | `NVIDIA_API_KEY` |
| OpenRouter | gpt-oss-20b, gpt-oss-120b, nemotron-120b | `OPENROUTER_API_KEY` |
