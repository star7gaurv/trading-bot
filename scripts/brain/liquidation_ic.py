#!/usr/bin/env python3
"""liquidation_ic.py — Phase 4c: IC gate for LIQUIDATION features (Coinalyze data).

Tests whether market-wide futures liquidations predict short-horizon forward returns —
the one order-flow signal not in our data and not latency-bound. Same gate as feature_ic.py:
pooled Spearman IC of feature(t) vs realized forward return, per horizon, + per-pair sign
agreement. GATE: |pooled IC| > 0.05 with majority pair agreement -> graduate to a brain A/B.

Hypotheses (contrarian / capitulation):
  - liq_long  (longs force-SOLD = capitulation) spike -> bounce  => +IC vs fwd
  - liq_short (shorts force-BOUGHT = squeeze)   spike -> fade    => -IC vs fwd
  - liq_imbalance = (long-short)/(long+short)  -> +1 capitulation (bullish), -1 squeeze

Data: finbuddy_memory/historical/liquidations_perpair.parquet (1h buckets, sparse: missing
hour = no liquidation = 0). Reindexed onto each pair's 1h OHLCV feather grid.
Usage: python3 scripts/brain/liquidation_ic.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "freqtrade" / "user_data" / "data" / "binance" / "futures"
LIQ = ROOT / "finbuddy_memory" / "historical" / "liquidations_perpair.parquet"
OUT = ROOT / "finbuddy_memory" / "analytics" / "liquidation_ic.json"

HORIZONS = [1, 3, 6, 12]      # 1h candles -> 1h/3h/6h/12h forward
ZWIN = 168                    # 1-week rolling z-score window
FEATURES = ["liq_long_z", "liq_short_z", "liq_total_z", "liq_imbalance", "liq_spike"]


def load_ohlcv(pair: str) -> pd.DataFrame | None:
    f = DATA / f"{pair.replace('/', '_').replace(':', '_')}-1h-futures.feather"
    if not f.exists():
        return None
    df = pd.read_feather(f)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df[["date", "close"]].sort_values("date").reset_index(drop=True)


def liq_features(grid: pd.DataFrame, liq: pd.DataFrame) -> pd.DataFrame:
    """Reindex sparse liquidations onto the OHLCV hourly grid (missing = 0) and build features."""
    g = grid.merge(liq[["date", "liq_long_usd", "liq_short_usd"]], on="date", how="left")
    g[["liq_long_usd", "liq_short_usd"]] = g[["liq_long_usd", "liq_short_usd"]].fillna(0.0)
    ln = np.log1p(g["liq_long_usd"]); sh = np.log1p(g["liq_short_usd"])
    tot = np.log1p(g["liq_long_usd"] + g["liq_short_usd"])

    def z(s):
        return (s - s.rolling(ZWIN, min_periods=24).mean()) / s.rolling(ZWIN, min_periods=24).std()

    g["liq_long_z"] = z(ln)
    g["liq_short_z"] = z(sh)
    g["liq_total_z"] = z(tot)
    denom = (g["liq_long_usd"] + g["liq_short_usd"]).replace(0, np.nan)
    g["liq_imbalance"] = (g["liq_long_usd"] - g["liq_short_usd"]) / denom
    g["liq_spike"] = (g["liq_long_usd"] + g["liq_short_usd"]) / \
        (g["liq_long_usd"] + g["liq_short_usd"]).rolling(ZWIN, min_periods=24).mean()
    return g


def spearman_ic(x: np.ndarray, y: np.ndarray):
    xs = pd.Series(x); ys = pd.Series(y)
    if len(xs) < 30 or xs.nunique() < 5:
        return None
    xr = xs.rank().to_numpy(); yr = ys.rank().to_numpy()
    if xr.std() == 0 or yr.std() == 0:
        return None
    return float(np.corrcoef(xr, yr)[0, 1])


def main() -> int:
    liq_all = pd.read_parquet(LIQ)
    liq_all["date"] = pd.to_datetime(liq_all["date"], utc=True)
    pairs = json.loads((ROOT / "freqtrade/user_data/config.json").read_text())["exchange"]["pair_whitelist"]

    # pooled arrays + per-pair IC per (feature, horizon)
    pooled = {h: {f: [[], []] for f in FEATURES} for h in HORIZONS}
    perpair = {h: {f: [] for f in FEATURES} for h in HORIZONS}
    n_pairs = 0

    for pair in pairs:
        g = load_ohlcv(pair)
        if g is None:
            continue
        sym = pair.split("/")[0] + "USDT"
        sub = liq_all[liq_all["symbol"] == sym]
        if sub.empty:
            continue
        g = liq_features(g, sub)
        # restrict to the liquidation-covered span for this pair
        g = g[(g["date"] >= sub["date"].min()) & (g["date"] <= sub["date"].max())]
        if len(g) < 200:
            continue
        n_pairs += 1
        for h in HORIZONS:
            fwd = g["close"].shift(-h) / g["close"] - 1.0
            for f in FEATURES:
                d = pd.DataFrame({"f": g[f], "y": fwd}).dropna()
                if len(d) < 50:
                    continue
                pooled[h][f][0].append(d["f"].to_numpy())
                pooled[h][f][1].append(d["y"].to_numpy())
                ic = spearman_ic(d["f"].to_numpy(), d["y"].to_numpy())
                if ic is not None:
                    perpair[h][f].append(ic)

    report = {"n_pairs": n_pairs, "window": "liquidation-covered span per pair (~2026-04-25→06-23)",
              "horizons": {}}
    graduated = []
    for h in HORIZONS:
        report["horizons"][str(h)] = {}
        for f in FEATURES:
            xs, ys = pooled[h][f]
            if not xs:
                continue
            ic = spearman_ic(np.concatenate(xs), np.concatenate(ys))
            pp = perpair[h][f]
            agree = (np.mean([np.sign(v) == np.sign(ic) for v in pp]) if (pp and ic) else 0.0)
            report["horizons"][str(h)][f] = {
                "pooled_ic": round(ic, 4) if ic is not None else None,
                "n": int(sum(len(a) for a in xs)),
                "pair_agreement": round(float(agree), 2),
                "n_pairs": len(pp),
            }
            if ic is not None and abs(ic) > 0.05 and agree >= 0.6:
                graduated.append(f"{f}@{h}h")
    report["graduated"] = graduated

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))

    # pretty table
    print(f"\n=== Liquidation feature IC  ({n_pairs} pairs, ~2mo window) ===")
    hdr = f"{'feature':14s}" + "".join(f"{str(h)+'h':>22s}" for h in HORIZONS)
    print(hdr); print("-" * len(hdr))
    for f in FEATURES:
        cells = ""
        for h in HORIZONS:
            c = report["horizons"][str(h)].get(f)
            cells += f"{(str(c['pooled_ic'])+' ('+str(c['pair_agreement'])+')'):>22s}" if c else f"{'-':>22s}"
        print(f"{f:14s}{cells}")
    print("\n(format: pooled_IC (pair_agreement) ; GATE |IC|>0.05 & agree>=0.6)")
    print(f"Graduated: {graduated or 'NONE'}")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
