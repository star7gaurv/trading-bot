#!/usr/bin/env python3
"""
Build per-pair perpetual funding-rate features for all whitelist pairs.

Why per-pair instead of BTC-only:
  The existing funding_rate.parquet uses BTC perp as a market-wide proxy.
  Each pair has its own funding rate dynamics: ETH at -0.02% (longs paid)
  signals very different positioning than BTC at +0.03% (longs paying).
  This script adds the pair's OWN funding rate as 3 model features, giving
  LightGBM pair-specific crowding signal — the most actionable futures
  microstructure input after market-wide funding.

Output: finbuddy_memory/historical/funding_perpair.parquet
Schema:
  date                — UTC timestamp of the funding event (every 8h)
  symbol              — Binance symbol (e.g. "ETHUSDT")
  funding_rate        — raw rate per 8h
  funding_rate_z30d   — z-score vs 30d rolling per-symbol (extremeness)
  funding_rate_chg    — change vs previous event per-symbol (momentum)

Incremental: on subsequent runs, only fetches events since the latest
date already stored — completes in <30s after the initial backfill.

Cron: daily at 01:30 UTC (after BTC funding refresh at 01:25 UTC).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT       = Path("/home/ubuntu/var/www/html/trade")
OUT_FILE   = ROOT / "finbuddy_memory/historical/funding_perpair.parquet"
CONFIG_FILE = ROOT / "freqtrade/user_data/config.json"
BASE_URL   = "https://fapi.binance.com/fapi/v1/fundingRate"
PAGE_SZ    = 1000
# Safe lower bound: before any pair listed on Binance Futures
FALLBACK_START_MS = 1568000000000  # 2019-09-09


def _ft_pair_to_binance(pair: str) -> str:
    """'ETH/USDT:USDT' → 'ETHUSDT'  |  '1000PEPE/USDT:USDT' → '1000PEPEUSDT'"""
    return pair.replace("/", "").replace(":USDT", "")


def _load_pairs() -> list[str]:
    """Return Binance symbols for all whitelist pairs in config.json."""
    cfg = json.loads(CONFIG_FILE.read_text())
    return [_ft_pair_to_binance(p) for p in cfg["exchange"]["pair_whitelist"]]


def _fetch_symbol(symbol: str, start_ms: int) -> pd.DataFrame:
    """Fetch all funding events for one symbol from start_ms onward."""
    rows: list[dict] = []
    cursor = start_ms
    while True:
        qs  = f"?symbol={symbol}&startTime={cursor}&limit={PAGE_SZ}"
        req = urllib.request.Request(BASE_URL + qs, headers={"User-Agent": "FinBuddy/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                page = json.loads(r.read())
        except Exception as exc:
            print(f"  [{symbol}] fetch error: {exc} — skipping page", file=sys.stderr)
            break
        if not page:
            break
        rows.extend(page)
        last_ms = int(page[-1]["fundingTime"])
        if len(page) < PAGE_SZ:
            break
        cursor = last_ms + 1
        time.sleep(0.15)  # polite to public endpoint
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "date":         pd.to_datetime(int(r["fundingTime"]), unit="ms", utc=True),
        "symbol":       symbol,
        "funding_rate": float(r["fundingRate"]),
    } for r in rows])
    return df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Add z30d and chg per symbol (rolling computed independently per pair)."""
    LOOK = 90   # 30d at 3 events/day
    out_parts = []
    for symbol, grp in df.groupby("symbol", sort=False):
        grp = grp.sort_values("date").copy()
        rolling  = grp["funding_rate"].rolling(LOOK, min_periods=10)
        mu       = rolling.mean()
        sig      = rolling.std().replace(0, 1e-9)
        grp["funding_rate_z30d"] = ((grp["funding_rate"] - mu) / sig).fillna(0.0)
        grp["funding_rate_chg"]  = grp["funding_rate"].diff().fillna(0.0)
        out_parts.append(grp)
    return pd.concat(out_parts, ignore_index=True)


def main() -> int:
    symbols = _load_pairs()
    print(f"Per-pair funding rate builder — {len(symbols)} pairs → {OUT_FILE}")

    # Load existing parquet to determine incremental start per symbol
    existing: pd.DataFrame | None = None
    latest_by_symbol: dict[str, int] = {}
    if OUT_FILE.exists():
        try:
            existing = pd.read_parquet(OUT_FILE)
            existing["date"] = pd.to_datetime(existing["date"], utc=True)
            for sym, grp in existing.groupby("symbol"):
                latest_by_symbol[sym] = int(grp["date"].max().timestamp() * 1000) + 1
            print(f"  Existing: {len(existing)} rows, {len(latest_by_symbol)} symbols covered")
        except Exception as e:
            print(f"  Could not load existing parquet ({e}) — full backfill")
            existing = None

    new_parts: list[pd.DataFrame] = []
    for i, symbol in enumerate(symbols):
        start_ms = latest_by_symbol.get(symbol, FALLBACK_START_MS)
        mode     = "incr" if symbol in latest_by_symbol else "full"
        print(f"  [{i+1:2d}/{len(symbols)}] {symbol:16s} {mode} from "
              f"{pd.to_datetime(start_ms, unit='ms', utc=True).date()} ...", end=" ", flush=True)
        df = _fetch_symbol(symbol, start_ms)
        if df.empty:
            print("0 new rows")
            continue
        print(f"{len(df)} rows, latest={df['date'].max().date()}")
        new_parts.append(df)

    if not new_parts and existing is not None:
        print("Nothing new to append — parquet is up to date.")
        return 0

    new_df = pd.concat(new_parts, ignore_index=True) if new_parts else pd.DataFrame()

    # Merge with existing, re-derive rolling features on full history per symbol
    if existing is not None and not new_df.empty:
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date", "symbol"]).sort_values(
            ["symbol", "date"]).reset_index(drop=True)
    elif existing is not None:
        combined = existing.sort_values(["symbol", "date"]).reset_index(drop=True)
    else:
        combined = new_df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # Strip old derived cols before recomputing so they reflect new data
    for col in ("funding_rate_z30d", "funding_rate_chg"):
        if col in combined.columns:
            combined = combined.drop(columns=[col])

    combined = _add_derived(combined)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUT_FILE, index=False)

    n_sym = combined["symbol"].nunique()
    print(
        f"\nWrote {len(combined)} rows across {n_sym} symbols  "
        f"range: {combined['date'].min().date()} → {combined['date'].max().date()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
