#!/usr/bin/env python3
"""
liq_capitulation/scanner.py — hourly paper manager for the liquidation-bounce module.

Each run:
  1. Refresh current price for every open position; exit on TP / stop / 6h time-stop.
  2. Compute live liq_long_z per whitelist pair (Coinalyze recent history, 1-week z-window).
  3. Open a paper LONG where 2.0 <= liq_long_z <= 3.0 (capitulation, skip the >3 knife-catch tail).

Signal source: scripts/brain/fetch_liquidations.py helpers (Coinalyze REST). Price: 1h feathers
(same as the grid/pairs modules). PAPER MODE ONLY. Cron: hourly at :50.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/liq_capitulation"))
sys.path.insert(0, str(ROOT / "scripts/brain"))
import paper_executor as lx       # noqa: E402
import fetch_liquidations as fl   # noqa: E402

try:
    from lib.telegram_template import Subsystem, Status, send  # noqa: E402
    _TG = True
except Exception:
    _TG = False

CONFIG = ROOT / "freqtrade/user_data/config.json"
DATA_DIR = ROOT / "freqtrade/user_data/data/binance/futures"
MAP_CACHE = ROOT / "finbuddy_memory/liq_capitulation/symbol_map.json"

ZWIN = 168                  # 1-week rolling z window (matches liquidation_ic.py)
Z_OPEN_MIN = 2.0            # capitulation floor
Z_OPEN_MAX = 3.0            # skip the extreme knife-catch tail (z>3 reverses)
LOOKBACK_DAYS = 12          # enough history for the z window + buffer


def whitelist_bases() -> list[str]:
    return [p.split("/")[0] for p in json.load(open(CONFIG))["exchange"]["pair_whitelist"]]


def symbol_map(bases: list[str]) -> dict[str, str]:
    """Cached base->Coinalyze symbol map; refresh if missing or >1 day old."""
    if MAP_CACHE.exists():
        age = time.time() - MAP_CACHE.stat().st_mtime
        if age < 86400:
            return json.loads(MAP_CACHE.read_text())
    m = fl._binance_perp_map(bases)
    MAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MAP_CACHE.write_text(json.dumps(m, indent=2))
    return m


def latest_liq_z(cz_sym: str, t_from: int, t_to: int) -> tuple[float, float] | None:
    """(liq_long_z, liq_long_usd) on the latest COMPLETE hourly bucket, or None."""
    df = fl.fetch_liq_history(cz_sym, "1hour", t_from, t_to)
    if df.empty or len(df) < 24:
        return None
    df = df.sort_values("date")
    # drop the current (partial) hour
    cur_hour = pd.Timestamp.now(tz="UTC").floor("h")
    df = df[df["date"] < cur_hour]
    if len(df) < 24:
        return None
    ln = np.log1p(df["liq_long_usd"])
    z = (ln - ln.rolling(ZWIN, min_periods=24).mean()) / ln.rolling(ZWIN, min_periods=24).std()
    zv = z.iloc[-1]
    if pd.isna(zv):
        return None
    return float(zv), float(df["liq_long_usd"].iloc[-1])


def price_for(base: str) -> float:
    f = DATA_DIR / f"{base}_USDT_USDT-1h-futures.feather"
    if not f.exists():
        return 0.0
    try:
        return float(pd.read_feather(f)["close"].iloc[-1])
    except Exception:
        return 0.0


def main() -> int:
    if not fl.load_key():
        print("[liq_cap] no COINALYZE_API_KEY (env or scripts/.secrets.env)")
        return 0
    bases = whitelist_bases()
    smap = symbol_map(bases)
    state = lx.load_state()
    now = datetime.now(timezone.utc)
    t_to = int(now.timestamp())
    t_from = int((now - timedelta(days=LOOKBACK_DAYS)).timestamp())

    # 1) manage open positions
    for sym in list(state["positions"].keys()):
        pos = state["positions"][sym]
        base = sym.replace("USDT", "")
        price = price_for(base)
        if price <= 0:
            continue
        held = (now - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600
        reason = lx.check_exit(pos, price, held)
        if reason:
            net = lx.close_position(state, sym, price, reason)
            print(f"[liq_cap] closed {sym} — {reason}  net={net:+.3f}")
            if _TG:
                send(Subsystem.BRAIN_CYCLE, Status.INFO, f"Liq-bounce (paper): closed {sym}",
                     fields={"Reason": reason, "Net P&L": f"{net:+.3f} USDT"}, silent=True)

    # 2) scan for capitulation entries
    if len(state["positions"]) < lx.MAX_POSITIONS:
        cands = []
        for base in bases:
            cz = smap.get(base)
            if not cz or (base + "USDT") in state["positions"]:
                continue
            try:
                res = latest_liq_z(cz, t_from, t_to)
            except Exception as e:
                print(f"[liq_cap] {base} liq fetch failed: {type(e).__name__}: {e}")
                res = None
            if res is None:
                continue
            z, liq_usd = res
            if Z_OPEN_MIN <= z <= Z_OPEN_MAX:
                cands.append((base, z, liq_usd))
            time.sleep(0.25)  # stay under 40 req/min
        cands.sort(key=lambda x: x[1], reverse=True)  # strongest capitulation first

        for base, z, liq_usd in cands:
            if len(state["positions"]) >= lx.MAX_POSITIONS:
                break
            price = price_for(base)
            if lx.open_position(state, base + "USDT", price, z, liq_usd):
                print(f"[liq_cap] opened {base}USDT  price={price:.5g}  liq_long_z={z:.2f}  "
                      f"liq_long=${liq_usd:,.0f}")
                if _TG:
                    send(Subsystem.BRAIN_CYCLE, Status.OK, f"Liq-bounce (paper): long {base}",
                         fields={"Price": f"{price:.5g}", "liq_long_z": f"{z:.2f}",
                                 "Long liq": f"${liq_usd:,.0f}"},
                         context="Paper: contrarian bounce after a long-liquidation capitulation.",
                         silent=True)

    state["last_update"] = lx._now()
    lx.save_state(state)
    w, l = state.get("wins", 0), state.get("losses", 0)
    print(f"[liq_cap] done  open={len(state['positions'])}  "
          f"realized={round(state.get('realized_pnl', 0.0), 2)}  W/L={w}/{l}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
