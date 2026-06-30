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
SECRETS = ROOT / "scripts" / ".secrets.env"
API = "https://api.coinalyze.net/v1"

INTERVAL = sys.argv[1] if len(sys.argv) > 1 else "1hour"
FROM_ISO = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"


def load_key() -> str:
    """Key from env, falling back to the gitignored scripts/.secrets.env (for cron)."""
    k = os.environ.get("COINALYZE_API_KEY", "").strip()
    if not k and SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            if line.strip().startswith("COINALYZE_API_KEY="):
                k = line.split("=", 1)[1].strip()
                break
    return k


def _get(path: str, params: dict, key: str | None = None) -> list | dict:
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"api_key": key or load_key(),
                                               "User-Agent": "FinBuddy/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _bases() -> list[str]:
    cfg = json.loads((ROOT / "freqtrade" / "user_data" / "config.json").read_text())
    return [p.split("/")[0] for p in cfg["exchange"]["pair_whitelist"]]


def _binance_perp_map(bases: list[str]) -> dict[str, str]:
    """Map our base assets -> Coinalyze Binance USDT-perp symbol codes via /future-markets.

    Coinalyze: exchange is a 1-char code (Binance = 'A', confirmed via /exchanges); Binance
    USDT-M perps look like 'BTCUSDT_PERP.A' (quote USDT, is_perpetual, margined STABLE).
    """
    markets = _get("/future-markets", {})
    want = {b.upper() for b in bases}
    out: dict[str, str] = {}
    for m in markets:
        base = str(m.get("base_asset", "")).upper()
        if (m.get("exchange") == "A" and m.get("is_perpetual")
                and str(m.get("quote_asset", "")).upper() == "USDT"
                and str(m.get("margined", "")).upper() == "STABLE"
                and base in want):
            out.setdefault(base, m["symbol"])  # first match wins
    return out


def fetch_liq_history(cz_sym: str, interval: str, t_from: int, t_to: int) -> pd.DataFrame:
    """Reusable: liquidation history for one Coinalyze symbol -> DataFrame[date,liq_long_usd,liq_short_usd].

    Used by the historical builder (main) and the liq_capitulation paper scanner.
    """
    resp = _get("/liquidation-history", {
        "symbols": cz_sym, "interval": interval,
        "from": t_from, "to": t_to, "convert_to_usd": "true",
    })
    hist = resp[0]["history"] if resp else []
    if not hist:
        return pd.DataFrame(columns=["date", "liq_long_usd", "liq_short_usd"])
    df = pd.DataFrame(hist)
    df["date"] = pd.to_datetime(df["t"], unit="s", utc=True)
    return df.rename(columns={"l": "liq_long_usd", "s": "liq_short_usd"})[
        ["date", "liq_long_usd", "liq_short_usd"]]


def main() -> int:
    if not load_key():
        print("ERROR: COINALYZE_API_KEY not set (env or scripts/.secrets.env).", file=sys.stderr)
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
            df = fetch_liq_history(cz_sym, INTERVAL, t_from, t_to)  # convert_to_usd inside
            if df.empty:
                print(f"  {base:10s} no history")
                continue
            df["symbol"] = base + "USDT"
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
