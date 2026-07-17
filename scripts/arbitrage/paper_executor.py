#!/usr/bin/env python3
"""
arbitrage/paper_executor.py — simulated capture of cross-venue price gaps.

Unlike Funding Farm (positions held for days) or Grid/Pairs (positions held until a
condition triggers), an arbitrage capture is ATOMIC: both legs execute in the same
instant in the simulation, so there's no "open position" state to carry between runs
— just a running wallet balance and a log of what happened.

Honesty rule (this is the whole point of this module, not an afterthought): only
`intra_exchange_basis` and `cross_exchange_prefunded` opportunities ever move the
paper wallet. `cross_exchange_transfer` opportunities get an `observe` event with
`realizable: false` — logged so the breadth of exchanges polled is doing its actual
job (finding where price gaps exist), but never counted as captured profit, since
withdrawal/deposit time almost always exceeds a real cross-exchange gap's lifetime.

PAPER ONLY — no orders are ever placed anywhere.
State:  finbuddy_memory/arbitrage/state.json
Ledger: finbuddy_memory/arbitrage/ledger.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
STATE_FILE = ROOT / "finbuddy_memory/arbitrage/state.json"
LEDGER_FILE = ROOT / "finbuddy_memory/arbitrage/ledger.jsonl"

WALLET_USDT = 1000.0
NOTIONAL_PER_CAPTURE = 200.0
MAX_CAPTURES_PER_RUN = 3  # cap how much of one scanner cycle's opportunities get "taken"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "wallet_usdt": WALLET_USDT,
        "realized_pnl": 0.0,
        "captures": 0,
        "observations": 0,
        "last_run": None,
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event: dict) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps({"ts": _now(), **event}, default=str) + "\n")


def capture(state: dict, opportunity: dict) -> float:
    """Record a realized paper capture (category 1 or 2 only — see module docstring).
    Returns the net P&L booked."""
    notional = NOTIONAL_PER_CAPTURE
    gross_gap_pct = opportunity["gap_pct"]
    fees_pct = opportunity["fees_pct"]
    net_pct = gross_gap_pct - fees_pct
    net_pnl = notional * net_pct

    state["wallet_usdt"] += net_pnl
    state["realized_pnl"] += net_pnl
    state["captures"] += 1

    log_event({
        "type": "capture",
        "opportunity_type": opportunity["opportunity_type"],
        "symbol": opportunity["symbol"],
        "buy_exchange": opportunity["buy_exchange"],
        "sell_exchange": opportunity["sell_exchange"],
        "buy_price": opportunity["buy_price"],
        "sell_price": opportunity["sell_price"],
        "notional": notional,
        "gross_gap_pct": round(gross_gap_pct * 100, 4),
        "fees_pct": round(fees_pct * 100, 4),
        "net_pnl": round(net_pnl, 4),
        "caveat": opportunity.get("caveat"),
    })
    return net_pnl


def observe(state: dict, opportunity: dict) -> None:
    """Record a discovery-only gap (category 3: cross_exchange_transfer) — never
    touches the wallet. This is the module doing its actual job of finding gaps
    across many venues without pretending they're all instantly tradable.

    Not every observation is a cross_exchange_transfer gap specifically — an
    intra_exchange_basis or cross_exchange_prefunded opportunity that simply
    didn't clear its own fees also lands here (scanner.py routes anything
    below the fee threshold to observe(), not just category-3 gaps). The
    `reason` field reflects which case actually applies."""
    state["observations"] += 1
    opp_type = opportunity["opportunity_type"]
    if opp_type == "cross_exchange_transfer":
        reason = ("cross-exchange transfer time almost always exceeds a real gap's lifetime "
                   "without capital already pre-positioned on both venues")
    else:
        reason = "gap did not clear the assumed round-trip fee cost"
    log_event({
        "type": "observe",
        "opportunity_type": opp_type,
        "symbol": opportunity["symbol"],
        "buy_exchange": opportunity["buy_exchange"],
        "sell_exchange": opportunity["sell_exchange"],
        "buy_price": opportunity["buy_price"],
        "sell_price": opportunity["sell_price"],
        "gap_pct": round(opportunity["gap_pct"] * 100, 4),
        "realizable": opp_type != "cross_exchange_transfer",
        "reason": reason,
    })


def summary(days: int = 7) -> dict:
    """Aggregate ledger for reporting (used by the dashboard endpoint)."""
    state = load_state()
    if not LEDGER_FILE.exists():
        return {
            "wallet_usdt": state.get("wallet_usdt", WALLET_USDT),
            "realized_pnl": state.get("realized_pnl", 0.0),
            "captures_7d": 0, "observations_7d": 0,
            "captures_total": state.get("captures", 0),
            "observations_total": state.get("observations", 0),
        }
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    captures_7d = observations_7d = 0
    for line in LEDGER_FILE.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if datetime.fromisoformat(e["ts"]) < cutoff:
            continue
        if e.get("type") == "capture":
            captures_7d += 1
        elif e.get("type") == "observe":
            observations_7d += 1
    return {
        "wallet_usdt": round(state.get("wallet_usdt", WALLET_USDT), 2),
        "realized_pnl": round(state.get("realized_pnl", 0.0), 2),
        "captures_7d": captures_7d,
        "observations_7d": observations_7d,
        "captures_total": state.get("captures", 0),
        "observations_total": state.get("observations", 0),
    }
