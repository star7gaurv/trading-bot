#!/usr/bin/env python3
"""
regime_core.py — single source of truth for regime classification (E3, 2026-06-11).

Both regime entry points import from here:
  - scripts/build_historical_regime.py  (per-candle parquet for backtests)
  - freqtrade/user_data/scripts/hmm_regime_detector.py  (live current.json)

Before this module the two used UNRELATED inputs (price action vs fear/greed
sentiment) and routinely disagreed — e.g. 2026-06-07/08: parquet said
BEAR/CRASH while current.json said NEUTRAL, deadlocking all entries. Price
action wins: it is computable on any historical candle, so live == backtest.

Also provides trend-horizon detection (CLAUDE.md "detecting trend time"):
a 0-3 score of how long the prevailing trend has been in force, exposed to
the model as %-trend_horizon.
"""
from __future__ import annotations

import pandas as pd

REGIME_NUMERIC = {"CRASH": -2, "BEAR": -1, "NEUTRAL": 0, "BULL": 1, "EUPHORIA": 2}

# BTC 4h candles per period
_CANDLES_PER_DAY = 6


def classify_row(close: float, ret_30d: float, drawdown_7d: float,
                 sma_90d: float) -> tuple[str, float]:
    """Classify one candle from BTC price action. Returns (regime, confidence)."""
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
    return ("NEUTRAL", 0.70)


def compute_features(df_4h: pd.DataFrame) -> pd.DataFrame:
    """Add ret_30d / drawdown_7d / sma_90d columns to a BTC 4h OHLC dataframe."""
    df = df_4h.sort_values("date").reset_index(drop=True).copy()
    df["sma_90d"] = df["close"].rolling(90 * _CANDLES_PER_DAY).mean()
    df["high_7d"] = df["high"].rolling(7 * _CANDLES_PER_DAY).max()
    df["ret_30d"] = (df["close"] / df["close"].shift(30 * _CANDLES_PER_DAY)) - 1.0
    df["drawdown_7d"] = (df["close"] / df["high_7d"]) - 1.0
    return df


def classify_latest(df_4h: pd.DataFrame) -> tuple[str, float]:
    """Classify the most recent candle of a BTC 4h dataframe."""
    df = compute_features(df_4h)
    row = df.iloc[-1]
    return classify_row(row["close"], row["ret_30d"], row["drawdown_7d"], row["sma_90d"])


def trend_horizon(df_4h: pd.DataFrame) -> pd.Series:
    """Trend-duration score 0-3 per candle (E3 'detecting trend time').

    Counts how many lookback horizons agree with the current short-term
    direction: EMA20>EMA50 (≈3d trend), EMA50>EMA200 (≈2wk), close vs SMA 90d
    (quarterly). 3 = trend aligned across all horizons (mature, durable);
    0 = no alignment (chop / fresh reversal). Sign follows the short horizon.
    """
    df = df_4h.sort_values("date").reset_index(drop=True)
    ema20 = df["close"].ewm(span=20, adjust=False).mean()
    ema50 = df["close"].ewm(span=50, adjust=False).mean()
    ema200 = df["close"].ewm(span=200, adjust=False).mean()
    sma90d = df["close"].rolling(90 * _CANDLES_PER_DAY).mean()

    up = ((ema20 > ema50).astype(int)
          + (ema50 > ema200).astype(int)
          + (df["close"] > sma90d).astype(int))
    down = ((ema20 < ema50).astype(int)
            + (ema50 < ema200).astype(int)
            + (df["close"] < sma90d).astype(int))
    score = up.where(ema20 > ema50, -down)
    return score.astype(float)
