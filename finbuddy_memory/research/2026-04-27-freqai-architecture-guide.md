# FreqAI Architecture & Benefits Guide
**For Phase 1: FreqAI Brain Development**
**Prepared:** 2026-04-27
**Reference:** https://www.freqtrade.io/en/stable/freqai/ (official docs)

---

## What Is FreqAI?

FreqAI is a **machine learning framework built into FreqTrade** that enables traders to:
- Train ML models on historical market data
- Generate predictive signals using trained models
- Run inference on live market data in real-time
- Support multiple ML libraries and custom models
- Integrate external APIs for enriched features
- Backtest strategies with walk-forward validation

**Key Insight:** FreqAI is NOT a separate tool — it runs inside FreqTrade as an integrated component. Your strategy directly calls the FreqAI model endpoint.

---

## Core Benefits for FinBuddy

### 1. **Unified Signal Generation Inside FreqTrade**
- ✅ No external API calls (N8N → Groq → webhook → FreqTrade)
- ✅ Latency: ~50–100ms per signal (vs. N8N + Groq = 500–800ms)
- ✅ Single source of truth: FreqTrade config, FreqAI model, strategy logic all co-located
- ✅ Eliminates orchestration complexity (no N8N workflows needed)

### 2. **Multiple ML Algorithms (Choose Best Fit)**

**Built-in Tabular Models:**
- **LightGBM** — Fast, gradient boosting, excellent for structured data (recommended start)
- **XGBoost** — Powerful gradient boosting with regularization
- **CatBoost** — Handles categorical features well
- **Random Forest** — Ensemble, interpretable baseline

**Neural Network Support:**
- **PyTorch MLP** — Custom multi-layer perceptron
- **Reinforcement Learning (Stable Baselines3)** — Agent-based learning

**Custom Models:**
- **IFreqaiModel interface** — Write any model, any library (TensorFlow, Keras, scikit-learn, custom)

### 3. **Automatic Data Pipeline**
- ✅ Fetches OHLCV data from exchange automatically
- ✅ Manages feature engineering (populates feature columns)
- ✅ Handles data normalization/scaling
- ✅ Splits train/test data with proper windowing
- ✅ Retrains on schedule (hourly, daily, weekly, etc.)

### 4. **Walk-Forward Backtesting Built-In**
- ✅ Validates model on unseen future data (prevents overfitting)
- ✅ Mimics live trading: train on past, test on future in rolling windows
- ✅ Reports: Sharpe, Sortino, max drawdown, win rate, profit factor
- ✅ Mandatory before going live (FinBuddy Phase 1 requirement)

### 5. **Feature Engineering & External Data**
- ✅ Create custom features: RSI, MACD, ATR, etc.
- ✅ Add external data: Fear & Greed Index, CoinGecko sentiment, on-chain metrics
- ✅ Normalize all features on the same scale
- ✅ Feature importance scoring (know which inputs matter)

### 6. **Hyperparameter Optimization**
- ✅ Bayesian optimization, grid search, random search available
- ✅ Automatically find best LightGBM parameters (max_depth, learning_rate, etc.)
- ✅ Integrated with FreqTrade: `freqtrade backtest --hyperopt-loss`

### 7. **Multi-Timeframe Support**
- ✅ Train model on 15m data, use 1h features, generate signals on 5m
- ✅ Flexible feature engineering across timeframes
- ✅ FinBuddy: Train on 15m, test on 1h

### 8. **Production-Ready Inference**
- ✅ Model predictions cached per candle (no redundant inference)
- ✅ Graceful fallback if model fails (use previous signal)
- ✅ Model versioning (track which model generated which signal)
- ✅ Built-in logging of model outputs

---

## Architecture: FreqAI Signal Flow

```
┌─────────────────────────────────────┐
│  Binance OHLCV (15m candles)        │
│  + External data (Fear & Greed, etc)│
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  FreqAI Feature Pipeline             │
│  • Normalize raw OHLCV               │
│  • Calculate technical indicators    │
│  • Fetch external data               │
│  • Combine all features              │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  FreqAI Training Loop (scheduled)    │
│  • Rolling 30-day train window       │
│  • LightGBM fits model               │
│  • Walk-forward validation on 7-day  │
│  • Model saved to disk               │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  FreqAI Inference (per new candle)   │
│  • Load trained model                │
│  • Prepare features for new candle   │
│  • LightGBM predicts: buy/sell score │
│  • Return prediction (0.0–1.0)       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Custom IFreqaiModel Layer           │
│  • Receive LightGBM prediction       │
│  • Optional Groq confirmation call   │
│  • Apply confidence threshold (≥0.65)│
│  • Return entry/exit signal          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  FreqTrade Strategy (AiGuardRail)    │
│  • Receive signal from FreqAI        │
│  • Apply risk filters (regime, size) │
│  • Execute forceentry/forceexit      │
│  • Send Telegram notification        │
└─────────────────────────────────────┘
```

---

## Key FreqAI Concepts

### **Data Pair & Protection**
- `data_pair`: Which pair to train model on (e.g., BTC/USDT)
- `protection_window`: Hours of data to use for training
- Example: 30 days rolling window, retrain every 1 hour

### **Feature Columns**
```python
# In populate_indicators() method
dataframe["rsi"] = ta.RSI(dataframe, 14)
dataframe["macd"] = ta.MACD(dataframe)
dataframe["atr"] = ta.ATR(dataframe, 14)
dataframe["fear_greed"] = external_api_call()  # Custom!

# FreqAI will use these as model inputs
```

### **Target Column**
```python
# Label for training: what should the model predict?
# Example: "close_price_tomorrow_higher_than_today"
dataframe["target"] = (dataframe["close"].shift(-1) > dataframe["close"]).astype(int)
```

### **Model Training Schedule**
- Default: Retrain every new candle (production mode)
- Backtest mode: Train once per 5 days of data
- Configurable: hourly, daily, weekly retrains

### **Prediction Normalization**
FreqAI returns predictions as probabilities (0.0–1.0):
- 0.0 = 100% confidence in "sell"
- 0.5 = Neutral
- 1.0 = 100% confidence in "buy"

---

## Why FreqAI Beats the Current N8N Setup

| Aspect | N8N v4 (Current) | FreqAI (Phase 1) |
|---|---|---|
| **Signal latency** | 500–800ms (N8N + Groq) | ~50ms (in-process) |
| **Data pipeline** | Manual (N8N nodes) | Automatic (built-in) |
| **Model training** | Manual (N8N prompts) | Scheduled (freqtrade) |
| **Walk-forward validation** | None (unvalidated) | Built-in |
| **Scalability** | Breaks at ~100 pairs | Handles 1000+ pairs |
| **Cost** | Free (Groq) + N8N infra | Free (LightGBM only) |
| **Debugging** | N8N UI (complex) | FreqTrade logs (simple) |
| **Code reuse** | Groq prompts | ML models across users |

---

## Implementation Strategy (Phase 1)

### **Step 1: LightGBM Baseline (Days 1–2)**
- Create `FinBuddyFreqAI.py` with LightGBM model
- Features: RSI(14), MACD(12,26,9), ATR(14) + external data
- Target: Close price direction (up/down)
- Backtest on 3 months of BTC/USDT data
- Walk-forward validation mandatory

### **Step 2: Custom Confirmation Layer (Days 2–3)**
- Extend `IFreqaiModel` to add Groq confirmation
- LightGBM prediction + Groq prompt = final signal
- Confidence threshold: 0.65 (both must agree)
- Backtest full pipeline

### **Step 3: Live Validation (Day 4)**
- Deploy to paper trading
- Monitor signal quality vs. N8N v4
- Compare Sharpe, drawdown, win rate
- Commit results to memory vault

### **Step 4: Retire N8N (After validation)**
- Once FreqAI validated, disable N8N signal workflow
- Keep N8N running for 1 week (safety net)
- Shut down entirely after confidence built

---

## FreqAI vs. Custom Model: When to Use Each

### **Use FreqAI When:**
- ✅ Training on historical candle data (90% of use cases)
- ✅ Need walk-forward validation
- ✅ Want built-in data management
- ✅ Need to backtest reliably
- ✅ Building production system (solo operator)

### **Use Custom Model When:**
- ⚠️ Training on non-OHLCV data only (requires manual integration)
- ⚠️ Real-time inference without historical training
- ⚠️ Complex multi-step pipelines (use FreqAI + custom layer instead)

**FinBuddy:** Use FreqAI + custom IFreqaiModel for Groq layer. Best of both worlds.

---

## Files to Create/Modify in Phase 1

| File | Purpose |
|---|---|
| `freqtrade/user_data/freqaimodels/FinBuddyFreqAI.py` | LightGBM model + custom logic |
| `freqtrade/user_data/strategies/AiGuardrailStrategy.py` | Calls FreqAI predictions |
| `freqtrade/user_data/config.json` | FreqAI config section |
| `finbuddy_memory/models/lightgbm_baseline.md` | Training logs + metrics |
| `docs/freqai-implementation-guide.md` | Architecture docs |

---

## Critical Success Factors

1. **Feature Engineering** — Garbage in = garbage out. Good features = good predictions.
2. **Walk-Forward Testing** — Non-negotiable. Prevent overfitting.
3. **Simple Models First** — LightGBM baseline before adding Groq.
4. **Monitor Degradation** — Track model performance over time.
5. **Automate Retraining** — Set forget_schedule so old data is dropped.

---

## References

- Official: https://www.freqtrade.io/en/stable/freqai/
- LightGBM docs: https://lightgbm.readthedocs.io
- Walk-forward validation: https://en.wikipedia.org/wiki/Walk_forward_optimization
- Feature engineering: https://www.freqtrade.io/en/stable/freqai/features/

---

*This guide will be the foundation for Phase 1 implementation. Read before starting FinBuddyFreqAI.py.*

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[research/README]]*
