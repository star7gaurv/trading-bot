#!/usr/bin/env python3
"""
grid_trading/scanner.py — hourly paper grid manager.

Each run:
  1. Tick every open grid (accumulate crossing P&L since last hour).
  2. Close grids where price broke out of the range, coin went trending,
     or the hold limit expired.
  3. Scan whitelist for new grid candidates (ranging + volatile coins).

Ranking: grid_score = vol% × (1 − ER).  Higher = more profitable grid.
PAPER MODE ONLY.  Cron: hourly at :40.

Open  : ER < 0.30 AND vol% > 0.50 AND capacity available
Tick  : each scan — count how many levels price crossed, earn per crossing
Close : price < low | price > high | held > 14d | ER > 0.50 (gone trending)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/grid_trading"))
sys.path.insert(0, str(ROOT / "scripts/lib"))
import paper_executor as gx  # noqa: E402
from live_price import get_live_price  # noqa: E402

try:
    from lib.telegram_template import Subsystem, Status, send  # noqa: E402
    _TG = True
except Exception:
    _TG = False

CONFIG = ROOT / "freqtrade/user_data/config.json"
DATA_DIR = ROOT / "freqtrade/user_data/data/binance/futures"

LOOK = 336           # 14 days of 1h candles
MAX_ER_OPEN = 0.30   # max trendiness to open a grid
MIN_VOL_OPEN = 0.50  # min hourly swing % to open a grid
MAX_ER_CLOSE = 0.50  # close if coin goes trending
MAX_HOLD_DAYS = 14


def load_closes() -> pd.DataFrame:
    cfg = json.load(open(CONFIG))
    wl = cfg["exchange"]["pair_whitelist"]
    closes: dict[str, pd.Series] = {}
    for p in wl:
        base = p.split("/")[0]
        f = DATA_DIR / f"{base}_USDT_USDT-1h-futures.feather"
        if not f.exists():
            continue
        try:
            s = pd.read_feather(f).set_index("date")["close"].tail(LOOK)
        except Exception:
            continue
        if len(s) >= LOOK * 0.8:
            closes[base] = s
    df = pd.DataFrame(closes)
    return df


def coin_stats(close: pd.Series, live_price: float | None = None) -> dict:
    """er/vol/range from the historical window (feather is fine here — only its
    tail can be stale, and this needs the whole trailing window regardless).
    `price` is the CURRENT price used for crossing/threshold checks — pass
    live_price (fixed 2026-07-14, see scripts/lib/live_price.py) so it isn't
    silently hours stale; falls back to the window's last close if omitted."""
    close = close.dropna()
    if len(close) < 10:
        return {"er": 1.0, "vol": 0.0, "range_pct": 0.0, "price": 0.0}
    net = abs(float(close.iloc[-1]) - float(close.iloc[0]))
    path = float(close.diff().abs().sum())
    er = (net / path) if path > 0 else 1.0
    vol = float(close.pct_change().std() * 100)
    mean = float(close.mean())
    rng = float((close.max() - close.min()) / mean * 100) if mean else 0.0
    price = live_price if live_price and live_price > 0 else float(close.iloc[-1])
    return {"er": round(er, 4), "vol": round(vol, 4),
            "range_pct": round(rng, 2), "price": price}


def main() -> int:
    px_df = load_closes()
    if px_df.empty:
        print("[grid] not enough price data")
        return 0

    state = gx.load_state()
    now = datetime.now(timezone.utc)

    # 1) tick + close check on every open grid
    for sym in list(state["grids"].keys()):
        g = state["grids"][sym]
        if sym not in px_df.columns:
            continue
        s = coin_stats(px_df[sym], live_price=get_live_price(sym))
        price = s["price"]
        if price <= 0:
            continue

        gx.tick_grid(state, sym, price)

        held_days = (now - datetime.fromisoformat(g["deployed_at"])).total_seconds() / 86400
        reason = None
        if price < g["low"]:
            reason = f"price broke below ({price:.5g} < {g['low']:.5g})"
        elif price > g["high"]:
            reason = f"price broke above ({price:.5g} > {g['high']:.5g})"
        elif held_days > MAX_HOLD_DAYS:
            reason = f"time stop ({held_days:.0f}d)"
        elif s["er"] > MAX_ER_CLOSE:
            reason = f"gone trending (ER={s['er']:.2f})"

        if reason:
            net = g["accrued_pnl"] - g["fees_paid"]
            gx.close_grid(state, sym, price, reason)
            print(f"[grid] closed {sym} — {reason}  net={net:+.2f}")
            if _TG:
                send(Subsystem.BRAIN_CYCLE, Status.INFO,
                     f"Grid (paper): closed {sym}",
                     fields={"Reason": reason, "Net P&L": f"{net:+.2f} USDT"},
                     silent=True)

    # 2) scan for new candidates
    candidates = []
    for sym in px_df.columns:
        if sym in state["grids"]:
            continue
        s = coin_stats(px_df[sym])
        if s["er"] < MAX_ER_OPEN and s["vol"] > MIN_VOL_OPEN and s["price"] > 0:
            score = s["vol"] * (1.0 - s["er"])
            candidates.append((sym, s, score))
    candidates.sort(key=lambda x: x[2], reverse=True)

    for sym, s, _ in candidates:
        if len(state["grids"]) >= gx.MAX_GRIDS:
            break
        entry_price = get_live_price(sym) or s["price"]  # live at the moment of entry
        if gx.open_grid(state, sym, entry_price, s["range_pct"], s["er"], s["vol"]):
            print(f"[grid] opened {sym}  price={entry_price:.5g}  "
                  f"ER={s['er']:.2f}  vol={s['vol']:.2f}%  range={s['range_pct']:.1f}%")
            if _TG:
                send(Subsystem.BRAIN_CYCLE, Status.OK,
                     f"Grid (paper): opened on {sym}",
                     fields={
                         "Price": f"{entry_price:.5g}",
                         "Range": f"±{s['range_pct']/2:.1f}%",
                         "ER": f"{s['er']:.2f}",
                         "Vol/h": f"{s['vol']:.2f}%",
                     },
                     context="Paper grid: earns from price oscillating in range.",
                     silent=True)

    state["last_update"] = gx._now()
    gx.save_state(state)
    n = len(state["grids"])
    r = round(state.get("realized_pnl", 0.0), 2)
    print(f"[grid] done  open={n}  realized_total={r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
