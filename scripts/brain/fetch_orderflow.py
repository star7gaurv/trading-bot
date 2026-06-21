#!/usr/bin/env python3
"""fetch_orderflow.py — Phase 4b.5: pull 15m klines WITH taker-buy volume from Binance futures.

FreqTrade's stored feathers drop the taker-buy-volume column; this fetches it directly so we can
build order-flow features (CVD / taker imbalance) and run them through the same IC gate. Saves
per-symbol parquet (date, volume, taker_buy_base) to finbuddy_memory/historical/orderflow/.

Usage: python3 scripts/brain/fetch_orderflow.py
"""
import time, json, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "finbuddy_memory" / "historical" / "orderflow"
BASE = "https://fapi.binance.com/fapi/v1/klines"

# Genuine windows (same as feature_ic.py) — fetch the union span per symbol.
SPAN = ("2024-01-01", "2026-04-01")
# Liquid large+mid-cap subset (≥10 pairs gives ample pooled samples for the IC gate).
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOTUSDT", "AVAXUSDT",
           "LINKUSDT", "APTUSDT", "ARBUSDT", "FETUSDT", "ADAUSDT", "LTCUSDT"]


def fetch(symbol: str) -> pd.DataFrame:
    start = int(pd.Timestamp(SPAN[0], tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp(SPAN[1], tz="UTC").timestamp() * 1000)
    rows = []
    while start < end:
        url = f"{BASE}?symbol={symbol}&interval=15m&startTime={start}&endTime={end}&limit=1500"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        if not data:
            break
        rows += data
        last = data[-1][0]
        if last <= start:
            break
        start = last + 1
        time.sleep(0.25)  # polite
    df = pd.DataFrame(rows, columns=["openTime", "o", "h", "l", "c", "vol", "closeTime",
                                     "qvol", "n", "taker_buy_base", "taker_buy_quote", "ig"])
    df["date"] = pd.to_datetime(df["openTime"], unit="ms", utc=True)
    df["volume"] = df["vol"].astype(float)
    df["taker_buy_base"] = df["taker_buy_base"].astype(float)
    return df[["date", "volume", "taker_buy_base"]].drop_duplicates("date").reset_index(drop=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for sym in SYMBOLS:
        try:
            df = fetch(sym)
            df.to_parquet(OUT / f"{sym}.parquet")
            print(f"  {sym:10s} {len(df):6d} candles  {df['date'].min().date()} → {df['date'].max().date()}")
        except Exception as e:
            print(f"  {sym:10s} FAILED: {e}")
    print(f"→ saved to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
