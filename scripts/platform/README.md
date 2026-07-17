# FinBuddy Platform (Phase 3 — multi-tenant SaaS shell)

Everything under this directory is new and additive. It never touches
`freqtrade/`, its config, or the operator's own dashboard/streamer.py — the
live dry-run bot is not put at risk by any of this.

## Setup (one-time)

1. **Postgres role + database** (needs a real sudo password — the automation
   account's sudoers scope is deliberately narrowed to `apt`/`systemctl`/
   `docker`/`journalctl`, no generic superuser access):
   ```
   sudo -u postgres psql -f scripts/platform/bootstrap_db.sql
   ```
   This creates the `finbuddy_platform` role + database. Safe to re-run.
   The real file (gitignored — it embeds the generated password) is already
   written; `bootstrap_db.sql.example` is the committed template.

2. **Dedicated venv** (already created, keeps these deps off the host
   python3 that brain crons share):
   ```
   /home/ubuntu/.finbuddy/venvs/platform/bin/pip install -r scripts/platform/requirements.txt
   ```

3. **Apply migrations**:
   ```
   cd scripts/platform
   /home/ubuntu/.finbuddy/venvs/platform/bin/alembic upgrade head
   ```

4. **Verify**:
   ```
   /home/ubuntu/.finbuddy/venvs/platform/bin/python3 -c "
   from db import engine
   from sqlalchemy import inspect
   print(sorted(inspect(engine).get_table_names()))
   "
   ```
   Expect: `['alembic_version', 'api_keys', 'audit_log', 'execution_jobs',
   'seen_signals', 'seen_stripe_events', 'subscriptions', 'trades', 'users',
   'user_settings']`

5. **Install the API-key vault's master key** (KEK — same sudo boundary as
   step 1, a real key already generated and waiting at
   `scripts/platform/.platform_master.key.tmp`, gitignored):
   ```
   sudo install -o root -g root -m 600 scripts/platform/.platform_master.key.tmp /etc/finbuddy/platform_master.key
   rm scripts/platform/.platform_master.key.tmp
   ```
   Verify: `sudo -n cat /etc/finbuddy/platform_master.key | wc -c` → `32`.
   **Back this file up offline once installed** — losing it means every
   customer who has connected an exchange key must reconnect it. Never put
   it in the same backup as the Postgres DB (defeats the point of separating
   the two secrets).

## Files

- `schema.py` — SQLAlchemy Core table definitions (source of truth for shape)
- `db.py` — engine/session setup, reads `DATABASE_URL` from `.env` (gitignored)
- `migrations/` — Alembic migration history (`0001_initial_schema.py` is
  hand-written to match `schema.py` exactly, authored before the DB existed)
- `bootstrap_db.sql` (gitignored, real password) / `.example` (committed template)

## Design notes

- SQLAlchemy Core, not the ORM — deliberately thin (ADR-001/roadmap decision).
- `users.trading_enabled` defaults `false` (fail-closed) — nothing in this
  phase's build order flips it to `true` until Phase 3 step 7 (the final,
  individually-gated live-trading toggle) is separately built and approved.
- `user_settings.paper_trading` defaults `true` — every new customer starts
  in paper mode, per the plan's Phase 3 build-order step 4.
- `execution_jobs` is the fan-out queue: one signal → one row per subscribed
  user, consumed via `SELECT ... FOR UPDATE SKIP LOCKED` (worker pool, not
  yet built — see `executor_worker.py`).
- `seen_signals` PK is `(signal_id, user_id)`, not just `signal_id` — one
  signal fans out to N users, dedup is per-user per signal-contract.md.
- API-key encryption lives at `scripts/lib/key_vault.py` (PyNaCl envelope
  encryption, KEK/DEK two-layer per ADR-001) — self-tested standalone
  (roundtrip, tamper-rejection via authenticated encryption, missing-key
  handling) before any DB wiring existed. `check_non_custodial()` currently
  has a real implementation only for Binance (`sapiGetAccountApiRestrictions`);
  every other exchange returns `ok=None` ("unverified") rather than a false
  "safe" — callers must treat `None` as reject-or-flag, never as pass.
