# Shadow Rule Extraction Report

Generated: 2026-07-16T13:06:04.751648+00:00

Interpretable rule extraction (KMeans clustering + shallow decision trees) applied to FinBuddy's own closed-trade history — a different technique class than the ML regression/classification approaches already exhausted on this project (meta-labeling AUC=0.50, cross-sectional IC negative, order-flow/OI/funding features all noise). Asks 'what did the winners already have in common' rather than 'predict the future return'.

**Any candidate rule below is a hypothesis, not a conclusion.** It must go through the normal `hypothesis_gen.py` -> `runner.py` backtest -> `promote.py` gate pipeline like every other hypothesis before it could ever affect live trading. This script has no fast path to production.

### Cohort: exit_signal only

Total trades in cohort: 280. Profitable: 257.

Auto-selected k=2 clusters (silhouette=0.332).

**Cluster 0** (34 trades, avg pnl 6.29%, avg hold 9.6h):
- Base rate (this cluster's share of the cohort): 12.1%
- Tree in-sample precision when it predicts membership: 0.0% (lift 0.00x over base rate)
- **No meaningful entry-time signal found** — precision barely beats chance. Consistent with this project's other findings (IC≈0.03-0.05, meta-labeling AUC=0.50): entry-time features don't separate winners from the rest, even with a completely different technique.
```
|--- entry_weekday <= -0.34
|   |--- entry_hour_utc <= -1.59
|   |   |--- direction_long <= 0.50
|   |   |   |--- class: 0
|   |   |--- direction_long >  0.50
|   |   |   |--- class: 0
|   |--- entry_hour_utc >  -1.59
|   |   |--- pair_short_XRP <= 0.50
|   |   |   |--- class: 0
|   |   |--- pair_short_XRP >  0.50
|   |   |   |--- class: 0
|--- entry_weekday >  -0.34
|   |--- regime_at_entry_BEAR <= 0.50
|   |   |--- direction_long <= 0.50
|   |   |   |--- class: 0
|   |   |--- direction_long >  0.50
|   |   |   |--- class: 0
|   |--- regime_at_entry_BEAR >  0.50
|   |   |--- entry_weekday <= 0.18
|   |   |   |--- class: 0
|   |   |--- entry_weekday >  0.18
|   |   |   |--- class: 0
```

**Cluster 1** (223 trades, avg pnl 1.53%, avg hold 1.8h):
- Base rate (this cluster's share of the cohort): 79.6%
- Tree in-sample precision when it predicts membership: 81.2% (lift 1.02x over base rate)
- **No meaningful entry-time signal found** — precision barely beats chance. Consistent with this project's other findings (IC≈0.03-0.05, meta-labeling AUC=0.50): entry-time features don't separate winners from the rest, even with a completely different technique.
```
|--- regime_at_entry_BEAR <= 0.50
|   |--- pair_short_AVAX <= 0.50
|   |   |--- entry_weekday <= -0.34
|   |   |   |--- class: 1
|   |   |--- entry_weekday >  -0.34
|   |   |   |--- class: 1
|   |--- pair_short_AVAX >  0.50
|   |   |--- class: 0
|--- regime_at_entry_BEAR >  0.50
|   |--- pair_short_XRP <= 0.50
|   |   |--- entry_hour_utc <= 0.56
|   |   |   |--- class: 1
|   |   |--- entry_hour_utc >  0.56
|   |   |   |--- class: 1
|   |--- pair_short_XRP >  0.50
|   |   |--- class: 0
```

### Cohort: all closed trades

Total trades in cohort: 1003. Profitable: 427.

Auto-selected k=2 clusters (silhouette=0.337).

**Cluster 0** (45 trades, avg pnl 5.73%, avg hold 12.7h):
- Base rate (this cluster's share of the cohort): 4.5%
- Tree in-sample precision when it predicts membership: 0.0% (lift 0.00x over base rate)
- **No meaningful entry-time signal found** — precision barely beats chance. Consistent with this project's other findings (IC≈0.03-0.05, meta-labeling AUC=0.50): entry-time features don't separate winners from the rest, even with a completely different technique.
```
|--- pair_short_BTC/USDT <= 0.50
|   |--- entry_hour_utc <= 0.71
|   |   |--- pair_short_ARB <= 0.50
|   |   |   |--- class: 0
|   |   |--- pair_short_ARB >  0.50
|   |   |   |--- class: 0
|   |--- entry_hour_utc >  0.71
|   |   |--- pair_short_NEAR <= 0.50
|   |   |   |--- class: 0
|   |   |--- pair_short_NEAR >  0.50
|   |   |   |--- class: 0
|--- pair_short_BTC/USDT >  0.50
|   |--- entry_hour_utc <= 0.40
|   |   |--- entry_weekday <= 0.29
|   |   |   |--- class: 0
|   |   |--- entry_weekday >  0.29
|   |   |   |--- class: 0
|   |--- entry_hour_utc >  0.40
|   |   |--- entry_weekday <= -1.26
|   |   |   |--- class: 0
|   |   |--- entry_weekday >  -1.26
|   |   |   |--- class: 0
```

**Cluster 1** (382 trades, avg pnl 1.25%, avg hold 2.8h):
- Base rate (this cluster's share of the cohort): 38.1%
- Tree in-sample precision when it predicts membership: 73.9% (lift 1.94x over base rate)
```
|--- regime_at_entry_NEUTRAL <= 0.50
|   |--- entry_weekday <= -1.26
|   |   |--- entry_hour_utc <= 0.79
|   |   |   |--- class: 0
|   |   |--- entry_hour_utc >  0.79
|   |   |   |--- class: 1
|   |--- entry_weekday >  -1.26
|   |   |--- entry_hour_utc <= 1.02
|   |   |   |--- class: 0
|   |   |--- entry_hour_utc >  1.02
|   |   |   |--- class: 0
|--- regime_at_entry_NEUTRAL >  0.50
|   |--- pair_short_FIL <= 0.50
|   |   |--- direction_short <= 0.50
|   |   |   |--- class: 0
|   |   |--- direction_short >  0.50
|   |   |   |--- class: 0
|   |--- pair_short_FIL >  0.50
|   |   |--- direction_short <= 0.50
|   |   |   |--- class: 1
|   |   |--- direction_short >  0.50
|   |   |   |--- class: 1
```
