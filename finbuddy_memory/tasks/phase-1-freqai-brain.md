# Phase 1 — FreqAI as the Brain

> FreqAI is the primary signal intelligence. Trains on rolling market data, produces ML-powered long/short signals on Binance Futures USDT-M. Live v22 strategy serves real dry-run evidence; v23 variants explored autonomously by the brain.

**Reference:** [FreqAI Architecture Guide](../research/2026-04-27-freqai-architecture-guide.md)
**Official Docs:** https://www.freqtrade.io/en/stable/freqai/

---

## Status as of 2026-05-18

| Sub-task | Status |
|---|---|
| 1.1 Build FreqAI Strategy | ✅ COMPLETE — v22 live (`FinBuddyFreqAI.py`) |
| 1.2 LLM Confirmation Layer | ✅ COMPLETE — `FinBuddyLLMModel` v5 (auto-confirm ≥ 0.90) |
| 1.3 Walk-Forward OOS | ❌ FAILED — see results below; **WF deprecated as gate** in favor of brain-validated dry-run path |
| 1.4 Dry-run live | ✅ COMPLETE — +$107 USDT, 273 trades, since 2026-04-30 |

**Walk-forward verdict (last run 2026-05-16):** 21 folds × 25 pairs × 2024-01-01 → 2026-04-01 produced WR 21.2% / Sharpe -9.45 / PF 0.54 / -2,302 USDT. **All four gate criteria failed.** Re-running v22 on the same code would produce identical results — v22 strategy file has not changed since.

**Phase 1 forward path**: Brain (Phase 13) autonomously searches v23 + v22 variants. When a variant beats live v22 on bull + bear windows, scan fires Telegram alert with Apply button → swap is the new gate for v23 deployment. See `phase-10-live-migration.md` for live-capital criteria.

---

## Task 1.1 — FreqAI Strategy (v22 LIVE)

**File:** `freqtrade/user_data/strategies/FinBuddyFreqAI.py` — unchanged since 2026-05-15

Live config:
- **1h base TF**, **25 pairs**, Binance USDT-M perpetual, isolated margin, **2x leverage**, max 8 trades
- Asymmetric triple-barrier labels: `k_tp=2.0`, `k_sl=1.0`, `label_period_candles=6`
- `custom_stoploss`: 1.0×ATR initial / trail locks at 2.0×ATR once profit > 3.0×ATR
- Regime kill-switches: CRASH/BEAR → no longs; BULL/EUPHORIA → no shorts
- MTF Sniper gate (v22): pair 4h trend alignment required
- Relative Strength gate: dynamic ML threshold (+0.05) when going against RS-vs-BTC
- Cluster cap (`MEGA_CAP` / `L2`): max 2 trades per cluster
- Funding-rate long guard: blocks longs if BTC perp funding > 0.05%/8h
- Identifier: `finbuddy_v22_balanced_1779015982` (LightGBMClassifier, `class_weight=balanced`)
- Enter tags: `freqai_lgbm_v22_long` / `freqai_lgbm_v22_short`

---

## Task 1.2 — FinBuddyLLMModel (LLM Confirmation Layer)

**File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` v5

Wraps LightGBMClassifier with an LLM confirmation gate:
- `proba ≥ 0.90` → auto-confirm (no LLM call) — bypass added in v5 after v3 was rejecting 91% of signals
- `proba ≥ 0.55` and cooldown elapsed → LLM CONFIRM/REJECT call
- All LLM providers fail → raw LightGBM passthrough (safe degradation)
- Cooldown: 30 min per pair

**LLM provider chain (task="signal"):** nvidia-mistral-medium → nvidia-llama-70b → nvidia-kimi-k2 → openrouter-gpt-oss-20b → openrouter-gpt-oss-120b → openrouter-nemotron-120b

Keys: `NVIDIA_API_KEY` + `OPENROUTER_API_KEY` in `freqtrade/.env`.

---

## Task 1.3 — Walk-Forward OOS (FAILED, deprecated as Phase 10 gate)

Last full run: `FinBuddyFreqAI_2024-01-01_2026-04-01_20260516T184159`

| Metric | Result | Target | Status |
|---|---|---|---|
| Win Rate | 21.2% | > 50% | ❌ |
| Sharpe | -9.45 | > 0.5 | ❌ |
| Profit Factor | 0.54 | > 1.2 | ❌ |
| Worst DD | 2.2% | < 20% | ✅ (only one passing) |
| Total P&L | -2,302 USDT | > 0 | ❌ |

WF will NOT be re-run until the strategy code materially changes. **Replaced as gate** by the brain's per-window experiments (see Phase 13) which test on `bull_2024Q1` / `bull_2024Q2` / `bear_2025Q1` per hypothesis.

---

## Task 1.4 — Live Dry-Run (ACTIVE)

Bot running v22 + LLMModel v5 since 2026-04-30.

| Metric (as of 2026-05-18) | Value |
|---|---|
| Closed trades | 273 |
| Win rate | 39.6% |
| Profit factor | 1.51 ✅ |
| Total P&L | +$107.49 USDT (+10.86%) |
| Max drawdown | 3.19% ✅ |
| Best exit reason | `exit_signal` — 60 trades / +174 USDT / 75% WR ✅ |
| Worst exit reason | `stop_loss` — 49 trades / -70 USDT ❌ |

Live profit interpretation: BEAR regime favors shorts and v22 takes shorts well. WF failure across full 2-year window shows v22 doesn't have a regime-agnostic edge. Real signal vs. regime luck won't be conclusive until the bot has lived through a regime flip (NEUTRAL → BULL transition).

---

## Phase 1 "Complete" Definition (revised 2026-05-18)

The original gate was walk-forward PASS → Phase 10. That gate is dead (v22 fails it). New gate:

- [x] FreqAI live in dry-run with positive P&L (✅ +$107)
- [x] LLM layer working (✅ v5 with auto-confirm)
- [ ] 60-day dry-run track record with PF > 1.2 across at least one regime flip
- [ ] OR: brain promotes a v23 variant that passes on bull + bear simultaneously

Either path unlocks Phase 10.

---

## AI Models in FreqAI

| Class | Role |
|---|---|
| `LightGBMClassifier` | v22 live model — primary, balanced class weights |
| `LightGBMRegressor` | v23 variant — predicts `&-future_return` directly (eliminates class bias) |
| `XGBoostClassifier` | Available, not currently used |
| `PyTorchMLPRegressor` | Available for future experimentation |

## LLM Signal Confirmation (via `scripts/llm_client.py`)

| Provider | Models | Key |
|---|---|---|
| NVIDIA NIM | kimi-k2, mistral-medium, llama-70b, qwen3-coder | `NVIDIA_API_KEY` |
| OpenRouter | gpt-oss-20b, gpt-oss-120b, nemotron-120b | `OPENROUTER_API_KEY` |
