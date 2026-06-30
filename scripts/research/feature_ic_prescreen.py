#!/usr/bin/env python3
"""
feature_ic_prescreen.py — does a candidate ENTRY feature actually predict?

Phase 4 groundwork. The model has ~no net entry alpha after market beta
(reference_cross_sectional_nogo). Re-tuning won't fix that — we need a NEW signal.
This script pre-screens candidate features for directional Information Coefficient
(Spearman vs 12-candle forward return) BEFORE the expensive model retrain, using
only data we already have: OHLCV (2020→), OI per-pair (2024→), funding per-pair.

A feature is worth integrating only if its STANDALONE IC clears the bar the whole
1844-feature model currently achieves (pooled ~0.05) AND is robust (same sign on a
majority of pairs). Most won't. That's the point — kill bad ideas cheaply.

Pure pandas/numpy, host-only, read-only. No model, no docker, no live impact.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
DATA = ROOT / "freqtrade/user_data/data/binance/futures"
OI_PARQUET = ROOT / "finbuddy_memory/historical/oi_perpair.parquet"
FUND_PARQUET = ROOT / "finbuddy_memory/historical/funding_perpair.parquet"
CONFIG = ROOT / "freqtrade/user_data/config.json"
OUT = ROOT / "finbuddy_memory/analytics/feature_ic_prescreen.json"

HORIZON = 12          # forward-return horizon (candles), matches label_period
SINCE = "2024-06-01"  # OI coverage starts 2024-01; leave warmup


def load_pair(base: str, oi: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame | None:
    f = DATA / f"{base}_USDT_USDT-1h-futures.feather"
    if not f.exists():
        return None
    df = pd.read_feather(f).set_index("date")
    df = df[df.index >= SINCE]
    if len(df) < 1000:
        return None
    sym = f"{base}USDT"
    o = oi[oi["symbol"] == sym].set_index("date")[["oi", "oi_z30d", "oi_chg"]]
    fu = fund[fund["symbol"] == sym].set_index("date")[["funding_rate", "funding_rate_z30d"]]
    # funding is 8h; reindex/ffill onto the 1h grid
    df = df.join(o, how="left")
    df = df.join(fu.reindex(df.index, method="ffill"), how="left")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    ret1 = c.pct_change()
    out = pd.DataFrame(index=df.index)

    # ── momentum / mean-reversion baselines ──
    out["ret_6"] = c.pct_change(6)
    out["ret_24"] = c.pct_change(24)
    out["rsi_14"] = _rsi(c, 14)
    out["dist_ema50"] = c / c.ewm(span=50).mean() - 1
    out["dist_ema200"] = c / c.ewm(span=200).mean() - 1

    # ── volatility regime ──
    atr = (df["high"] - df["low"]).rolling(14).mean()
    out["atr_z"] = _z(atr, 240)
    out["vol_of_vol"] = ret1.rolling(24).std() / ret1.rolling(240).std()

    # ── volume ──
    out["vol_z"] = _z(df["volume"], 240)
    out["vol_ret"] = _z(df["volume"], 240) * np.sign(ret1)   # effort×direction

    # ── open interest (the headline Phase-4 candidates) ──
    if "oi_z30d" in df:
        oi_chg = df["oi"].pct_change()
        out["oi_z30d"] = df["oi_z30d"]
        out["oi_chg_6"] = df["oi"].pct_change(6)
        # OI-price divergence: OI up + price down = new shorts (bearish); etc.
        out["oi_price_div"] = np.sign(oi_chg) * np.sign(ret1) * _z(df["oi"].diff(), 240).abs()
        out["oi_up_price_dn"] = ((oi_chg > 0) & (ret1 < 0)).astype(float) - \
                                ((oi_chg > 0) & (ret1 > 0)).astype(float)

    # ── funding (overleverage signal) ──
    if "funding_rate" in df:
        out["funding_z"] = df["funding_rate_z30d"]
        fr = df["funding_rate"]
        out["funding_mom"] = fr.rolling(12).sum().diff()          # LLM proposal
        out["funding_extreme"] = -_z(fr, 240)                     # high funding → bearish
    return out


def _rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _z(s: pd.Series, n: int) -> pd.Series:
    return (s - s.rolling(n, min_periods=n // 4).mean()) / s.rolling(n, min_periods=n // 4).std()


def spearman(a: pd.Series, b: pd.Series) -> float:
    m = a.notna() & b.notna()
    if m.sum() < 100:
        return np.nan
    return a[m].rank().corr(b[m].rank())


def main():
    cfg = json.loads(CONFIG.read_text())
    wl = [p.split("/")[0] for p in cfg["exchange"]["pair_whitelist"]]
    oi = pd.read_parquet(OI_PARQUET)
    fund = pd.read_parquet(FUND_PARQUET)

    # accumulate per-feature IC across pairs
    feat_ics: dict[str, list] = {}
    n_pairs = 0
    for base in wl:
        df = load_pair(base, oi, fund)
        if df is None:
            continue
        n_pairs += 1
        feats = build_features(df)
        fwd = df["close"].shift(-HORIZON) / df["close"] - 1
        for col in feats.columns:
            ic = spearman(feats[col], fwd)
            if not np.isnan(ic):
                feat_ics.setdefault(col, []).append(ic)

    rows = []
    for feat, ics in feat_ics.items():
        ics = np.array(ics)
        mean_ic = ics.mean()
        # robustness: fraction of pairs sharing the dominant sign
        same_sign = max((ics > 0).mean(), (ics < 0).mean())
        rows.append({
            "feature": feat,
            "mean_ic": round(float(mean_ic), 4),
            "abs_ic": round(float(abs(mean_ic)), 4),
            "median_ic": round(float(np.median(ics)), 4),
            "same_sign_%": round(float(same_sign * 100), 0),
            "n_pairs": len(ics),
        })
    rows.sort(key=lambda r: r["abs_ic"], reverse=True)

    print(f"Feature IC pre-screen · {n_pairs} pairs · {HORIZON}h fwd · since {SINCE}")
    print(f"(model's whole-ensemble pooled IC ≈ 0.05 — a single feature beating that AND")
    print(f" robust across pairs is a real lead)\n")
    print(f"  {'feature':16} {'mean_IC':>8} {'median':>8} {'same_sign':>10} {'verdict'}")
    for r in rows:
        v = ("STRONG" if r["abs_ic"] >= 0.05 and r["same_sign_%"] >= 65 else
             "weak"   if r["abs_ic"] >= 0.03 and r["same_sign_%"] >= 60 else "noise")
        print(f"  {r['feature']:16} {r['mean_ic']:+8.4f} {r['median_ic']:+8.4f} "
              f"{r['same_sign_%']:9.0f}% {v}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"horizon": HORIZON, "since": SINCE,
                               "n_pairs": n_pairs, "features": rows}, indent=2))
    print(f"\nsaved → {OUT}")


if __name__ == "__main__":
    main()
