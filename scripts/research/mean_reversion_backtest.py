#!/usr/bin/env python3
"""
mean_reversion_backtest.py — is the measured MR signal actually PROFITABLE after fees?

The feature pre-screen found one robust signal: short-horizon mean-reversion
(ret24_z IC -0.028 @3h, 100% pair agreement). IC>0 ≠ money. This simulates a real
fade strategy — entries, time/revert exits, taker fees — across all 26 pairs and
reports whether the edge survives costs. No model, no docker, host-only, read-only.

Rule: when a pair is stretched UP past +Zσ (24h-return z-score), SHORT it; stretched
DOWN past -Zσ, LONG it. Exit after H hours or when the signal reverts toward 0.
One position per pair at a time. Fee = taker per side, both entry and exit.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
DATA = ROOT / "freqtrade/user_data/data/binance/futures"
CONFIG = ROOT / "freqtrade/user_data/config.json"

TAKER_FEE = 0.0005
SINCE = "2024-06-01"


def signal(df: pd.DataFrame) -> pd.Series:
    """Extension z-score: positive = stretched up (fade short), negative = fade long."""
    c = df["close"]
    r24 = c.pct_change(24)
    z = (r24 - r24.rolling(240, min_periods=60).mean()) / r24.rolling(240, min_periods=60).std()
    return z


def backtest_pair(df: pd.DataFrame, entry_z: float, hold_h: int, exit_z: float):
    """Return list of per-trade NET returns for one pair (non-overlapping)."""
    df = df[df.index >= SINCE]
    if len(df) < 400:
        return []
    sig = signal(df)
    close = df["close"].values
    s = sig.values
    n = len(df)
    trades = []
    i = 60
    while i < n - hold_h - 1:
        if np.isnan(s[i]):
            i += 1
            continue
        side = 0
        if s[i] >= entry_z:
            side = -1          # stretched up -> short (fade)
        elif s[i] <= -entry_z:
            side = +1          # stretched down -> long (fade)
        if side == 0:
            i += 1
            continue
        # hold until revert past exit_z or hold_h elapses
        exit_i = min(i + hold_h, n - 1)
        for j in range(i + 1, min(i + hold_h, n - 1) + 1):
            if (side == -1 and s[j] <= exit_z) or (side == +1 and s[j] >= -exit_z):
                exit_i = j
                break
        gross = side * (close[exit_i] / close[i] - 1)
        net = gross - 2 * TAKER_FEE
        trades.append(net)
        i = exit_i + 1         # non-overlapping
    return trades


def stats(trades):
    if not trades:
        return None
    t = np.array(trades)
    eq = (1 + t).cumprod()
    per_yr = 365 * 24 / 6  # rough: avg hold ~6h
    sharpe = (t.mean() / t.std() * np.sqrt(per_yr)) if t.std() > 0 else 0
    return {
        "trades": len(t), "total_%": (eq[-1] - 1) * 100, "avg_bps": t.mean() * 1e4,
        "WR_%": (t > 0).mean() * 100, "sharpe": sharpe,
        "maxDD_%": (eq / np.maximum.accumulate(eq) - 1).min() * 100,
    }


def main():
    cfg = json.loads(CONFIG.read_text())
    wl = [p.split("/")[0] for p in cfg["exchange"]["pair_whitelist"]]
    dfs = {}
    for base in wl:
        f = DATA / f"{base}_USDT_USDT-1h-futures.feather"
        if f.exists():
            dfs[base] = pd.read_feather(f).set_index("date")

    print(f"Mean-reversion fade backtest · {len(dfs)} pairs · since {SINCE} · "
          f"fee {TAKER_FEE*100:.3f}%/side\n")
    print(f"  {'entry_z':>7} {'hold':>5} {'exit_z':>6}  {'trades':>7} {'WR%':>5} "
          f"{'avg_bps':>8} {'total%':>8} {'Sharpe':>7} {'maxDD%':>7}")
    best = None
    for entry_z in (1.0, 1.5, 2.0):
        for hold_h in (3, 6, 12):
            for exit_z in (0.0, 0.5):
                allt = []
                for base, df in dfs.items():
                    allt += backtest_pair(df, entry_z, hold_h, exit_z)
                st = stats(allt)
                if not st:
                    continue
                print(f"  {entry_z:7.1f} {hold_h:5d} {exit_z:6.1f}  {st['trades']:7d} "
                      f"{st['WR_%']:5.1f} {st['avg_bps']:+8.1f} {st['total_%']:+8.1f} "
                      f"{st['sharpe']:+7.2f} {st['maxDD_%']:7.1f}")
                if best is None or st["avg_bps"] > best[1]["avg_bps"]:
                    best = ((entry_z, hold_h, exit_z), st)
    if best:
        (ez, hh, xz), st = best
        print(f"\nBest avg/trade: entry_z={ez} hold={hh}h exit_z={xz} → "
              f"{st['avg_bps']:+.1f} bps/trade net, WR {st['WR_%']:.1f}%, "
              f"Sharpe {st['sharpe']:+.2f}, {st['trades']} trades")
        print("Net edge per trade must clearly exceed ~10bps (2× fee) to be real.")


if __name__ == "__main__":
    main()
