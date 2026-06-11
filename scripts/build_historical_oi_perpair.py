#!/usr/bin/env python3
"""
Build per-pair historical Open Interest features (Phase C5, 2026-06-11).

Same source as build_historical_oi.py (Binance Data Vision daily metrics ZIPs,
5-minute resolution) but for EVERY whitelisted pair, resampled to 1h to keep
the parquet small. BTC OI z30d is already the #3 feature by importance —
per-pair OI is the highest-probability new signal family.

Output: finbuddy_memory/historical/oi_perpair.parquet  (long format)
Columns: date (UTC, 1h), symbol (e.g. ETHUSDT), oi, oi_z30d, oi_chg

Incremental: resumes per symbol from the last stored date. First full build
(26 pairs from 2024-01-01) takes hours — run via nohup. Daily cron afterward.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
OUT_FILE = ROOT / "finbuddy_memory/historical/oi_perpair.parquet"
CONFIG = ROOT / "freqtrade/user_data/config.json"
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _whitelist_symbols() -> list[str]:
    cfg = json.load(open(CONFIG))
    pairs = cfg["exchange"]["pair_whitelist"]
    return [p.replace("/", "").replace(":USDT", "") for p in pairs]


def fetch_daily_metrics(symbol: str, date_str: str) -> pd.DataFrame | None:
    url = (f"https://data.binance.vision/data/futures/um/daily/metrics/"
           f"{symbol}/{symbol}-metrics-{date_str}.zip")
    req = urllib.request.Request(url, headers={"User-Agent": "FinBuddy/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            zip_bytes = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"HTTP {e.code} {symbol} {date_str}")
        return None
    except Exception as e:
        print(f"Error {symbol} {date_str}: {e}")
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            with z.open(z.namelist()[0]) as f:
                return pd.read_csv(f, usecols=["create_time", "sum_open_interest"])
    except Exception as e:
        print(f"Parse error {symbol} {date_str}: {e}")
        return None


def build_symbol(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    frames = []
    d = start
    while d < end:
        df = fetch_daily_metrics(symbol, d.strftime("%Y-%m-%d"))
        if df is not None and not df.empty:
            frames.append(df)
        d += timedelta(days=1)
        time.sleep(0.15)  # be polite to Data Vision
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["create_time"], utc=True, format="mixed")
    hourly = (
        raw.set_index("date")["sum_open_interest"]
        .resample("1h").last().dropna().rename("oi").reset_index()
    )
    hourly["symbol"] = symbol
    return hourly


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute z30d + chg per symbol over the full stored history."""
    out = []
    for sym, g in df.groupby("symbol"):
        g = g.sort_values("date").reset_index(drop=True)
        roll = g["oi"].rolling(24 * 30, min_periods=24 * 5)
        g["oi_z30d"] = ((g["oi"] - roll.mean()) / (roll.std() + 1e-9)).fillna(0.0)
        g["oi_chg"] = g["oi"].pct_change().fillna(0.0)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def main() -> int:
    symbols = _whitelist_symbols()
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    existing = pd.DataFrame()
    if OUT_FILE.exists():
        existing = pd.read_parquet(OUT_FILE)
        existing["date"] = pd.to_datetime(existing["date"], utc=True)

    all_parts = [existing[["date", "symbol", "oi"]]] if not existing.empty else []
    for sym in symbols:
        start = START_DATE
        if not existing.empty:
            prev = existing[existing["symbol"] == sym]
            if not prev.empty:
                start = prev["date"].max().to_pydatetime() + timedelta(hours=1)
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if start >= end:
            print(f"[oi_perpair] {sym}: up to date")
            continue
        print(f"[oi_perpair] {sym}: fetching {start.date()} → {end.date()}")
        part = build_symbol(sym, start, end)
        if not part.empty:
            all_parts.append(part)
            # checkpoint after each symbol so an interrupted run resumes
            merged = (
                pd.concat(all_parts, ignore_index=True)
                .drop_duplicates(["date", "symbol"])
                .sort_values(["symbol", "date"])
            )
            add_derived(merged).to_parquet(OUT_FILE, index=False)
            print(f"[oi_perpair] {sym}: +{len(part)} rows (checkpoint saved)")

    if not all_parts:
        print("[oi_perpair] nothing fetched")
        return 1
    final = pd.read_parquet(OUT_FILE)
    print(f"[oi_perpair] done — {len(final)} rows, "
          f"{final['symbol'].nunique()} symbols, "
          f"{final['date'].min()} → {final['date'].max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
