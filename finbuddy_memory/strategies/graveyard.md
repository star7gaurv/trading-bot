# Strategy Graveyard

> Retired strategies + failed campaigns. Kept as historical reference — do NOT use these results to judge current system performance.

## Phase 0 — Spot Era (Historical Only)

All backtests and conclusions from 2025-02 to 2026-04 were run on BTC **spot** (mostly long-biased). Deprecated when FinBuddy pivoted to Binance USDT-M Perpetual (long + short, futures) on 2026-05-02.

- Market: BTC spot
- Mode: Long-biased, no leverage, no proper shorting
- Verdict: Kept only as historical research

## Futures Era — Retired Strategy Versions

| Version | File / Identifier | Retired | Why |
|---|---|---|---|
| AiGuardrailStrategy | `freqtrade/user_data/strategies/AiGuardrailStrategy.py` | 2026-04-30 | Superseded by FreqAI-driven `FinBuddyFreqAI`. File still on disk for reference, **do not restart**. |
| v6–v9 | identifier prefixes `finbuddy_v[6-9]_*` | 2026-05-05 | Round 1-4 futures backtests — symmetric barriers, hard SL hits destroyed P&L. Bull Sharpe -0.78 to -0.145. |
| v10 | `finbuddy_v10_*` | 2026-05-06 | First profitable bull (+$7.24, Sharpe +0.13) — but PF still 1.11, broken by walk-forward later. Stoploss-from-open fix carried forward. |
| v11–v15 | various v11/v12/v13/v15 identifiers | 2026-05-08 | Iterations on triple-barrier labeling. v12 introduced HOLD class (later removed in v16 for KeyError). v15 R8 grid hit 57.7% WR baseline. |
| v16 / v16.1 / v16.2 | `finbuddy_v16_clean_1778316280` | 2026-05-09 | First clean WF-tested version. Walk-forward T130947 first revealed WR=42.5% = label base rate problem. |
| v17 | `finbuddy_v17_sym_1778353539` | 2026-05-12 | Symmetric barriers (k_tp=k_sl=2.0) fix. Live for ~3 days. Replaced by v18 asymmetric campaign. |
| v18 | classifier campaign | 2026-05-12 | 24-run grid 0/24 PASS — symmetric 1:1 R:R + fee drag (~$196/yr) exactly cancels gross edge (best PF 0.996). Structural failure. |
| v19 | `finbuddy_v19_asym_1778575138` | 2026-05-17 | Asymmetric barriers K_TP=2.0/K_SL=1.0. Theoretical PF=3.26 at 62% WR. Live for ~5 days. Replaced by v22 retrain. |
| v20 / v21 | (used same v19 identifier, code edits only) | 2026-05-16 | 2x leverage + macro safety gates (v20). RS gating + dynamic ML threshold (v21). Won live trades but campaign failed walk-forward. |
| v23 standalone | `FinBuddyFreqAI_v23.py` direct manual edits | 2026-05-17 | Pivoted: v23 is no longer manually tuned. Hypothesis engine (Phase 13 brain) now owns v23 variant exploration. Strategy file remains but no longer hand-edited. |

## Walk-Forward Graveyard (FAILED runs)

| Run ID | Strategy | Folds | Result | Verdict |
|---|---|---|---|---|
| `20260509T091607` | v16 | 10/21 | killed mid-run | N/A |
| `20260509T130947` | v17 | 17 | WR 42.5%, PF 0.73 | FAIL — label base rate problem |
| `20260509T190609` | v17 | 17 | WR 47.0%, Sharpe -5.12, PF 0.73 | FAIL — better but no edge |
| `20260516T114420` | v22 | 21 | WR 21.4%, PF 0.61 (435 trades) | INVALID — `--timeframe 1h` conflicted with `include_timeframes` containing 15m |
| `20260516T182838` | v22 | 1 | crashed | walk_forward.py kwargs bug (since fixed) |
| `20260516T184159` | **v22 (current live code)** | **21** | **WR 21.2%, Sharpe -9.45, PF 0.54, -$2,302** | **FAIL** — current live v22 fails all 4 gate criteria catastrophically |

## Active Strategy (NOT in graveyard)

| Strategy | Identifier | Status |
|---|---|---|
| `FinBuddyFreqAI_v23` | `finbuddy_v23_live_*` (timestamped, bumped per promotion) | 🟢 LIVE since 2026-05-19. Per-pair-per-regime gate active. Brain owns variant exploration. |

## Retired 2026-05-19 — v22 + LLM gate

| Strategy | File | Why Retired |
|---|---|---|
| `FinBuddyFreqAI` (v22) | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | Dry-run +$94.94 (+9.59% / 45d / 291 trades) was statistically a regime coincidence — last 20 trades = 3W/17L (15% WR) after BEAR→NEUTRAL flip. File stays on disk for history (same pattern as AiGuardrailStrategy). Brain flag `V22_ENABLED=False`. |
| `FinBuddyLLMModel` (v5) | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | Wrapped v22's LightGBMClassifier with LLM confirmation. v23 uses LightGBMRegressor directly — no LLM gate needed. File on disk for history. |

---

*Last updated: 2026-05-19*

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
