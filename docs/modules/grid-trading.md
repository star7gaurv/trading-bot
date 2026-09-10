# Grid Trading (Paper)

The only module in this system with a genuinely strong, verified track record. Paper-only — no
real capital — but honestly accounted, and worth understanding closely because nothing else here
has evidence this good.

## The mechanism

`scripts/grid_trading/scanner.py` looks for coins that are **ranging, not trending, and volatile
enough to be worth it**: efficiency ratio below 0.30 (net directional movement is small relative
to total price movement — i.e. genuinely choppy) and hourly volatility above 0.50%. When it finds
one, `paper_executor.py` deploys a virtual 10-level grid across a band around the current price,
sized ±half the coin's recent trading range, capped at ±15%. Every hour, it counts how many grid
levels the price has crossed since the last check and books the cell-width profit on each crossing
— independent of which direction the price ultimately goes, as long as it stays in range.

A grid closes when price breaks outside its band, when the coin's efficiency ratio rises above
0.50 (it's gone trending — the whole premise stopped holding), or after 14 days regardless.

## The track record

26 closed positions as of the last review: **21 wins, 5 losses, +71.75 USDT net** (plus whatever's
accrued on currently-open positions — check `finbuddy_memory/grid_trading/state.json` for the live
number). Spread across nine different coins, with no single trade dominating the total. Losses are
structurally small — a grid that never gets crossed before closing loses only its entry fee
(around -0.30 USDT); wins scale with how many times the price actually oscillated.

## What's honestly *not* modeled

The paper accounting applies real taker fees on every simulated fill, but explicitly does not
model slippage or the inventory-drift a real grid bot would experience holding both legs of every
level. Real execution would likely underperform this paper number by some margin — worth keeping
in mind before reading the track record as a direct preview of live P&L.

## Reference

[`scripts/grid_trading` reference](../reference/scripts/grid_trading/scanner.md) · cron: hourly at `:40`
