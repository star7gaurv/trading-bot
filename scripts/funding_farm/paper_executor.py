#!/usr/bin/env python3
"""
funding_farm/paper_executor.py — simulated delta-neutral funding harvesting.

Position model (classic cash-and-carry, positive funding only):
  short perp + long spot, equal notional → price-neutral, collects funding
  every 8h while funding is positive. Negative-funding harvesting (reverse
  carry) needs a spot margin short — out of scope.

PAPER ONLY (Phase D, 2026-06-11): no orders are placed anywhere. A virtual
500 USDT sub-wallet, max 2 positions x 250 USDT notional. Honest accounting:
entry/exit fees on both legs; basis drift is NOT modeled (recorded as caveat).
State:  finbuddy_memory/funding_farm/state.json
Ledger: finbuddy_memory/funding_farm/ledger.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
STATE_FILE = ROOT / "finbuddy_memory/funding_farm/state.json"
LEDGER_FILE = ROOT / "finbuddy_memory/funding_farm/ledger.jsonl"

WALLET_USDT = 500.0
POSITION_NOTIONAL = 250.0
MAX_POSITIONS = 2
# Round-trip cost per leg pair: perp taker 0.05% + spot taker 0.10% per side.
ENTRY_FEE_PCT = 0.0015   # 0.15% of notional at open  (both legs)
EXIT_FEE_PCT = 0.0015    # 0.15% of notional at close (both legs)
FUNDING_EVENTS_PER_DAY = 3  # 00/08/16 UTC


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"positions": {}, "realized_pnl": 0.0, "last_accrual": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event: dict) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps({"ts": _now(), **event}) + "\n")


def open_position(state: dict, symbol: str, funding_rate: float, apr: float) -> bool:
    if symbol in state["positions"] or len(state["positions"]) >= MAX_POSITIONS:
        return False
    fee = POSITION_NOTIONAL * ENTRY_FEE_PCT
    state["positions"][symbol] = {
        "notional": POSITION_NOTIONAL,
        "opened_at": _now(),
        "entry_funding_rate": funding_rate,
        "entry_apr": apr,
        "funding_collected": 0.0,
        "fees_paid": fee,
        "accruals": 0,
    }
    log_event({"event": "open", "symbol": symbol, "notional": POSITION_NOTIONAL,
               "funding_rate": funding_rate, "apr_pct": round(apr * 100, 2),
               "entry_fee": round(fee, 4)})
    return True


def accrue(state: dict, rates: dict[str, float]) -> None:
    """Credit funding for each 8h boundary crossed since the last accrual.

    Uses the symbol's CURRENT rate as the estimate for missed events — paper
    approximation, noted in the ledger.
    """
    now = datetime.now(timezone.utc)
    last = state.get("last_accrual")
    last_dt = datetime.fromisoformat(last) if last else now
    boundaries = 0
    if last:
        # count 8h funding events (00/08/16 UTC) in (last_dt, now]
        cur = last_dt.replace(minute=0, second=0, microsecond=0)
        from datetime import timedelta
        cur += timedelta(hours=1)
        while cur <= now:
            if cur.hour in (0, 8, 16) and cur > last_dt:
                boundaries += 1
            cur += timedelta(hours=1)
    state["last_accrual"] = _now()
    if not boundaries:
        return
    for symbol, pos in state["positions"].items():
        rate = rates.get(symbol)
        if rate is None:
            continue
        # short perp receives positive funding
        credit = pos["notional"] * rate * boundaries
        pos["funding_collected"] += credit
        pos["accruals"] += boundaries
        log_event({"event": "accrue", "symbol": symbol, "events": boundaries,
                   "rate": rate, "credit": round(credit, 4)})


def close_position(state: dict, symbol: str, reason: str) -> None:
    pos = state["positions"].pop(symbol, None)
    if not pos:
        return
    exit_fee = pos["notional"] * EXIT_FEE_PCT
    net = pos["funding_collected"] - pos["fees_paid"] - exit_fee
    state["realized_pnl"] += net
    log_event({"event": "close", "symbol": symbol, "reason": reason,
               "funding_collected": round(pos["funding_collected"], 4),
               "fees_total": round(pos["fees_paid"] + exit_fee, 4),
               "net_pnl": round(net, 4),
               "held_hours": round(
                   (datetime.now(timezone.utc)
                    - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600, 1),
               "caveat": "basis drift not modeled"})


def summary(days: int = 7) -> dict:
    """Aggregate ledger for reporting (used by daily_summary.py)."""
    if not LEDGER_FILE.exists():
        return {"net_7d": 0.0, "open_positions": 0, "realized_total": 0.0}
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    net = 0.0
    for line in LEDGER_FILE.read_text().splitlines():
        e = json.loads(line)
        if datetime.fromisoformat(e["ts"]) < cutoff:
            continue
        if e["event"] == "accrue":
            net += e.get("credit", 0.0)
        elif e["event"] == "open":
            net -= e.get("entry_fee", 0.0)
        elif e["event"] == "close":
            net -= e.get("fees_total", 0.0) - 0.0
    state = load_state()
    unrealized = sum(p["funding_collected"] - p["fees_paid"]
                     for p in state["positions"].values())
    return {
        "net_7d": round(net, 2),
        "open_positions": len(state["positions"]),
        "realized_total": round(state.get("realized_pnl", 0.0), 2),
        "unrealized": round(unrealized, 2),
    }
