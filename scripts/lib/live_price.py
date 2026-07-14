"""live_price.py — shared live-price resolver for the paper-trading modules.

Added 2026-07-14. grid/pairs/liq_capitulation all read "current price" from the
same local 1h feathers, refreshed only once daily by download_data_daily.sh —
confirmed 4+ hours stale. liq_capitulation's 7h time-stop made this a real bug
(entry and exit could read the identical stale price, faking 0%-move closes).
grid/pairs hold positions for days so the effect is subtler (undercounted grid
crossings, delayed pair z-score reactions) but the same root cause applies.

Use get_live_price() for the CURRENT price used in threshold/crossing/exit
checks. Historical windowed stats (volatility, ER, half-life, beta) can still
read the feather directly — those need a genuine multi-day series, and the
feather's older rows are accurate; only the tail end goes stale.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/binance/futures")
FEATHER_STALE_H = 2.0   # max feather age to trust as a fallback


def get_live_price(base: str) -> float:
    """Live Binance futures ticker price for `base` (e.g. "OP", "BTC").

    Falls back to the local 1h feather only if its last candle is fresh enough
    to trust; otherwise returns 0.0 so callers can skip rather than act on
    unreliable data.
    """
    try:
        req = urllib.request.Request(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={base}USDT",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        return float(data["price"])
    except Exception as e:
        print(f"[live_price] live fetch failed for {base}: {type(e).__name__}: {e}", file=sys.stderr)

    f = DATA_DIR / f"{base}_USDT_USDT-1h-futures.feather"
    if not f.exists():
        return 0.0
    try:
        df = pd.read_feather(f)
        last_ts = df["date"].iloc[-1]
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
            last_ts = last_ts.tz_localize("UTC")
        age_h = (datetime.now(timezone.utc) - last_ts.to_pydatetime()).total_seconds() / 3600
        if age_h > FEATHER_STALE_H:
            print(f"[live_price] feather for {base} is {age_h:.1f}h stale "
                  f"(>{FEATHER_STALE_H}h) — skipping rather than trading on it", file=sys.stderr)
            return 0.0
        return float(df["close"].iloc[-1])
    except Exception:
        return 0.0
