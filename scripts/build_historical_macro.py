#!/usr/bin/env python3
"""
Build historical macro features per day for backtest use.

Fetches:
  - Fear & Greed Index from alternative.me (free, daily, since 2018)
  - Proxy "BTC strength" from BTC/USDT 1d returns vs ETH/USDT 1d returns
    (substitute for BTC dominance, which requires paid CoinGecko historical)

Output: finbuddy_memory/historical/macro_features.parquet
Columns: date (UTC, daily), fear_greed (0-100), btc_strength (-1 to +1 ish)

The v23 strategy reads this at backtest start and merges per-candle in
feature_engineering_standard, replacing the constant-value VarianceThreshold-dropped
fear_greed/btc_dominance features.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
BTC_1D = ROOT / "freqtrade/user_data/data/binance/futures/BTC_USDT_USDT-1d-futures.feather"
ETH_1D = ROOT / "freqtrade/user_data/data/binance/futures/ETH_USDT_USDT-1d-futures.feather"
OUT = ROOT / "finbuddy_memory/historical/macro_features.parquet"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"  # all-history


def fetch_fng() -> pd.DataFrame:
    """Fetch full Fear & Greed history from alternative.me."""
    print(f"Fetching Fear & Greed history from {FNG_URL}")
    req = urllib.request.Request(FNG_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    rows = data.get("data", [])
    print(f"Got {len(rows)} F&G data points")
    df = pd.DataFrame([{
        "date": pd.to_datetime(int(d["timestamp"]), unit="s", utc=True),
        "fear_greed": int(d["value"]),
    } for d in rows])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def compute_btc_strength() -> pd.DataFrame:
    """
    Proxy for BTC dominance: BTC 7d return − ETH 7d return.
    Positive = BTC outperforming ETH (dom rising); negative = alt season.
    Normalized to roughly [-0.2, +0.2].
    """
    btc = pd.read_feather(BTC_1D)[["date", "close"]].rename(columns={"close": "btc_close"})
    eth = pd.read_feather(ETH_1D)[["date", "close"]].rename(columns={"close": "eth_close"})

    btc["date"] = pd.to_datetime(btc["date"], utc=True)
    eth["date"] = pd.to_datetime(eth["date"], utc=True)
    df = pd.merge(btc, eth, on="date", how="inner").sort_values("date").reset_index(drop=True)

    df["btc_ret_7d"] = df["btc_close"].pct_change(7)
    df["eth_ret_7d"] = df["eth_close"].pct_change(7)
    df["btc_strength"] = (df["btc_ret_7d"] - df["eth_ret_7d"]).clip(lower=-0.30, upper=0.30)
    return df[["date", "btc_strength"]]


def main() -> int:
    if not BTC_1D.exists() or not ETH_1D.exists():
        print(f"ERROR: missing 1d feather files", file=sys.stderr)
        return 1

    fng = fetch_fng()
    bts = compute_btc_strength()

    # Daily-grain merge — F&G is daily, btc_strength is daily.
    # Both indexed by UTC midnight (or close to it). Normalize to date.
    fng["date_d"] = fng["date"].dt.floor("D")
    bts["date_d"] = bts["date"].dt.floor("D")

    merged = pd.merge(
        fng[["date_d", "fear_greed"]],
        bts[["date_d", "btc_strength"]],
        on="date_d", how="outer"
    ).sort_values("date_d").reset_index(drop=True)
    merged = merged.rename(columns={"date_d": "date"})

    # Forward-fill any gaps so every date has values
    merged["fear_greed"] = merged["fear_greed"].ffill().bfill()
    merged["btc_strength"] = merged["btc_strength"].ffill().fillna(0.0)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT, index=False)

    print(f"\nWritten {len(merged)} rows to {OUT}")
    print(f"Date range: {merged['date'].min()} → {merged['date'].max()}")
    print(f"F&G stats: min={merged['fear_greed'].min()} max={merged['fear_greed'].max()} mean={merged['fear_greed'].mean():.1f}")
    print(f"BTC strength stats: min={merged['btc_strength'].min():.3f} max={merged['btc_strength'].max():.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
