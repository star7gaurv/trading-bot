# Winning Strategies
> Strategies validated by walk-forward backtesting and promoted to live dry-run.
> Updated by the research loop and manual review.
> Failed strategies → [[graveyard]]  |  Back to hub → [[../CONTEXT]]

---

## Active
*(None yet — backtesting pipeline not yet wired)*

---

## Hall of Fame
*(Strategies retired after a good run will be archived here)*

---

## Promotion Criteria
A strategy must pass ALL of the following before being added here:
- [ ] Walk-forward backtest: Sharpe > 1.5 over 3+ months
- [ ] Max drawdown < 15%
- [ ] Tested across at least 2 different market regimes
- [ ] Reviewed and approved (Claude Sonnet used for final review)

---

### FinBuddyFreqAI v10 — entry-anchored ATR custom_stoploss (active, R5 results 2026-05-02)

**First profitable bull run across 5 futures backtest rounds.**

| | Bull (2024) | Bear (2025-26) |
|---|---|---|
| Trades | 57 | 87 |
| Win Rate | **57.9%** | **58.6%** |
| Sharpe (closed) | **+0.13** | -0.15 |
| Max Drawdown | **1.68%** | **3.66%** |
| Profit Factor | 1.11 | 0.91 |
| P&L (USDT) | **+7.24** | -8.78 |

**Key changes vs v9:**
1. `custom_stoploss()` returns `None` on missing data (was `self.stoploss` → forced reset every candle).
2. Both stops anchored to ENTRY price via `stoploss_from_open()`:
   - Initial: `stoploss_from_open(-2 × atr_pct, ...)` = loss-cap below open
   - Trailing: `stoploss_from_open(+1.5 × atr_pct, ...)` = profit-lock above open (only when profit > 1×ATR)
3. Returns positive floats (sign ignored by Freqtrade anyway, but explicit per docs).

**Mechanism that flipped the result:**
- v9's trailing returned `-(1.5 × atr_pct)` from current price — the stop chased price up forever and never locked in. Trailing cohort: 38 trades / 15.8% WR / -0.60% avg.
- v10's trailing locks the stop at +1.5×ATR above OPEN price (a fixed dollar level). Trailing cohort: 41 trades / 51.2% WR / +0.04% avg.
- Same trades, same signals — just stops in the right place.

**Status:** Active in dry-run. Next step before live: walk-forward / out-of-sample validation (R5 numbers are in-sample).
