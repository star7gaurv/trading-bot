# Strategy Graveyard
> Strategies that were tested and failed. Kept here so we never repeat the same mistake.
> Written by the research loop after a strategy is demoted.
> Winning strategies → [[winners]]  |  Back to hub → [[../CONTEXT]]

---

## Format
```
### Strategy Name
- **Reason failed:** ...
- **Regime it failed in:** ...
- **Date demoted:** ...
- **Key lesson:** ...
```

---

### FinBuddyFreqAI v3 — Stoploss -0.03 run (2026-05-01)
- **Stoploss:** -0.03
- **Trades:** 148 | Win rate: 57.4% ✅ | Sharpe: -1.58 ❌ | Drawdown: 17.87% ✅ | Profit factor: 0.52 ❌
- **Reason failed:** 44 stop_loss exits at -3.19% avg = -281 USDT destroyed all profits. Stoploss too tight for 4-hour avg trade duration.
- **Regime it failed in:** Bear market — BTC/market fell -47.55% during test period (2025-02-01 to 2026-04-01)
- **Date:** 2026-05-01
- **Key lesson:** Stoploss exits at -3% avg mean the position moves against entry before the ML signal fires exit. Entry threshold (0.008) is not selective enough.

### FinBuddyFreqAI v3 — Stoploss -0.035 run (2026-05-01)
- **Stoploss:** -0.035
- **Trades:** 141 | Win rate: 60.3% ✅ | Sharpe: -1.40 ❌ | Drawdown: 17.50% ✅ | Profit factor: 0.54 ❌
- **Reason failed:** 36 stop_loss exits at -3.69% avg = -265 USDT. Slightly looser stoploss barely changed outcome — root issue is bad entries, not stoploss level. Entry signal fires during counter-trend moves.
- **Regime it failed in:** Bear market — BTC/market fell -47.55% during test period (2025-02-01 to 2026-04-01)
- **Date:** 2026-05-01
- **Fix needed:** Raise ML entry threshold from 0.008 → 0.012 (stronger signal required), or add 1h trend filter (only enter if 1h EMA slope positive). Exit signal trades had 79.8% win rate — the ML signal is good, entries are just too permissive.

### FinBuddyFreqAI v4 — ML threshold 0.012 + 1h EMA-50 trend filter (2026-05-01)
- **Stoploss:** -0.035
- **Trades:** 24 | Win rate: 58.3% ✅ | Sharpe: -0.15 ❌ | Drawdown: 4.97% ✅ | Profit factor: 0.68 ❌
- **Reason failed:** Only 24 trades in 14-month period — filters over-tuned. 1h EMA-50 trend filter eliminates most entries in the bearish test window. Exit signal trades: 81.8% win rate — ML signal confirmed good. 8 stop_loss exits at -3.69% still dominate losses.
- **Regime it failed in:** Bear market — BTC/market fell -47.55% during test period (2025-02-01 to 2026-04-01)
- **Date:** 2026-05-01
- **Key lesson:** Threshold 0.012 + 1h EMA-50 filter too strict for bear market. Cuts valid trades along with bad ones. Improvement direction: threshold 0.010, or shorter 1h EMA-20, or separate bull/bear thresholds.
