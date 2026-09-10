# Getting Started

## Where this actually runs

Everything documented here runs on a single Oracle Free Tier server (Ubuntu 24.04 ARM64, 4 vCPU,
24GB RAM) at `/home/ubuntu/var/www/html/trade/`. There is no staging environment and no separate
docs server — this site is built from the same repo the live system runs from, and served from
the same box.

Gaurav manages this entire system from his phone via Termius SSH. That's not a limitation, it's a
constraint every design decision here respects: no Kubernetes, no microservices, nothing that
can't be debugged from a phone over SSH.

## Building this site

```bash
/home/ubuntu/.finbuddy/venvs/docs/bin/mkdocs build    # outputs to ./site/
/home/ubuntu/.finbuddy/venvs/docs/bin/mkdocs serve     # live-reload dev server on :8000
```

A dedicated virtualenv (`~/.finbuddy/venvs/docs/`) holds the MkDocs toolchain, following this
project's own convention of one venv per non-core-dependency tool (see the arbitrage module's
`~/.finbuddy/venvs/arbitrage/` for the same pattern) — it never touches the system Python or the
FreqTrade container's dependencies.

`mkdocs serve` binds to `127.0.0.1:8000` by default. Reach it from a phone via an SSH port
forward through Termius (local port 8000 → `127.0.0.1:8000` on the server) rather than exposing it
publicly — this site names real internal system details and is not meant to be internet-facing.

## Keeping it current

Most of this site regenerates itself from the live codebase and crontab on every build — see
[Contributing](contributing.md). The narrative pages (this one, Architecture, Strategy & Brain,
the Modules pages) are hand-written and need a human to update them when something material
changes, the same way `CLAUDE.md`'s session history does.

## The single source of truth for "what's live right now"

This site is the deep-reference layer. For the current, day-to-day operational state — which
FreqAI identifier is live, what the edge gate is doing, what changed in the last session — always
check `CLAUDE.md` at the repo root first. It's updated at the end of every substantive working
session and is the fastest way to know what's actually true right now.
