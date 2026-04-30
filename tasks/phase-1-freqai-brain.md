# Phase 1 — FreqAI as the Brain

> Make FreqAI the primary signal intelligence — replacing the N8N → Groq call.
> FreqAI lives inside FreqTrade, trains on rolling market data, and produces ML-powered signals.
> Custom files in user_data/ are NEVER deleted on FreqTrade upgrades (Docker volume mount).

---

## ⚠️ IMPORTANT: Communication Protocol

> **For Claude Code:** Before starting any task, read `CLAUDE_HANDOFF.md` in the repo root.
> It contains explicit instructions for work done by Perplexity AI that needs your review/deployment.
>
> **Status legend used in this file:**
> - ✅ **COMPLETE** — Verified running on live server by Claude Code
> - ⚠️ **NEEDS REVIEW** — Code written by Perplexity AI, committed to GitHub, NOT yet deployed/tested on server. Claude Code must pull, review, deploy, and verify before marking complete.
> - 🟡 **IN PROGRESS** — Being actively worked on
> - ⬜ **PENDING** — Not started

---

## Status as of 2026-05-01

- Task 1.1: ✅ COMPLETE (Claude Code verified live on server, 2026-04-30)
- Task 1.2: ⚠️ NEEDS REVIEW (Perplexity AI wrote code, committed to GitHub — NOT deployed)
- Task 1.3: ⬜ PENDING (blocked on 1.2 deploy)
- Task 1.4: ⬜ PENDING (blocked on 1.3)

---

## Task 1.1 — Build First FreqAI Strategy with LightGBM
**Status:** ✅ COMPLETE (verified live by Claude Code, 2026-04-30)  
**File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py`

**All Done:**
- ✅ 14+ TA indicators (RSI 14/7, MACD, EMA 9/21/50/200, Bollinger, ATR, Volume, Price position)
- ✅ `set_freqai_targets()` — LightGBM predicts `&-s_close` (% price change in next 3 candles / 45min)
- ✅ `self.freqai.start()` — trains model + injects predictions into dataframe every candle
- ✅ Entry: PRIMARY `&-s_close > 0.008` AND `do_predict == 1`, SECONDARY TA filter
- ✅ Exit: PRIMARY `&-s_close < -0.003` OR TA reversal signals
- ✅ Safety gate: rejects entries below 200 EMA and RSI >78
- ✅ Docker image `develop_freqai` — LightGBM, XGBoost, scikit-learn pre-installed
- ✅ Bot RUNNING, models training per pair

---

## Task 1.2 — Custom FreqAI Model with Groq LLM Layer
**Status:** ⚠️ NEEDS REVIEW — Code written by Perplexity AI (2026-05-01 01:00 IST)  
**File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py`  
**Commit:** [55848d7](https://github.com/star7gaurv/trading-bot/commit/55848d79305557914a5ef72f68dfad56d283f422)  
**Action required:** See `CLAUDE_HANDOFF.md` for full step-by-step deployment instructions.

### What Perplexity Built

A custom `IFreqaiModel` that inherits from `LightGBMRegressor` and overrides `predict()` to add a Groq LLM confirmation layer.

**Architecture:**
```
Market data + indicators
        ↓
  LightGBM prediction (inherited — full training pipeline unchanged)
        ↓
  If abs(&-s_close) > 0.006 (0.6% predicted move) AND cooldown elapsed:
    → Call Groq Llama 3.3 70B with market context (pair, RSI, MACD, EMA, BB, volume)
    → Parse response: CONFIRM / REJECT / HOLD
    → Blended signal = LightGBM * 0.60 + LightGBM * multiplier * 0.40
       CONFIRM → multiplier = 1.30 (amplify)
       REJECT  → multiplier = 0.15 (near-zero dampening)
       HOLD    → multiplier = 0.50 (moderate dampening)
  Else:
    → LightGBM signal unchanged (passes through to strategy)
```

**Safety features:**
- 4-second Groq timeout (never blocks a trade decision)
- 60-min per-pair cooldown (stays inside Groq free tier: 6000 req/day)
- Graceful fallback on any error → LightGBM signal used unchanged
- 429 rate limit → auto-extends cooldown to 2 hours
- GROQ_API_KEY from environment variable (set in docker-compose.yml)

### What Claude Code Must Do

> **Full instructions: read `CLAUDE_HANDOFF.md`**

Quick checklist:
- [ ] `git pull origin gaurav`
- [ ] Verify `user_data/freqaimodels/FinBuddyLLMModel.py` exists
- [ ] Check base class import compatibility with current FreqTrade version
- [ ] Add `GROQ_API_KEY` to docker-compose.yml environment
- [ ] Add `freqaimodels/` to docker-compose.yml volumes (if not present)
- [ ] Test import: `docker exec freqtrade python -c "from FinBuddyLLMModel import FinBuddyLLMModel"`
- [ ] If import passes: update config.json `freqaimodel` to `"FinBuddyLLMModel"`
- [ ] `docker restart freqtrade`
- [ ] Check logs for FinBuddyLLMModel startup + first Groq call
- [ ] If all good: mark Task 1.2 as ✅ COMPLETE in this file
- [ ] If broken: fix, or rollback to `LightGBMRegressor` and leave as NEEDS REVIEW with notes

---

## Task 1.3 — FreqAI Backtest Run
**Status:** ⬜ PENDING (blocked on Task 1.2 deployment)  
**Effort:** 1–2 hours

Run walk-forward backtest after FinBuddyLLMModel is verified running on server.

```bash
docker exec -it freqtrade freqtrade backtesting \
  --strategy FinBuddyFreqAI \
  --freqaimodel FinBuddyLLMModel \
  --timerange 20250101-20260401 \
  --timeframe 15m
```

### Accept if
- Win rate > 50%
- Sharpe ratio > 0.5
- Max drawdown < 20%
- Profit factor > 1.2

### Update registry after passing
Update `strategies/registry.json` — change `backtest.status` to `validated`.

---

## Task 1.4 — Switch Dry Run to FinBuddyFreqAI Strategy
**Status:** ⬜ PENDING (blocked on Task 1.3)  
**Effort:** 15 minutes

Once backtest passes:

```bash
sed -i 's/AiGuardrailStrategy/FinBuddyFreqAI/' \
  /home/ubuntu/var/www/html/trade/freqtrade/docker-compose.yml
docker restart freqtrade
```

Keep `AiGuardrailStrategy.py` — archive, don't delete.

---

## Phase 1 Complete When
- [x] `FinBuddyFreqAI.py` strategy exists and runs without errors (Task 1.1 ✅)
- [x] `set_freqai_targets()` implemented — ML predicts `&-s_close` (Task 1.1 ✅)
- [x] Entry/exit uses ML predictions (Task 1.1 ✅)
- [x] LightGBM model training on live data (Task 1.1 ✅)
- [ ] `FinBuddyLLMModel.py` deployed and verified on server (Task 1.2 ⚠️)
- [ ] Walk-forward backtest passes: win rate >50%, Sharpe >0.5, drawdown <20%, PF >1.2 (Task 1.3)
- [ ] Strategy listed as `validated` in `strategies/registry.json` (Task 1.3)
- [ ] Dry run switched to `FinBuddyFreqAI` with `FinBuddyLLMModel` (Task 1.4)

---

## AI Models Available in FreqAI

| Model | Class | Best For |
|---|---|---|
| LightGBM | `LightGBMRegressor` / `LightGBMClassifier` | Fast, tabular data, great baseline |
| XGBoost | `XGBoostRegressor` / `XGBoostClassifier` | Similar to LightGBM, good ensemble partner |
| CatBoost | `CatBoostRegressor` | Handles categorical features well |
| PyTorch MLP | `PyTorchMLPRegressor` | Neural net for complex patterns |
| Reinforcement Learning | `ReinforcementLearner` | Learns from trade outcomes directly |

## External AI APIs

| API | Use Case | Cost |
|---|---|---|
| Groq (Llama 3.3 70B) | Signal confirmation, market reasoning | Free (6000 req/day) |
| Gemini 2.5 Flash | Deep research, macro context | Free tier |
| DeepSeek R1 | Nightly strategy reasoning | Near-free |
