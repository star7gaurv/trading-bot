#!/usr/bin/env python3
"""
liq_capitulation/paper_executor.py — simulated contrarian liquidation-bounce, paper only.

EDGE (measured 2026-06-30, scripts/brain/liquidation_ic.py + event study): after a moderate
LONG-liquidation cascade (forced selling / capitulation, 2 <= liq_long_z <= 3), 6h-forward
return is +0.083% vs -0.064% baseline (51% WR, +14.7bps, 26-pair consistent). The EXTREME tail
(z>3) reverses (-0.27%, knife-catch) so we skip it. Edge ~+8bps/trade: NET NEGATIVE on taker
(~10bps round-trip) but NET POSITIVE on maker (~4bps). So this module assumes MAKER limit entries.

⚠️ The honest unknown a backtest can't answer: maker fills suffer ADVERSE SELECTION during a
capitulation (you fill the knives that keep falling, miss the ones that bounce). This paper
module exists to measure that with live fills before any real-money discussion. Fills are
modeled at candle close (optimistic — real maker fills are worse); logged as a caveat.

PAPER ONLY. Virtual 1000 USDT, max 3 longs × 200 USDT. Long-only contrarian.
State:  finbuddy_memory/liq_capitulation/state.json
Ledger: finbuddy_memory/liq_capitulation/ledger.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
STATE_FILE = ROOT / "finbuddy_memory/liq_capitulation/state.json"
LEDGER_FILE = ROOT / "finbuddy_memory/liq_capitulation/ledger.jsonl"

WALLET_USDT = 1000.0
POSITION_USDT = 200.0
MAX_POSITIONS = 3
MAKER_FEE_PCT = 0.0002      # 0.02% per fill — the signal only clears costs at maker fees

HOLD_HOURS = 6              # event-study horizon
TAKE_PROFIT_PCT = 0.015     # +1.5% bounce target
STOP_PCT = -0.03            # -3% — protect against capitulation that keeps falling


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"positions": {}, "realized_pnl": 0.0, "wins": 0, "losses": 0, "last_update": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event: dict) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps({"ts": _now(), **event}) + "\n")


def open_position(state: dict, symbol: str, price: float, liq_z: float,
                  liq_long_usd: float) -> bool:
    """Open a paper LONG on a capitulation. Returns False if at capacity / already in."""
    if symbol in state["positions"] or len(state["positions"]) >= MAX_POSITIONS or price <= 0:
        return False
    entry_fee = POSITION_USDT * MAKER_FEE_PCT
    state["positions"][symbol] = {
        "symbol": symbol,
        "side": "long",
        "entry_price": price,
        "notional": POSITION_USDT,
        "entry_liq_z": round(liq_z, 3),
        "entry_liq_long_usd": round(liq_long_usd, 0),
        "opened_at": _now(),
        "fees_paid": round(entry_fee, 6),
    }
    log_event({"event": "open", "symbol": symbol, "side": "long", "price": price,
               "liq_long_z": round(liq_z, 3), "liq_long_usd": round(liq_long_usd, 0),
               "entry_fee": round(entry_fee, 6)})
    return True


def check_exit(pos: dict, price_now: float, held_hours: float) -> str | None:
    """Return an exit reason or None. TP / SL / time-stop at the 6h horizon."""
    if price_now <= 0:
        return None
    ret = price_now / pos["entry_price"] - 1.0
    if ret >= TAKE_PROFIT_PCT:
        return f"take-profit (+{ret*100:.2f}%)"
    if ret <= STOP_PCT:
        return f"stop ({ret*100:.2f}%)"
    if held_hours >= HOLD_HOURS:
        return f"time stop ({held_hours:.1f}h, {ret*100:+.2f}%)"
    return None


def close_position(state: dict, symbol: str, price_now: float, reason: str) -> float:
    pos = state["positions"].pop(symbol, None)
    if not pos:
        return 0.0
    gross = pos["notional"] * (price_now / pos["entry_price"] - 1.0)
    exit_fee = pos["notional"] * MAKER_FEE_PCT
    fees = pos["fees_paid"] + exit_fee
    net = gross - fees
    state["realized_pnl"] = round(state.get("realized_pnl", 0.0) + net, 6)
    state["wins"] = state.get("wins", 0) + (1 if net > 0 else 0)
    state["losses"] = state.get("losses", 0) + (1 if net <= 0 else 0)
    log_event({"event": "close", "symbol": symbol, "reason": reason, "exit_price": price_now,
               "entry_price": pos["entry_price"], "gross_pnl": round(gross, 4),
               "fees_total": round(fees, 4), "net_pnl": round(net, 4),
               "held_hours": round((datetime.now(timezone.utc)
                                    - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600, 1),
               "caveat": "maker fill modeled at close — optimistic vs real adverse selection"})
    return net
