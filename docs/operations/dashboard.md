# Operator Dashboard

`dashboard/` (FastAPI backend, `streamer.py` is the main API surface) plus `dashboard-ui/` (React
frontend) together form the operator's own console — password-gated, operator-only, not a
customer-facing surface. It's fine for this dashboard to show real system names and internals; see
[Confidentiality](../confidentiality.md) for exactly where that line is.

## What it's for

A live, phone-reachable view into every module — Directional, Grid Trading, Pairs Trading, Funding
Farm, Arbitrage — each grouped under its own tab with a plain-English one-line description, a
status badge (`LIVE` / `PAPER`), and a hero P&L number, followed by open positions, recent trades,
and module-specific detail. A separate `System` group covers the brain's experiment queue, the
walk-forward history, overall system health, and settings.

## How it connects to the live system

`streamer.py` talks to the real FreqTrade REST API (`/api/v1/`, loopback-only — see
[Security](security.md)) and to each paper module's own `state.json`/`ledger.jsonl` files directly.
A WebSocket layer pushes live updates rather than requiring the frontend to poll.

## The manual control surface lives here too

The same dashboard exposes the force-exit and pause/resume controls covered on
[Manual Trade Control](../strategy/manual-control.md) — a Close button on any open trade, and a
global pause toggle, both calling real FreqTrade order endpoints, not database-only tricks.

## Deployment

Served from `trade.star7gaurav.in` (Cloudflare-fronted), with static assets served content-hashed
and cached forever, while `index.html` itself is always served no-cache — so a new build's asset
hashes get picked up on next load without anyone needing to hard-refresh. This exact caching setup
was the fix for a real bug: pagination silently breaking after every rebuild, root-caused
2026-06-19 to browsers holding onto a stale `index.html` pointing at deleted asset bundles, not a
code defect in the pagination logic itself.

## Reference

The backend's full endpoint surface is auto-documented at
[`reference/dashboard/streamer`](../reference/dashboard/streamer.md); the smaller supporting
modules (`auth.py`, `system_health.py`, `cron_status.py`) are alongside it in the same reference
section.
