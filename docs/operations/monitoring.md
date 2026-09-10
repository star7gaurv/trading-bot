# Monitoring & Alerting

## Telegram is the primary channel

Every alerting mechanism in this system posts to a single Telegram chat via a shared formatting
library (`scripts/lib/telegram_template.py`), so every message — brain experiment result, trade
notification, watchdog alert, daily digest — follows the same layout: which subsystem is speaking,
a status (OK/INFO/WARN/FAIL/ACTION), key fields, and a one-line context. That consistency exists so
messages can be scanned at a glance from a phone without opening each one.

## Watchdog

`scripts/watchdog.py` (cron, every 30 minutes) checks disk usage (warns at 80%, critical at 90%),
CPU load (warns at 1x core count, critical at 1.5x), and container/training/heartbeat health, and
alerts on anything crossing threshold.

## Data Sentinel

`scripts/data_sentinel.py` (cron, every 6 hours) checks every external data feed, every cron job,
and the brain's queue schema for silent failures — freshness, non-constancy (a feed that's stopped
updating but hasn't actually errored), and liveness. Built after this project hit the same silent-
failure pattern (a cron missing its `cd` into the project root, and therefore dying immediately
and invisibly) more than once — see [Contributing](../contributing.md#the-cron-rule).

## The Edge Gate — self-awareness, not just monitoring

`scripts/edge_monitor.py` (cron, every 30 minutes) is a different category from the above: it
doesn't just alert a human, it changes live behavior. See [The Brain](../brain.md#the-edge-gate)
for the full reasoning. Its current state is always readable at
`finbuddy_memory/analytics/edge_state.json`.

## Daily digest

`scripts/daily_summary.py` (cron, 08:00 UTC) posts a morning summary: current regime, open
trades, yesterday's closed P&L, last training age, and — since 2026-09-07 — the edge gate's
current status, so its state is visible every morning without needing to check a file.

## Weekly prediction-quality report

`scripts/ic_monitor.py` (cron, Monday 06:30 UTC) reports the live model's rank correlation between
predictions and realized outcomes, both all-time and over a rolling 30 days, per pair and pooled.
This is the same measurement `edge_monitor.py` consumes live — the weekly report is the
human-readable, per-pair breakdown of the same underlying signal.
