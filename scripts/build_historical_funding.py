#!/usr/bin/env python3
"""
Build historical BTC perpetual funding rate features for backtest use.

Fetches the full BTC/USDT funding-rate history from Binance Futures
(/fapi/v1/fundingRate) — public endpoint, no auth, free.

Funding events happen every 8h (00:00, 08:00, 16:00 UTC). The output parquet
contains every event since 2019-09 (Binance Futures launch). Strategy reads
this at backtest start and merges per-candle via merge_asof (backward).

Why funding rate as a model feature:
  - Strongest published correlation with 1–4h crypto perp price moves of any
    cheap signal. High positive funding → longs overcrowded → mean-reversion
    pressure. High negative funding → shorts overcrowded → squeeze risk.
  - Already used as a trade-time GATE in CortexaAI_v23 (block longs when
    funding > 0.05% / 8h). Adding it as a model FEATURE lets LightGBM learn
    nonlinear interactions (e.g. funding × momentum × regime).

Output: finbuddy_memory/historical/funding_rate.parquet
Columns:
  date                — UTC timestamp of the funding event
  funding_rate        — raw % per 8h (e.g. 0.0001 = 0.01%)
  funding_rate_z30d   — z-score vs trailing 30-day mean+std (extremeness)
  funding_rate_chg    — change vs previous event (momentum of funding)

Run manually after install, then daily via cron (refresh keeps it from going
stale; gap > 3d triggers a warning in the strategy).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT     = Path("/home/ubuntu/var/www/html/trade")
OUT_FILE = ROOT / "finbuddy_memory/historical/funding_rate.parquet"
SYMBOL   = "BTCUSDT"
URL      = "https://fapi.binance.com/fapi/v1/fundingRate"
PAGE_SZ  = 1000          # Binance hard max
START_MS = 1568000000000  # 2019-09-09 — before Binance Futures launched, safe lower bound


def fetch_page(start_ms: int) -> list[dict]:
    """Fetch up to 1000 funding events from start_ms (inclusive)."""
    qs = f"?symbol={SYMBOL}&startTime={start_ms}&limit={PAGE_SZ}"
    req = urllib.request.Request(URL + qs, headers={"User-Agent": "Cortexa/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_all() -> pd.DataFrame:
    """Paginate through full history. Each event is 8h; 1000 events = ~333 days."""
    all_rows: list[dict] = []
    cursor = START_MS
    page = 0
    while True:
        page += 1
        rows = fetch_page(cursor)
        if not rows:
            break
        all_rows.extend(rows)
        last_ms = int(rows[-1]["fundingTime"])
        print(f"  page {page}: {len(rows)} events, latest={pd.to_datetime(last_ms, unit='ms', utc=True)}")
        if len(rows) < PAGE_SZ:
            break
        cursor = last_ms + 1  # skip duplicate of last event
        time.sleep(0.25)      # be polite to public endpoint
    print(f"Got {len(all_rows)} funding events for {SYMBOL}")
    df = pd.DataFrame([{
        "date":         pd.to_datetime(int(r["fundingTime"]), unit="ms", utc=True),
        "funding_rate": float(r["fundingRate"]),
    } for r in all_rows])
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Add z-score (30d rolling) and 1-step change as derived features."""
    # 30d at 3 events/day = 90 lookback
    LOOK = 90
    rolling = df["funding_rate"].rolling(LOOK, min_periods=10)
    mu  = rolling.mean()
    sig = rolling.std().replace(0, 1e-9)
    df["funding_rate_z30d"] = ((df["funding_rate"] - mu) / sig).fillna(0.0)
    df["funding_rate_chg"]  = df["funding_rate"].diff().fillna(0.0)
    return df


def main() -> int:
    print(f"Building historical funding-rate feature → {OUT_FILE}")
    df = fetch_all()
    if df.empty:
        print("ERROR: no data returned", file=sys.stderr)
        return 1
    df = add_derived(df)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    print(
        f"Wrote {len(df)} rows  range: {df['date'].min()} → {df['date'].max()}  "
        f"latest_rate={df['funding_rate'].iloc[-1]:.5f}  "
        f"latest_z={df['funding_rate_z30d'].iloc[-1]:+.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
