#!/usr/bin/env python3
"""
pairs_trading/paper_executor.py — simulated market-neutral statistical arbitrage.

Position model (classic pairs trade, beta-weighted, dollar-balanced):
  When the spread between two correlated coins (A vs B) stretches far from its
  mean, go long the cheap leg and short the rich leg. Profit comes when the
  spread reverts — independent of overall market direction.

    side = +1  →  long A / short B   (spread is low: A cheap vs B)
    side = -1  →  short A / long B   (spread is high: A rich vs B)

PAPER ONLY (2026-06-25): no orders are placed anywhere. A virtual 500 USDT
sub-wallet, max 3 positions x ~200 USDT each (split across the two legs by the
hedge ratio so the position is beta-neutral). Honest accounting: taker fees on
both legs at entry and exit. Slippage/borrow are NOT modeled (recorded caveat).

State:  finbuddy_memory/pairs_trading/state.json
Ledger: finbuddy_memory/pairs_trading/ledger.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
STATE_FILE = ROOT / "finbuddy_memory/pairs_trading/state.json"
LEDGER_FILE = ROOT / "finbuddy_memory/pairs_trading/ledger.jsonl"

WALLET_USDT = 500.0
POSITION_USDT = 200.0       # total per pair, split across the two legs
MAX_POSITIONS = 3
TAKER_FEE_PCT = 0.0005      # 0.05% per leg per side (futures taker)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(a: str, b: str) -> str:
    return f"{a}/{b}"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"positions": {}, "realized_pnl": 0.0, "last_update": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event: dict) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps({"ts": _now(), **event}) + "\n")


def leg_notionals(beta: float) -> tuple[float, float]:
    """Split POSITION_USDT across legs A and B by the hedge ratio so the dollar
    exposure is beta-neutral. notional_b = beta * notional_a, summing to POSITION."""
    beta = max(0.2, min(5.0, abs(beta)))
    notional_a = POSITION_USDT / (1.0 + beta)
    notional_b = POSITION_USDT - notional_a
    return round(notional_a, 4), round(notional_b, 4)


def position_pnl(pos: dict, price_a: float, price_b: float) -> float:
    """Mark-to-market unrealized P&L (before exit fee)."""
    ret_a = price_a / pos["entry_price_a"] - 1.0
    ret_b = price_b / pos["entry_price_b"] - 1.0
    side = pos["side"]
    # long leg earns +ret, short leg earns -ret
    long_a = side == 1
    pnl_a = pos["notional_a"] * (ret_a if long_a else -ret_a)
    pnl_b = pos["notional_b"] * (-ret_b if long_a else ret_b)
    return pnl_a + pnl_b


def open_position(state: dict, a: str, b: str, side: int, beta: float, z: float,
                  price_a: float, price_b: float, corr: float, half_life_h) -> bool:
    key = _key(a, b)
    if key in state["positions"] or len(state["positions"]) >= MAX_POSITIONS:
        return False
    na, nb = leg_notionals(beta)
    fee = (na + nb) * TAKER_FEE_PCT
    state["positions"][key] = {
        "a": a, "b": b, "side": side, "beta": round(beta, 4),
        "entry_z": round(z, 3), "corr": round(corr, 3),
        "entry_price_a": price_a, "entry_price_b": price_b,
        "notional_a": na, "notional_b": nb,
        "opened_at": _now(), "fees_paid": round(fee, 4),
        "half_life_h": half_life_h,
    }
    log_event({"event": "open", "pair": key, "side": side,
               "trade": (f"long {a} / short {b}" if side == 1 else f"short {a} / long {b}"),
               "z": round(z, 2), "beta": round(beta, 3), "corr": round(corr, 3),
               "notional": POSITION_USDT, "entry_fee": round(fee, 4)})
    return True


def close_position(state: dict, key: str, price_a: float, price_b: float,
                   reason: str, cur_z) -> None:
    pos = state["positions"].pop(key, None)
    if not pos:
        return
    gross = position_pnl(pos, price_a, price_b)
    exit_fee = (pos["notional_a"] + pos["notional_b"]) * TAKER_FEE_PCT
    net = gross - exit_fee  # entry fee already deducted at realization below
    net_after_entry = net - pos["fees_paid"]
    state["realized_pnl"] += net_after_entry
    log_event({"event": "close", "pair": key, "reason": reason,
               "exit_z": round(cur_z, 2) if cur_z is not None else None,
               "gross_pnl": round(gross, 4),
               "fees_total": round(pos["fees_paid"] + exit_fee, 4),
               "net_pnl": round(net_after_entry, 4),
               "held_hours": round(
                   (datetime.now(timezone.utc)
                    - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600, 1),
               "caveat": "slippage/borrow not modeled"})


def summary(days: int = 7) -> dict:
    state = load_state()
    realized = round(state.get("realized_pnl", 0.0), 2)
    if not LEDGER_FILE.exists():
        return {"net_7d": 0.0, "open_positions": len(state["positions"]),
                "realized_total": realized}
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    net = 0.0
    for line in LEDGER_FILE.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if datetime.fromisoformat(e["ts"]) < cutoff:
            continue
        if e["event"] == "close":
            net += e.get("net_pnl", 0.0)
        elif e["event"] == "open":
            net -= e.get("entry_fee", 0.0)
    return {"net_7d": round(net, 2), "open_positions": len(state["positions"]),
            "realized_total": realized}
