# Confidentiality Style Guide

**Read this before writing anything customer-facing, public, or marketing-adjacent** (landing
page, in-app copy, support docs, investor materials, error messages shown to users).

## The rule

Cortexa's underlying tech stack is confidential. Never name it — not the framework, not specific
libraries, not internal script/service/container names — in anything a customer, prospect, or the
public could see.

## Never say, in customer/public-facing content

- **FreqTrade**, **FreqAI** — the trading-execution framework this is built on
- **Docker**, container names, image names
- **LightGBM**, **Optuna**, or any other specific ML/optimization library by name
- Internal script names (`brain_cli.py`, `promote.py`, `runner.py`, cron job names, etc.)
- Config file names, environment variable names, database table names
- Raw error messages or stack traces from any internal system

## Say instead

| Instead of... | Say... |
|---|---|
| "Built on FreqTrade/FreqAI" | "a self-evolving AI trading engine" / "our proprietary execution engine" |
| "LightGBM regression model" | "a custom-built machine-learning model" |
| A raw exception message | A generic, safe message (see `scripts/lib/user_facing_errors.py` once built — Phase 3) |
| A specific script/cron name | "our automated systems" / describe what it does, not what it's called |

## Where this is enforced

- **`landing/index.html`** — audited and fixed 2026-07-17 (previously said "Built on
  FreqTrade/FreqAI").
- **This docs site** (`docs/`, built by MkDocs) is internal-only and can reference the real stack
  freely — that's the point of it. The rule is about what leaves this boundary, not what's true
  internally.
- **The operator dashboard** (`dashboard-ui/`) is password-gated and operator-only (Gaurav's own
  debugging tool) — it's fine for it to show real names (e.g. System Health's "FreqTrade: Up 8
  days"). It is not a customer-facing surface.
- **Future customer/admin panels** (Phase 3 of the platform roadmap) will route every
  customer-visible error through a generic-message mapping layer
  (`scripts/lib/user_facing_errors.py`) rather than relying on every call site remembering this
  rule by hand.

## When in doubt

If a prospective customer, journalist, or competitor could plausibly read it, run it past this
list first.
