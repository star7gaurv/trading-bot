#!/usr/bin/env python3
"""
grid_trading/paper_executor.py — simulated grid positions, paper only.

A grid is "deployed" on a ranging coin: N evenly-spaced price levels across a
band.  Each time price oscillates through one cell the strategy earns the cell
width minus fees, independently of overall direction.

PAPER ONLY (2026-06-25): no orders placed anywhere.  Virtual 1000 USDT wallet,
max 3 grids × 300 USDT each (10 levels × 30 USDT per level).  Honest
accounting: taker fees on every fill.  Slippage / inventory drift not modeled.

State:  finbuddy_memory/grid_trading/state.json
Ledger: finbuddy_memory/grid_trading/ledger.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
STATE_FILE = ROOT / "finbuddy_memory/grid_trading/state.json"
LEDGER_FILE = ROOT / "finbuddy_memory/grid_trading/ledger.jsonl"

WALLET_USDT = 1000.0        # total virtual allocation to this module
GRID_POSITION_USDT = 300.0  # total notional per deployed grid
MAX_GRIDS = 3
N_LEVELS = 10               # grid lines per deployment
TAKER_FEE_PCT = 0.0005      # 0.05% per fill (futures taker)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"grids": {}, "realized_pnl": 0.0, "last_update": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event: dict) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps({"ts": _now(), **event}) + "\n")


def open_grid(state: dict, symbol: str, price: float,
              range_pct: float, er: float, vol_pct: float) -> bool:
    """Deploy a new paper grid on `symbol` at `price`.

    The range is ±(range_pct/2) of entry price, capped at ±15% so an
    unusually wide-ranging coin doesn't produce a degenerate grid.
    Returns True on success, False if already at max capacity.
    """
    if symbol in state["grids"] or len(state["grids"]) >= MAX_GRIDS:
        return False
    half = min(range_pct / 2 / 100.0, 0.15)
    low = round(price * (1.0 - half), 8)
    high = round(price * (1.0 + half), 8)
    spacing_abs = (high - low) / (N_LEVELS - 1) if N_LEVELS > 1 else (high - low)
    spacing_pct = spacing_abs / price * 100.0
    entry_fee = GRID_POSITION_USDT * TAKER_FEE_PCT * 2.0  # two initial fills
    state["grids"][symbol] = {
        "symbol": symbol,
        "entry_price": price,
        "low": low,
        "high": high,
        "n_levels": N_LEVELS,
        "position_usdt": GRID_POSITION_USDT,
        "spacing_abs": round(spacing_abs, 8),
        "spacing_pct": round(spacing_pct, 4),
        "er": round(er, 3),
        "vol_pct": round(vol_pct, 2),
        "deployed_at": _now(),
        "last_price": price,
        "last_price_ts": _now(),
        "total_crossings": 0,
        "fees_paid": round(entry_fee, 6),
        "accrued_pnl": 0.0,    # gross fill P&L before fees
    }
    log_event({
        "event": "open",
        "symbol": symbol,
        "price": price,
        "low": low,
        "high": high,
        "range_pct": round(range_pct, 1),
        "spacing_pct": round(spacing_pct, 4),
        "er": round(er, 3),
        "vol_pct": round(vol_pct, 2),
        "entry_fee": round(entry_fee, 6),
    })
    return True


def tick_grid(state: dict, symbol: str, price_now: float) -> None:
    """Accumulate fill P&L for one price tick (called each hourly scan).

    Model: the number of grid levels crossed = floor(|Δprice| / spacing).
    Each crossing earns one fill: the cell-width profit on one level's notional,
    minus one taker fee.  This is an undercount (ignores oscillation within a
    candle) but it's conservative and honest for a paper model.
    """
    g = state["grids"].get(symbol)
    if not g:
        return
    spacing = g["spacing_abs"]
    if spacing <= 0:
        return
    pos_per_level = g["position_usdt"] / g["n_levels"]
    price_move = abs(price_now - g["last_price"])
    crossings = int(price_move / spacing)
    if crossings > 0:
        earn_per = (spacing / g["entry_price"]) * pos_per_level
        fee_per = pos_per_level * TAKER_FEE_PCT
        cycle_pnl = crossings * (earn_per - fee_per)
        g["total_crossings"] += crossings
        g["accrued_pnl"] = round(g["accrued_pnl"] + cycle_pnl, 6)
        g["fees_paid"] = round(g["fees_paid"] + crossings * fee_per, 6)
    g["last_price"] = price_now
    g["last_price_ts"] = _now()


def close_grid(state: dict, symbol: str, price_now: float, reason: str) -> None:
    g = state["grids"].pop(symbol, None)
    if not g:
        return
    net = g["accrued_pnl"] - g["fees_paid"]
    state["realized_pnl"] = round(state.get("realized_pnl", 0.0) + net, 6)
    log_event({
        "event": "close",
        "symbol": symbol,
        "reason": reason,
        "exit_price": price_now,
        "total_crossings": g["total_crossings"],
        "gross_pnl": round(g["accrued_pnl"], 4),
        "fees_total": round(g["fees_paid"], 4),
        "net_pnl": round(net, 4),
        "held_hours": round(
            (datetime.now(timezone.utc)
             - datetime.fromisoformat(g["deployed_at"])).total_seconds() / 3600, 1),
        "caveat": "slippage/inventory drift not modeled",
    })
