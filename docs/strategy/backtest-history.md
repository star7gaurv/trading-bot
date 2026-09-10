# Backtest & Architecture History

The live strategy went through a real, measured evolution before reaching its current shape —
worth understanding both as a record of what was tried and as evidence the current architecture
wasn't arrived at casually.

## Spot was retired for a structural reason, not a strategy bug

The earliest rounds (192 backtest combinations) ran on Binance spot — long-only by construction.
Best result: Sharpe -0.174, in a market that fell 47.55% over the test window. The finding that
mattered: the model's own signal quality was healthy (79-81% win rate on signal-driven exits) — the
strategy wasn't broken, spot itself was. **No long-only strategy clears Sharpe 0.5 in a -47.55%
market**, no matter how good the entry signal is. That's an architectural ceiling, not a tuning
problem, and it's the reason this project moved to futures — long *and* short — rather than trying
to patch spot with regime filters.

## Five rounds to the first profitable configuration (futures, 5-pair, bull + bear windows)

Acceptance targets throughout: Sharpe > 0.5, win rate > 50%, drawdown < 20%, profit factor > 1.2.

| Round | Change | Bull Sharpe | Bear Sharpe | What happened |
|---|---|---|---|---|
| 1 | Futures-ready baseline | -0.145 | -0.258 | 13 of 14 stop-losses hit at -3.59%, destroying P&L |
| 2 | Tighter stop (-1.5%) | -0.896 | -0.554 | 41 of 42 trades just chopped — win rate collapsed |
| 3 | ATR-based custom stoploss | -0.78 | -0.22 | Hard stop-hits went to zero, but the trailing stop started chopping instead |
| 4 | Disabled trailing, added a macro short gate | -0.13 | -0.37 | Bull-market shorts dropped from 81 to 26, but the trailing mechanism still chopped |
| 5 | Entry-anchored trailing (`stoploss_from_open`) | **+0.13** | -0.15 | **First profitable bull window** — the trailing cohort flipped from chop to genuine lock-in |

Round 5's actual numbers: 57.9% win rate bull / 58.6% bear, max drawdown 1.68% / 3.66%, profit
factor 1.11 / 0.91. Win rate and drawdown cleared target on both legs; Sharpe and profit factor
were still short, but the gap had closed dramatically from round 1.

## The architectural pivot that followed

Classification (predict long/short/hold as discrete classes) turned out to have its own ceiling:
with an asymmetric take-profit/stop-loss ratio, the label distribution itself becomes imbalanced
(a 2:1 TP:SL ratio produces roughly 67% "stop-loss-first" labels), biasing the model toward
predicting the majority class regardless of what the market was actually doing. Even class-weight
balancing only reached 35% win rate. **v23's regression architecture** — predicting a continuous
z-scored return instead of a class — has no majority class to be biased toward. This is documented
in more depth in [Strategy & Brain](../strategy.md#the-core-idea-regression-not-classification).

## The pattern this history established

Every one of these rounds was a *measured* iteration — a specific number moved, in a specific
direction, in response to a specific structural cause identified beforehand. That discipline
(diagnose the actual mechanism before changing a parameter) is the same one behind the 2026-09-07
and 2026-09-10 sessions' fixes — see the corresponding session entries in `CLAUDE.md` for the most
recent examples of the same method applied to the live system's current gap.
