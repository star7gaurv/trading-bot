#!/usr/bin/env python3
"""
FinBuddy Signal Executor — paper trading mode with signal dedup and regime filter.
Simplified version without FastAPI (stores in SQLite, can be called via cron).
"""
import sqlite3, json, os
from datetime import datetime, timezone
from pathlib import Path

ROOT    = Path("/home/ubuntu/var/www/html/trade")
DB_PATH = ROOT / "freqtrade/user_data/executor.sqlite"
CFG_PATH= ROOT / "users/user_01_gaurav.json"
SIGNAL_FILE = ROOT / "freqtrade/user_data/data/external/executor_signals.json"

USER_CONFIG = json.loads(CFG_PATH.read_text())

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_signals (
            signal_id TEXT PRIMARY KEY,
            received_at TEXT,
            pair TEXT,
            side TEXT,
            confidence REAL,
            regime TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

def process_signals():
    """Process signals from executor_signals.json."""
    init_db()

    if not SIGNAL_FILE.exists():
        return

    try:
        with open(SIGNAL_FILE) as f:
            signals = json.load(f)
    except Exception:
        return

    conn = sqlite3.connect(DB_PATH)

    for signal in signals:
        signal_id = signal.get("signal_id", f"auto_{datetime.utcnow().timestamp()}")

        if conn.execute("SELECT 1 FROM seen_signals WHERE signal_id=?", [signal_id]).fetchone():
            continue

        confidence = signal.get("confidence", 1.0)
        if confidence < USER_CONFIG.get("min_confidence_threshold", 0.6):
            conn.execute("INSERT INTO seen_signals VALUES (?,?,?,?,?,?,?)",
                [signal_id, datetime.utcnow().isoformat(), signal.get("pair","?"), signal.get("side","?"), confidence, signal.get("regime","?"), "skipped_low_confidence"])
            conn.commit()
            continue

        regime = signal.get("regime", "NEUTRAL")
        blocked = USER_CONFIG.get("regime_filter", {}).get("blocked_regimes", ["CRASH"])
        if regime in blocked:
            conn.execute("INSERT INTO seen_signals VALUES (?,?,?,?,?,?,?)",
                [signal_id, datetime.utcnow().isoformat(), signal.get("pair","?"), signal.get("side","?"), confidence, regime, f"skipped_regime_{regime}"])
            conn.commit()
            continue

        side = signal.get("side", "hold")
        pair = signal.get("pair", "BTC/USDT")
        status = "accepted"

        if side in ("buy", "sell") and USER_CONFIG.get("paper_trading", True):
            print(f"[PAPER] {side.upper()} {pair} | conf={confidence} | regime={regime}")
            status = f"paper_{side}"

        conn.execute("INSERT INTO seen_signals VALUES (?,?,?,?,?,?,?)",
            [signal_id, datetime.utcnow().isoformat(), pair, side, confidence, regime, status])
        conn.commit()

    conn.close()

if __name__ == "__main__":
    process_signals()
