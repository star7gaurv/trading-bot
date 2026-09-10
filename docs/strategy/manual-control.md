# Manual Trade Control

The brain and the strategy make every trading decision autonomously — but a human watching a bad
trade unfold has a real, tested way to intervene without SSH access. Shipped 2026-07-14 after a
direct request: "in case if AI not predicting correctly and user is watching trade and it is going
wrong then user can stop trade."

## What exists

**Force-exit, per trade.** A Close button on the dashboard (Trades tab and the Overview open-trades
panel) and a Telegram `/trades` command that lists every open trade with its own inline Close
button. Both call FreqTrade's real `POST /forceexit` — a genuine market exit order, not a
database-only removal.

**Pause / resume, globally.** A dashboard toggle and Telegram `/pause` / `/resume` commands stop
new entries system-wide while leaving every open position to manage and exit normally. This flips
the same `state: running ↔ paused` FreqTrade itself exposes.

**Proactive loss alert.** A 15-minute check (`trade_postmortem.py`) watches every open position's
live P&L; a trade crossing `MANUAL_ALERT_LOSS_PCT` (default -3%) gets a Telegram warning with a
one-tap Close button attached directly to the alert, rate-limited to once per trade per hour so a
trade sitting underwater doesn't spam repeat warnings.

**One audit trail.** Both the dashboard and Telegram append to the same
`finbuddy_memory/trades/manual_overrides.jsonl` with an identical schema — every override, from
either channel, is one queryable history:

```json
{"ts":"2026-07-14T11:20:38Z","action":"force_exit","channel":"dashboard","trade_id":1019,
 "pair":"BTC/USDT:USDT","result":"closed",
 "snapshot":{"direction":"short","profit_pct":-0.33,"stake_amount":62.60}}
```

`analyst.py` (the brain's own 6-hour self-diagnosis cron) reads this log and reports force-exit and
pause/resume counts per pair alongside its normal findings — the brain notices when a human has
been overriding it, even though the current volume (a handful of real overrides) is nowhere near
enough to safely act on automatically yet.

## A safety fix this shipped alongside

Building the pause/resume mechanism surfaced a real, latent bug in an unrelated existing function:
`flatten_trades` (which fires automatically before every timeframe switch) was calling FreqTrade's
`DELETE /trades/{id}` — which only removes the local database row, never fetches a price or places
an actual exit order. Invisible in dry-run, since there's no real position to abandon either way;
running this against a live account would have silently walked away from an open exchange position
while the dashboard showed it as closed. Rewritten to `POST /forceexit {tradeid: "all"}`, which
places genuine exit orders.

## Verified against the live bot, not just unit-tested

Three real trades were force-exited across both channels during testing and confirmed gone from
`/status`, landed in the closed-trade ledger with `exit_reason=force_exit` and real P&L — proving
genuine market exit orders, not a database trick.
