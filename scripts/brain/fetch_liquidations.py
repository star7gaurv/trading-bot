#!/usr/bin/env python3
"""fetch_liquidations.py — Phase 4c: historical futures LIQUIDATIONS via Coinalyze REST.

WHY: market-wide futures liquidations are the one untested order-flow signal with real
edge potential (forced flow -> multi-hour dislocations, not latency-bound). Binance only
exposes them on the !forceOrder websocket, which is BLOCKED from this server's IP (the
futures WS delivers zero frames here; spot WS + futures REST both work). Coinalyze serves
HISTORICAL liquidation aggregates over REST, so we can backtest the signal immediately
(IC-test like funding/OI) instead of waiting weeks for a forward feed.

Key: reads COINALYZE_API_KEY from the environment (never committed). Free tier, ~40 req/min.
Output: finbuddy_memory/historical/liquidations_perpair.parquet
        columns [date, symbol, liq_long_usd, liq_short_usd]  (symbol = <BASE>USDT, 1h buckets)
        'liq_long_usd' = longs force-closed (forced sells); 'liq_short_usd' = shorts force-closed.

Usage: COINALYZE_API_KEY=... python3 scripts/brain/fetch_liquidations.py [interval] [from_iso]
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "finbuddy_memory" / "historical" / "liquidations_perpair.parquet"
API = "https://api.coinalyze.net/v1"
KEY = os.environ.get("COINALYZE_API_KEY", "").strip()

INTERVAL = sys.argv[1] if len(sys.argv) > 1 else "1hour"
FROM_ISO = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"


def _get(path: str, params: dict) -> list | dict:
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"api_key": KEY, "User-Agent": "FinBuddy/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _bases() -> list[str]:
    cfg = json.loads((ROOT / "freqtrade" / "user_data" / "config.json").read_text())
    return [p.split("/")[0] for p in cfg["exchange"]["pair_whitelist"]]


def _binance_perp_map(bases: list[str]) -> dict[str, str]:
    """Map our base assets -> Coinalyze Binance USDT-perp symbol codes via /future-markets."""
    markets = _get("/future-markets", {})
    want = {b.upper() for b in bases}
    out: dict[str, str] = {}
    for m in markets:
        exch = str(m.get("exchange", "")).lower()
        base = str(m.get("base_asset", "")).upper()
        quote = str(m.get("quote_asset", "")).upper()
        if "binance" in exch and m.get("is_perpetual") and quote == "USDT" and base in want:
            out.setdefault(base, m["symbol"])  # first match wins
    return out


def main() -> int:
    if not KEY:
        print("ERROR: COINALYZE_API_KEY not set in environment.", file=sys.stderr)
        return 2
    bases = _bases()
    try:
        sym_map = _binance_perp_map(bases)
    except Exception as e:
        print(f"ERROR querying future-markets: {e}", file=sys.stderr)
        return 1
    missing = [b for b in bases if b.upper() not in sym_map]
    print(f"mapped {len(sym_map)}/{len(bases)} pairs"
          + (f"; no Binance-perp match for: {missing}" if missing else ""))

    t_from = int(pd.Timestamp(FROM_ISO, tz="UTC").timestamp())
    t_to = int(pd.Timestamp.now(tz="UTC").timestamp())
    frames = []
    for base, cz_sym in sym_map.items():
        try:
            # convert_to_usd so long/short liq are comparable across pairs
            resp = _get("/liquidation-history", {
                "symbols": cz_sym, "interval": INTERVAL,
                "from": t_from, "to": t_to, "convert_to_usd": "true",
            })
            hist = resp[0]["history"] if resp else []
            if not hist:
                print(f"  {base:10s} no history")
                continue
            df = pd.DataFrame(hist)  # columns: t (unix s), l (long liq), s (short liq)
            df["date"] = pd.to_datetime(df["t"], unit="s", utc=True)
            df["symbol"] = base + "USDT"
            df = df.rename(columns={"l": "liq_long_usd", "s": "liq_short_usd"})
            frames.append(df[["date", "symbol", "liq_long_usd", "liq_short_usd"]])
            print(f"  {base:10s} {len(df):6d} buckets  {df['date'].min().date()} → {df['date'].max().date()}")
            time.sleep(0.3)  # stay under 40 req/min
        except Exception as e:
            print(f"  {base:10s} FAILED: {type(e).__name__}: {e}")
    if not frames:
        print("no data fetched", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"])
    out.to_parquet(OUT)
    print(f"→ saved {len(out)} rows, {out['symbol'].nunique()} symbols to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
