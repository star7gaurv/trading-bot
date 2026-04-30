# Phase 1 — FreqAI as the Brain

> Make FreqAI the primary signal intelligence — replacing the N8N → Groq call.
> FreqAI lives inside FreqTrade, trains on rolling market data, and produces ML-powered signals.
> Custom files in user_data/ are NEVER deleted on FreqTrade upgrades (Docker volume mount).

**Reference:** [FreqAI Architecture Guide](../finbuddy_memory/research/2026-04-27-freqai-architecture-guide.md)  
**Official Docs:** https://www.freqtrade.io/en/stable/freqai/

---

## Core Benefits of FreqAI (vs. N8N + Groq)

### 1. **Unified In-Process Signals**
- ✅ Latency: ~50ms (vs. N8N Groq = 500–800ms)
- ✅ No external service dependencies (no N8N, no webhook complexity)
- ✅ Single source of truth: strategy code calls FreqAI predictions directly
- ✅ Zero network failure modes (model lives in FreqTrade process)

### 2. **Automatic Data Pipeline**
- ✅ Fetches OHLCV data from exchange automatically
- ✅ Manages feature engineering (calculates indicators, normalizes)
- ✅ Handles data splits for training/validation
- ✅ Retrains on schedule (hourly, daily, weekly) — no manual intervention
- ✅ Proper handling of train/test leakage

### 3. **Walk-Forward Validation Built-In**
- ✅ Tests model on unseen future data (prevents overfitting)
- ✅ Mimics live trading: train on past, validate on future in rolling windows
- ✅ Reports Sharpe, Sortino, max drawdown, win rate, profit factor
- ✅ Mandatory validation gate before going live

### 4. **Multiple ML Algorithms**
- ✅ **LightGBM** — Fast, powerful, recommended baseline (tabular data)
- ✅ **XGBoost** — Gradient boosting with regularization
- ✅ **CatBoost** — Handles categorical features natively
- ✅ **PyTorch MLP** — Neural networks for complex patterns
- ✅ **Reinforcement Learning** — Stable Baselines3 (learn from trade outcomes)
- ✅ **Custom IFreqaiModel** — Any model, any library, can call external APIs (Groq, Gemini, DeepSeek)

### 5. **Scalability & Maintainability**
- ✅ Handles 1000+ pairs (N8N breaks at ~100)
- ✅ Model versioning tracked automatically
- ✅ Hyperparameter optimization built-in
- ✅ Feature importance scoring (know which inputs matter)
- ✅ Simple debugging: just read FreqTrade logs

### 6. **Production-Ready Infrastructure**
- ✅ Model caching per candle (no redundant inference)
- ✅ Graceful fallback if model fails (use previous signal)
- ✅ Persistent model storage (trained models saved to disk)
- ✅ Live prediction on new data with proper feature alignment

---

## Task 1.1 — Build First FreqAI Strategy (LightGBM)
**Status:** ⬜ Pending  
**Effort:** 2–3 hours  
**File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py`

A FreqAI strategy that uses LightGBM trained on OHLCV + indicators to predict price direction.

### Features to engineer (inputs to the model)
- RSI 14, RSI 7
- MACD histogram, MACD signal
- EMA 9, EMA 21, EMA 50, EMA 200
- Bollinger Band width, %B
- ATR 14 (normalized)
- Volume change % vs 20-period average
- Hour of day (cyclical encoding — sin/cos)
- Day of week (cyclical encoding)
- Price position relative to 24h high/low

### Target variable
- `&-s_close` — whether price will be higher in N candles (FreqAI standard)
- Start with N=3 (3 candles = 45 minutes on 15m timeframe)

### FreqAI config additions to `config.json`
```json
"freqai": {
  "enabled": true,
  "purge_old_models": true,
  "train_period_days": 30,
  "backtest_period_days": 7,
  "live_retrain_hours": 4,
  "identifier": "finbuddy_lgbm_v1",
  "feature_parameters": {
    "include_timeframes": ["5m", "15m", "1h"],
    "include_corr_pairlist": ["BTC/USDT", "ETH/USDT"],
    "label_period_candles": 3,
    "include_shifted_candles": 2
  },
  "data_split_parameters": {
    "test_size": 0.15
  },
  "model_training_parameters": {
    "n_estimators": 200,
    "learning_rate": 0.05
  }
}
```

### Model config
```json
"freqaimodel": "LightGBMRegressor"
```

---

## Task 1.2 — Build Custom FreqAI Model with Groq LLM Layer
**Status:** ⬜ Pending (after 1.1)  
**Effort:** 3–4 hours  
**File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py`

A custom `IFreqaiModel` that combines LightGBM predictions with a Groq LLM confirmation call. Best of both worlds: ML picks the signal, LLM validates it with market context.

### Architecture
```
Market data + indicators
        ↓
  LightGBM prediction (fast, local)
        ↓
  If confidence > 0.60:
    → Call Groq Llama 3.3 70B with market context + LightGBM signal
    → Parse LLM confirmation
    → Final signal = LightGBM * 0.6 + LLM_confirmation * 0.4
  Else:
    → HOLD
```

### Key methods to implement
- `fit(data_dictionary, dk)` — train LightGBM on historical data
- `predict(unfiltered_df, dk)` — run LightGBM, then optionally call Groq

---

## Task 1.3 — FreqAI Backtest Run
**Status:** ⬜ Pending (after 1.1)  
**Effort:** 1–2 hours

Run walk-forward backtest on the LightGBM strategy before activating in dry run.

```bash
docker exec -it freqtrade freqtrade backtesting \
  --strategy FinBuddyFreqAI \
  --freqaimodel LightGBMRegressor \
  --timerange 20250101-20260401 \
  --timeframe 15m
```

### Accept if
- Win rate > 50%
- Sharpe ratio > 0.5
- Max drawdown < 20%
- Profit factor > 1.2

### Update registry
Update `strategies/registry.json` — change `backtest.status` to `validated` if it passes.

---

## Task 1.4 — Switch Dry Run to FinBuddyFreqAI Strategy
**Status:** ⬜ Pending (after 1.3)  
**Effort:** 15 minutes

Once backtest passes, switch FreqTrade from `AiGuardrailStrategy` to `FinBuddyFreqAI`.

```bash
# Edit docker-compose.yml
sed -i 's/AiGuardrailStrategy/FinBuddyFreqAI/' \
  /home/ubuntu/var/www/html/trade/freqtrade/docker-compose.yml
docker restart freqtrade
```

Keep `AiGuardrailStrategy.py` — don't delete it. Archive, don't remove.

---

## AI Models Available in FreqAI (No Extra Install Needed)

| Model | Class | Best For |
|---|---|---|
| LightGBM | `LightGBMRegressor` / `LightGBMClassifier` | Fast, tabular data, great baseline |
| XGBoost | `XGBoostRegressor` / `XGBoostClassifier` | Similar to LightGBM, good ensemble partner |
| CatBoost | `CatBoostRegressor` | Handles categorical features well |
| PyTorch MLP | `PyTorchMLPRegressor` | Neural net for complex patterns |
| Reinforcement Learning | `ReinforcementLearner` | Learns from trade outcomes directly |
| Sklearn | `SklearnRandomForestClassifier` | Interpretable, good for feature importance |

## External AI APIs to Integrate (via custom model)

| API | Use Case | Cost |
|---|---|---|
| Groq (Llama 3.3 70B) | Signal confirmation, market reasoning | Free (6000 req/day) |
| Gemini 2.5 Flash | Deep research, macro context | Free tier |
| DeepSeek R1 | Nightly strategy reasoning | Near-free |
| Anthropic Claude Sonnet | Pine Script writing, strategy promotion | Sparingly |

---

## Phase 1 Complete When
- [ ] `FinBuddyFreqAI.py` strategy exists and runs without errors
- [ ] LightGBM model trains and predicts on live data
- [ ] Walk-forward backtest passes acceptance criteria
- [ ] Strategy listed as `validated` in `strategies/registry.json`
- [ ] Dry run switched to `FinBuddyFreqAI`
