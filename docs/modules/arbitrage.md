# Arbitrage (Paper)

Cross-exchange and intra-exchange basis arbitrage: watch bid/ask spreads for the same asset across
many exchanges simultaneously, and capture the gap when it's wide enough to clear round-trip fees.
Paper-only.

## The mechanism

Two processes, deliberately separated:

- **`feed_daemon.py`** — a persistent background service (not a cron job; arbitrage needs
  sub-minute freshness) that polls ~25 exchanges across three priority tiers via
  [ccxt](https://github.com/ccxt/ccxt) and writes a shared price snapshot every few seconds.
- **`scanner.py`** — a lightweight cron job (every minute) that reads that snapshot and looks for
  a realizable gap, refusing to act on it if the snapshot is stale (feed daemon down).

## Current state

Fixed 2026-09-10: the feed daemon was built in July but its systemd service file had never
actually been registered with `systemctl` — it had last been run manually, got disconnected, and
was never restarted. The scanner had been correctly detecting the resulting stale cache and
refusing to trade on it for nearly two months; that half was always working as designed. Now
installed as a proper systemd service (`finbuddy-arb-feed.service`, enabled to survive reboots)
and verified flowing real data end to end.

The only real data this module ever gathered (7 observations, from its brief manual run in July)
showed every single detected gap was smaller than the assumed round-trip fee cost — 0 of 7
realizable. Fixing the plumbing means it can now honestly accumulate a real sample; it isn't
evidence of an edge on its own.

## Reference

[`scripts/arbitrage` reference](../reference/scripts/arbitrage/scanner.md) · cron: every minute (scanner) +
persistent service (feed daemon)
