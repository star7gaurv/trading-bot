#!/usr/bin/env python3
"""
Build historical regime data per BTC 4h candle.

Computes regime (CRASH/BEAR/NEUTRAL/BULL/EUPHORIA) for every BTC 4h candle
since 2023-09-01 using deterministic rolling-stats rules. Output is a parquet
file the v23 strategy loads at backtest start so dynamic thresholds reflect
the HISTORICAL regime at each candle, not stale live state.

Rules (mirror finbuddy_memory/regimes/current.json semantics):
  CRASH    — 7d drawdown < -15% OR 30d return < -25%
  BEAR     — 30d return < -10% AND close < 90d SMA
  EUPHORIA — 30d return > +30% AND close > 90d SMA × 1.20
  BULL     — 30d return > +10% AND close > 90d SMA
  NEUTRAL  — anything else

Output: finbuddy_memory/regimes/historical_regime.parquet
Columns: date (UTC), regime (str), regime_numeric (-2..+2), confidence (float)
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path("/home/ubuntu/var/www/html/trade")
BTC_4H_FEATHER = ROOT / "freqtrade/user_data/data/binance/futures/BTC_USDT_USDT-4h-futures.feather"
OUTPUT_PARQUET = ROOT / "finbuddy_memory/regimes/historical_regime.parquet"

REGIME_NUMERIC = {"CRASH": -2, "BEAR": -1, "NEUTRAL": 0, "BULL": 1, "EUPHORIA": 2}


def classify_row(close: float, ret_30d: float, drawdown_7d: float, sma_90d: float) -> tuple[str, float]:
    """Classify single candle. Returns (regime, confidence)."""
    if pd.isna(ret_30d) or pd.isna(drawdown_7d) or pd.isna(sma_90d):
        return ("NEUTRAL", 0.5)

    # CRASH — sharp recent move down or deep multi-week loss
    if drawdown_7d < -0.15 or ret_30d < -0.25:
        return ("CRASH", 0.95)
    # EUPHORIA — strong multi-week up AND price stretched above its 90d trend
    if ret_30d > 0.30 and close > sma_90d * 1.20:
        return ("EUPHORIA", 0.90)
    # BEAR — multi-week down AND below 90d trend
    if ret_30d < -0.10 and close < sma_90d:
        return ("BEAR", 0.80)
    # BULL — multi-week up AND above 90d trend
    if ret_30d > 0.10 and close > sma_90d:
        return ("BULL", 0.85)
    # NEUTRAL — mixed
    return ("NEUTRAL", 0.70)


def main() -> int:
    if not BTC_4H_FEATHER.exists():
        print(f"ERROR: BTC 4h feather not found at {BTC_4H_FEATHER}", file=sys.stderr)
        return 1

    df = pd.read_feather(BTC_4H_FEATHER)
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Loaded {len(df)} BTC 4h candles: {df['date'].min()} → {df['date'].max()}")

    # Rolling stats: 30d = 30*6 = 180 4h candles; 90d = 540; 7d = 42
    candles_per_day = 6  # 4h × 6 = 24h
    df["sma_90d"]      = df["close"].rolling(90 * candles_per_day).mean()
    df["high_7d"]      = df["high"].rolling(7  * candles_per_day).max()
    df["close_30d_ago"]= df["close"].shift(30 * candles_per_day)

    df["ret_30d"]      = (df["close"] / df["close_30d_ago"]) - 1.0
    df["drawdown_7d"]  = (df["close"] / df["high_7d"]) - 1.0

    regimes  = []
    confidences = []
    for _, row in df.iterrows():
        r, c = classify_row(row["close"], row["ret_30d"], row["drawdown_7d"], row["sma_90d"])
        regimes.append(r)
        confidences.append(c)

    out = pd.DataFrame({
        "date":           df["date"].dt.tz_convert("UTC") if df["date"].dt.tz else df["date"].dt.tz_localize("UTC"),
        "regime":         regimes,
        "regime_numeric": [REGIME_NUMERIC[r] for r in regimes],
        "confidence":     confidences,
    })

    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTPUT_PARQUET, index=False)

    # Summary
    counts = pd.Series(regimes).value_counts()
    pct = (counts / len(regimes) * 100).round(1)
    print(f"\nRegime distribution across {len(regimes)} candles:")
    for r, n in counts.items():
        print(f"  {r:9s}: {n:5d}  ({pct[r]}%)")

    print(f"\nWritten to: {OUTPUT_PARQUET}")
    print(f"First non-neutral regime starts: {out[out['regime'] != 'NEUTRAL']['date'].iloc[0] if (out['regime'] != 'NEUTRAL').any() else 'never'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
