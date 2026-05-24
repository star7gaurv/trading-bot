#!/usr/bin/env python3
"""
Build historical BTC Open Interest (OI) macro feature for backtest use.

Fetches the daily 'metrics' ZIP archives from Binance Data Vision for BTCUSDT,
which contain 5-minute resolution Open Interest and Long/Short ratio.
We use BTC OI as a global macro proxy for crypto market leverage.

Output: finbuddy_memory/historical/open_interest.parquet
Columns:
  date              — UTC timestamp
  btc_oi            — Raw BTC open interest (coin amount)
  btc_ls_ratio      — Global Long/Short ratio
  btc_oi_z30d       — Z-score vs trailing 30-day mean+std
  btc_oi_chg        — OI change vs previous 5m period
"""
from __future__ import annotations

import io
import sys
import time
import zipfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT     = Path("/home/ubuntu/var/www/html/trade")
OUT_FILE = ROOT / "finbuddy_memory/historical/open_interest.parquet"
SYMBOL   = "BTCUSDT"

# Start from 2023-09-01 to give a 3-month warmup buffer before the 2024-01-01 backtest start
START_DATE = datetime(2023, 9, 1, tzinfo=timezone.utc)

def fetch_daily_metrics(date_str: str) -> pd.DataFrame | None:
    """Download and extract the daily metrics CSV for the given YYYY-MM-DD."""
    url = f"https://data.binance.vision/data/futures/um/daily/metrics/{SYMBOL}/{SYMBOL}-metrics-{date_str}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "FinBuddy/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            zip_bytes = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # Missing data for this day (expected for today if incomplete)
        print(f"HTTP {e.code} for {date_str}: {url}")
        return None
    except Exception as e:
        print(f"Error fetching {date_str}: {e}")
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                # Binance columns: create_time, symbol, sum_open_interest, sum_open_interest_value, ...
                df = pd.read_csv(f, usecols=["create_time", "sum_open_interest", "count_long_short_ratio"])
                return df
    except Exception as e:
        print(f"Error parsing ZIP for {date_str}: {e}")
        return None

def build_all() -> pd.DataFrame:
    """Iterate through all days and build the full dataset."""
    dfs = []
    current_date = START_DATE
    end_date = datetime.now(timezone.utc)
    
    print(f"Fetching daily Open Interest metrics from {START_DATE.date()} to {end_date.date()}...")
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        df = fetch_daily_metrics(date_str)
        if df is not None and not df.empty:
            dfs.append(df)
            sys.stdout.write(f"\rFetched {date_str} ({(len(dfs))} files)")
            sys.stdout.flush()
        else:
            # Not an error if it's today's date, the zip might not be published yet
            if current_date.date() < end_date.date():
                sys.stdout.write(f"\rMissing {date_str}                 ")
                sys.stdout.flush()
        current_date += timedelta(days=1)
        time.sleep(0.1)  # Be polite
        
    print("\nProcessing raw data...")
    if not dfs:
        return pd.DataFrame()
        
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Rename and type cast
    full_df = full_df.rename(columns={
        "create_time": "date",
        "sum_open_interest": "btc_oi",
        "count_long_short_ratio": "btc_ls_ratio"
    })
    full_df["date"] = pd.to_datetime(full_df["date"], utc=True)
    
    # Clean and sort
    full_df = full_df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    
    return full_df

def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add z-score (30d rolling) and 1-step change."""
    # Data is 5-minute resolution. 30 days = 30 * 24 * 12 = 8640 rows.
    LOOKBACK = 8640
    
    rolling = df["btc_oi"].rolling(LOOKBACK, min_periods=288)  # Require at least 1 day
    mu  = rolling.mean()
    sig = rolling.std().replace(0, 1e-9)
    
    df["btc_oi_z30d"] = ((df["btc_oi"] - mu) / sig).fillna(0.0)
    df["btc_oi_chg"]  = df["btc_oi"].diff().fillna(0.0)
    
    return df

def main() -> int:
    df = build_all()
    if df.empty:
        print("ERROR: No data collected.", file=sys.stderr)
        return 1
        
    df = add_derived_features(df)
    
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    
    print(
        f"Wrote {len(df)} rows. Range: {df['date'].min()} → {df['date'].max()}\n"
        f"Latest OI: {df['btc_oi'].iloc[-1]:.1f} BTC  "
        f"Z-Score: {df['btc_oi_z30d'].iloc[-1]:+.2f}  "
        f"L/S Ratio: {df['btc_ls_ratio'].iloc[-1]:.2f}"
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
