# Phase 4b — New Entry Features (the only remaining path)

> Created 2026-06-20 after meta-labeling was correctly disproven (corrected label, AUC=0.50,
> corr(pred,outcome)=0.001). Three independent measurements now agree the EXISTING ~530 entry
> features carry no directional signal: live OOS IC≈0.03, corrected-meta AUC=0.50, dumb-EMA
> baseline also loses. The bot's only edge is in EXITS. The sole way to make a *directional*
> bot profitable is to give the ENTRY real predictive features. This is that effort.

## The governing principle (don't repeat the last 2 months)
Adding features to the 530-feature soup and re-running the brain is how prior attempts failed —
a real signal gets diluted among 756 dead features and lost. So Phase 4b is **test-in-isolation
first**: every candidate feature family must clear a cheap standalone gate BEFORE it touches the
model. No feature graduates on hope.

### The standalone gate (cheap, hours, no full retrain)
For each candidate feature `f`:
1. Build `f` over the historical windows (offline, pandas).
2. Compute its **Spearman IC vs forward return** (12-candle, the same target the model predicts),
   pooled and per-pair, on bull_2024Q1/2024Q4 + bear_2025Q1/2026Q1.
3. **GATE:** |pooled IC| must be **> 0.05** (meaningfully above the current 0.03 noise floor) on
   AT LEAST the bear windows (live is bear). IC ≤ 0.03 → drop the feature, do not integrate.
Only features that clear this enter a brain A/B. (A new `scripts/brain/feature_ic.py` should
compute this — mirror of the validation harness already used for the meta-label.)

### The integration test (for features that clear the gate)
1. Add the feature family to the model; **prune to ~top-100 features** at the same time (see 4b.4)
   so the new signal isn't diluted.
2. Brain A/B vs current model on genuine bull+bear windows. Success = OOS IC rises meaningfully
   above 0.03 AND/OR corrected-meta AUC (re-run `meta_auc.py`) rises above 0.55.

## Candidate feature families — ranked by (evidence × data-availability)

Evidence basis: the importance report already shows MACRO/FLOW features dominate (funding, BTC OI
z-score #3, BTC ATR, btc_strength) while per-pair TA is dead weight; and the model has most edge on
mid-cap alts, ~0 on BTC/ETH — so cross-asset and flow features are the priors.

| # | Feature family | Data available now? | Effort | Why |
|---|---|---|---|---|
| 4b.1 | **BTC→alt lead-lag** (lagged BTC returns/vol/accel as alt features) | ✅ yes (BTC OHLCV exists) | low | BTC leads alts by minutes; model is weak on BTC, strong on alts |
| 4b.2 | **Funding extremes** (z-cross, sign-flip, percentile, not just level) | ✅ yes (funding parquet exists) | low | funding is the #1 importance feature; the EXTREME is the signal |
| 4b.3 | **OI-delta** (rate-of-change of open interest, not level) | ~ partial (per-pair OI backfilling) | low-med | OI level (#3) works; the delta is the published 2nd-best signal |
| 4b.4 | **Feature pruning to ~top-100** | ✅ yes | low | prerequisite — 756/530 features are dead; they dilute any new signal |
| 4b.5 | **Order-flow / CVD** (cumulative volume delta, taker buy/sell ratio) | ❌ NO — klines store only OHLCV; needs an aggTrades/taker-volume fetcher | high | most-cited short-term directional signal — highest ceiling, most data work |

### Execution order
Start with the FREE, no-new-data families (4b.1, 4b.2) + pruning (4b.4) — they can be IC-gated
this week. 4b.3 once per-pair OI backfill completes. 4b.5 (order-flow) only if 4b.1–4b.3 show
signs of life (it's the expensive data-engineering bet; don't pay it on spec).

## KILL condition (so Phase 4b is not endless)
If NO candidate family lifts pooled OOS IC above ~0.05 on the bear windows after 4b.1–4b.4, the
honest conclusion is **the directional-prediction approach is exhausted on this data/timeframe**.
At that point STOP trying to predict 15m direction and pivot to **market-neutral modules where
direction does not need to be predicted** — funding-rate farming (already paper-running), grid
(ranging), or spot-futures basis arb. The exit edge stays; we stop betting on a broken compass.

## Hard rules (carried from the project)
- Build/IC-gate offline first; only graduated features get a brain A/B (default-OFF env flag,
  family-cache keyed). Apply live ONLY on a clean PASS (identifier bump + pkl flush + `up -d`).
- queue only via `experiment_log.queue_hypothesis()`. Configs via Python json, never sed.
- Live bot untouched until a feature set demonstrably beats the frozen baseline.
- See [[reference-meta-label-nogo]], [[reference-ic-and-edge-location]], [[reference-phase1-measurement-failed]].
