# Funding Farm (Paper)

Cash-and-carry funding-rate capture: hold a spot-equivalent long and an equal-notional perpetual
short (or the reverse) on the same coin, collecting the periodic funding payment while staying
market-neutral on price. Paper-only.

## The mechanism

`scripts/funding_farm/scanner.py` runs hourly, looking for coins with a high, stable funding rate
worth capturing net of fees, and `paper_executor.py` books the accrual each cycle with honest fees
— basis drift (the spot/perp price gap itself moving against the position) is not modeled.

## Current state

Essentially dormant: zero open positions, -0.75 USDT lifetime realized. A notable historical
incident — TON's perpetual contract was delisted (`SETTLING` status) shortly after the module
opened a position in it at an attractive-looking 199% APR; funding stopped accruing but the
decay-close rule couldn't fire because it depended on funding history that had also frozen.
Fixed 2026-07-08: the scanner now checks contract status directly and refuses to open, or closes,
any position on a non-`TRADING` symbol.

## Reference

[`scripts/funding_farm` reference](../reference/scripts/funding_farm/scanner.md) · cron: hourly at `:05`
