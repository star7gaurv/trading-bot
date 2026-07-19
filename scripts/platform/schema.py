"""Core table definitions for the Cortexa platform database (Phase 3).

SQLAlchemy Core, not the ORM — per ADR-001/roadmap decision, this stays thin.
Alembic migrations in scripts/platform/migrations/ are generated from this file
via `alembic revision --autogenerate`; this file is the source of truth for
schema shape, migrations are the applied history.

Table shapes mirror finbuddy_memory/docs/signal-contract.md and ADR-001's
Phase 3 action items 1-9. `execution_jobs` is the fan-out queue: one signal
produces one job per subscribed user, consumed by the worker pool via
`SELECT ... FOR UPDATE SKIP LOCKED` (see executor_worker.py, not yet built).
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

# --- users -------------------------------------------------------------
# Primary key is the Clerk user id directly (e.g. "user_2abc...") — one
# fewer id mapping to keep in sync with the auth provider.
users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("email", String, nullable=False, unique=True),
    Column("is_admin", Boolean, nullable=False, server_default="false"),
    # Fail-closed: a brand-new row defaults to False. Nothing enables this
    # except the explicit Phase 3.7 step-7 toggle, and even then it only
    # ever governs paper-mode execution until that step is separately built.
    Column("trading_enabled", Boolean, nullable=False, server_default="false"),
    Column("status", String, nullable=False, server_default="active"),  # active|suspended
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# --- subscriptions -------------------------------------------------------
subscriptions = Table(
    "subscriptions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("stripe_customer_id", String, nullable=True),
    Column("stripe_subscription_id", String, nullable=True, unique=True),
    Column("plan", String, nullable=True),
    # active|trialing|past_due|canceled|incomplete — mirrors Stripe's own status enum
    Column("status", String, nullable=False, server_default="incomplete"),
    Column("current_period_end", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_subscriptions_user_id", "user_id"),
)

# --- api_keys --------------------------------------------------------------
# Ciphertext-only at rest. `nonce` + `wrapped_dek` are PyNaCl envelope-
# encryption artifacts (see scripts/lib/key_vault.py, not yet built).
# `permissions_ok=False` means ccxt's account-permissions probe found
# withdrawal rights on the key — non-custodial enforcement, reject on sight.
api_keys = Table(
    "api_keys",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("exchange", String, nullable=False),  # ccxt exchange id, e.g. "binance"
    Column("label", String, nullable=True),
    Column("ciphertext", LargeBinary, nullable=False),
    Column("nonce", LargeBinary, nullable=False),
    Column("wrapped_dek", LargeBinary, nullable=False),
    Column("permissions_verified_at", DateTime(timezone=True), nullable=True),
    Column("permissions_ok", Boolean, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Index("ix_api_keys_user_id", "user_id"),
)

# --- user_settings -----------------------------------------------------
# One row per user. Seeded from users/user_01_gaurav.json's shape.
user_settings = Table(
    "user_settings",
    metadata,
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("capital_usd", Numeric, nullable=False, server_default="0"),
    Column("max_risk_per_trade_pct", Numeric, nullable=False, server_default="0.02"),
    Column("min_confidence_threshold", Numeric, nullable=False, server_default="0.60"),
    # Every new customer starts in paper mode — see Phase 3 build order step 4.
    Column("paper_trading", Boolean, nullable=False, server_default="true"),
    Column("blocked_regimes", JSONB, nullable=False, server_default='["CRASH"]'),
    Column("pairs", JSONB, nullable=False, server_default='[]'),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# --- execution_jobs ------------------------------------------------------
# The fan-out queue. On signal receipt, one row per subscribed user.
# Workers claim rows via `SELECT ... FOR UPDATE SKIP LOCKED` on
# status='queued', ordered by created_at.
execution_jobs = Table(
    "execution_jobs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("signal_id", String, nullable=False),  # UUID from the signal contract
    # queued|processing|done|failed|skipped (skipped = side:"hold" or a user-side filter)
    Column("status", String, nullable=False, server_default="queued"),
    Column("payload", JSONB, nullable=False),  # full signal-contract JSON
    Column("result", JSONB, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Index("ix_execution_jobs_status_created", "status", "created_at"),
    Index("ix_execution_jobs_user_id", "user_id"),
)

# --- trades ----------------------------------------------------------------
trades = Table(
    "trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("execution_job_id", Integer, ForeignKey("execution_jobs.id", ondelete="SET NULL"), nullable=True),
    Column("pair", String, nullable=False),
    Column("side", String, nullable=False),  # buy|sell
    Column("entry_price", Numeric, nullable=False),
    Column("exit_price", Numeric, nullable=True),
    Column("size", Numeric, nullable=False),
    Column("pnl", Numeric, nullable=True),
    Column("status", String, nullable=False, server_default="open"),  # open|closed
    Column("paper", Boolean, nullable=False, server_default="true"),
    Column("strategy_id", String, nullable=True),
    Column("opened_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("closed_at", DateTime(timezone=True), nullable=True),
    Column("raw", JSONB, nullable=True),
    Index("ix_trades_user_id", "user_id"),
    Index("ix_trades_user_status", "user_id", "status"),
)

# --- audit_log -------------------------------------------------------------
# Relational analog of finbuddy_memory/trades/manual_overrides.jsonl (the
# existing operator-side audit trail). `user_id` is nullable because some
# events are platform-wide (e.g. "admin:gaurav paused all trading").
audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("actor", String, nullable=False),  # e.g. user id, "admin:<id>", "system"
    Column("action", String, nullable=False),  # e.g. "trading_enabled", "key_revoked", "force_exit"
    Column("detail", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_audit_log_user_id", "user_id"),
    Index("ix_audit_log_created_at", "created_at"),
)

# --- seen_signals ------------------------------------------------------
# Idempotency per signal-contract.md: "Executors dedupe on this [signal_id].
# Same ID twice = ignore second." Composite PK because one signal fans out
# to many users' jobs — dedup is per (signal, user), not global.
seen_signals = Table(
    "seen_signals",
    metadata,
    Column("signal_id", String, primary_key=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("received_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# --- seen_stripe_events ------------------------------------------------
# Stripe retries webhooks; dedupe on event id before applying any effect.
seen_stripe_events = Table(
    "seen_stripe_events",
    metadata,
    Column("event_id", String, primary_key=True),
    Column("event_type", String, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
