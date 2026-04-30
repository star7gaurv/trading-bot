# Phase 1 — FreqAI as the Brain

> Make FreqAI the primary signal intelligence — replacing the N8N → Groq call.
> FreqAI lives inside FreqTrade, trains on rolling market data, and produces ML-powered signals.
> Custom files in user_data/ are NEVER deleted on FreqTrade upgrades (Docker volume mount).

---

## ⚠️ BLOCKING ISSUE (2026-04-30)

**FreqTrade v2026.3 (stable) does not include LightGBMRegressor** in its FreqAI module.

**Options to resolve:**
1. **Upgrade FreqTrade container** to latest dev build (may have breaking changes)
2. **Use sklearn RandomForestRegressor** — available in all versions, slower but works
3. **Use built-in PyTorch MLP** — no external deps, flexible
4. **Delay Phase 1** until upgrading infrastructure

Current recommendation: **Use RandomForestRegressor (Option 2)** — keep Phase 1 moving without container changes.

---

## Why FreqAI Instead of N8N + Groq

- FreqAI continuously retrains models on fresh data — it learns from what happened
- Supports LightGBM, XGBoost, CatBoost, PyTorch, Reinforcement Learning natively
- Custom `IFreqaiModel` can call any external API (Groq, Gemini) inside predict()
- Walk-forward validation is built in — no separate backtesting pipeline needed
- One system, not two (FreqAI + FreqTrade vs FreqTrade + N8N + Groq)

---

## Task 1.1 — Build First FreqAI Strategy (LightGBM)
**Status:** ✅ In Progress (Blocked)  
**Effort:** 30 min (creation), blocked on FreqTrade FreqAI module compatibility  
**File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py` — ✅ Created

**What's Done:**
- ✅ Strategy class created with 16+ technical indicators (RSI, MACD, EMA, Bollinger, ATR, Volume, Time features)
- ✅ FreqAI configuration added to config.json (LightGBMRegressor model, 30-day training, 4-hour retrain)
- ✅ Indicator population complete, entry/exit hooks ready
- ✅ datasieve module installed (FreqAI dependency)

**Blocker:**
- ❌ FreqTrade version (2026.3 stable) does not have LightGBMRegressor available
- Error: "Impossible to load FreqaiModel 'LightGBMRegressor'. This class does not exist or contains Python code errors."
- This is a container version issue, not a code issue

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
