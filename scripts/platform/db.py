"""Engine/session setup for the Cortexa platform Postgres database.

Separate from everything under freqtrade/ — this database has nothing to do
with the operator's own dry-run bot or its SQLite trade ledger. It exists
purely for the multi-tenant SaaS shell (Phase 3): customer accounts,
encrypted API keys, subscriptions, per-user execution jobs.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
Session = sessionmaker(bind=engine)
