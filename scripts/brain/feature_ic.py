#!/usr/bin/env python3
"""feature_ic.py — Phase 4b standalone feature IC gate (2026-06-20).

Tests candidate ENTRY features in ISOLATION before they ever touch the model, so a real
signal isn't diluted among the 530-feature soup (the failure mode of every prior attempt).

For each candidate feature it computes the Spearman Information Coefficient (rank corr of the
feature at time t vs the realized 12-candle forward return), pooled across pairs, per window.

GATE: a feature graduates to a brain A/B only if |pooled IC| > 0.05 on the BEAR windows
(live is bear). |IC| <= ~0.03 is the current noise floor → drop it.

Families tested here (the free, no-new-data ones — 4b.1 BTC lead-lag + 4b.2 funding extremes).
Usage:
  python3 scripts/brain/feature_ic.py [horizon [tf]]   # single-TF (backward compat)
  python3 scripts/brain/feature_ic.py --all-tf         # sweep all TFs → feature_ic_by_tf.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "freqtrade" / "user_data" / "data" / "binance" / "futures"
FUNDING = ROOT / "finbuddy_memory" / "historical" / "funding_perpair.parquet"
OIFILE = ROOT / "finbuddy_memory" / "historical" / "oi_perpair.parquet"
OFDIR = ROOT / "finbuddy_memory" / "historical" / "orderflow"
OUT = ROOT / "finbuddy_memory" / "analytics" / "feature_ic.json"
OUT_BY_TF = ROOT / "finbuddy_memory" / "analytics" / "feature_ic_by_tf.json"

ALL_TF_MODE = "--all-tf" in sys.argv
H = int(sys.argv[1]) if not ALL_TF_MODE and len(sys.argv) > 1 else 12
TF = sys.argv[2] if not ALL_TF_MODE and len(sys.argv) > 2 else "15m"

WINDOWS = {
    "bull_2024Q1": ("2024-01-01", "2024-04-01"),
    "bull_2024Q4": ("2024-10-01", "2025-01-01"),
    "bear_2025Q1": ("2025-01-01", "2025-04-01"),
    "bear_2026Q1": ("2026-01-01", "2026-04-01"),
}
BEAR = ["bear_2025Q1", "bear_2026Q1"]


def load_ohlcv(pair: str, tf: str = None) -> pd.DataFrame | None:
    _tf = tf or TF
    f = DATA / f"{pair.replace('/', '_').replace(':', '_')}-{_tf}-futures.feather"
    if not f.exists():
        return None
    df = pd.read_feather(f)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df


def btc_leadlag(btc: pd.DataFrame) -> pd.DataFrame:
    """BTC features known at time t (no lookahead) — to be aligned onto each alt's timeline."""
    c = btc["close"]
    r1 = c.pct_change(1)
    out = pd.DataFrame({"date": btc["date"]})
    out["btc_ret_1"]   = r1
    out["btc_ret_4"]   = c.pct_change(4)
    out["btc_ret_12"]  = c.pct_change(12)
    out["btc_vol_12"]  = r1.rolling(12).std()
    out["btc_accel"]   = c.pct_change(4) - c.pct_change(4).shift(4)
    return out


def funding_feats(symbol: str) -> pd.DataFrame | None:
    fp = pd.read_parquet(FUNDING)
    sub = fp[fp["symbol"] == symbol].copy()
    if sub.empty:
        return None
    sub["date"] = pd.to_datetime(sub["date"], utc=True)
    sub = sub.sort_values("date")
    sub["funding_abs_z"] = sub["funding_rate_z30d"].abs()
    return sub[["date", "funding_rate", "funding_rate_z30d", "funding_rate_chg", "funding_abs_z"]]


def oi_feats(symbol: str) -> pd.DataFrame | None:
    oi = pd.read_parquet(OIFILE)
    sub = oi[oi["symbol"] == symbol].copy()
    if sub.empty:
        return None
    sub["date"] = pd.to_datetime(sub["date"], utc=True)
    sub = sub.sort_values("date")
    sub["oi_chg_abs"] = sub["oi_chg"].abs()
    return sub[["date", "oi_z30d", "oi_chg", "oi_chg_abs"]]


def orderflow_feats(symbol: str, tf: str = None) -> pd.DataFrame | None:
    """4b.5 order-flow from taker-buy volume (Binance klines field 9, fetched separately)."""
    _tf = tf or TF
    if _tf != "15m":         # order-flow data is 15m-only; skip for higher-TF sweeps
        return None
    f = OFDIR / f"{symbol}.parquet"
    if not f.exists():
        return None
    of = pd.read_parquet(f)
    of["date"] = pd.to_datetime(of["date"], utc=True)
    of = of.sort_values("date")
    vol = of["volume"].replace(0, np.nan)
    ratio = (of["taker_buy_base"] / vol)              # fraction of volume that was aggressive buy
    net = 2 * of["taker_buy_base"] - of["volume"]     # per-candle net taker-buy
    of["of_taker_ratio"] = ratio
    of["of_ratio_z"] = (ratio - ratio.rolling(96).mean()) / ratio.rolling(96).std()
    of["of_netflow_12"] = net.rolling(12).sum() / of["volume"].rolling(12).sum()
    of["of_netflow_z"] = (of["of_netflow_12"] - of["of_netflow_12"].rolling(96).mean()) / of["of_netflow_12"].rolling(96).std()
    return of[["date", "of_taker_ratio", "of_ratio_z", "of_netflow_12", "of_netflow_z"]]


FEATURES = ["btc_ret_1", "btc_ret_4", "btc_ret_12", "btc_vol_12", "btc_accel",
            "funding_rate", "funding_rate_z30d", "funding_rate_chg", "funding_abs_z",
            "oi_z30d", "oi_chg", "oi_chg_abs",
            "of_taker_ratio", "of_ratio_z", "of_netflow_12", "of_netflow_z"]


def _run_single(h: int, tf: str) -> dict:
    """Compute IC report for one (horizon, timeframe) combination. Returns {report, graduated}."""
    btc = load_ohlcv("BTC/USDT:USDT", tf)
    if btc is None:
        print(f"[feature_ic] no BTC {tf} data"); return {}
    bll = btc_leadlag(btc)

    cfg = json.loads((ROOT / "freqtrade/user_data/config.json").read_text())
    pairs = cfg["exchange"]["pair_whitelist"]

    rows = {w: {f: [[], []] for f in FEATURES} for w in WINDOWS}

    for pair in pairs:
        df = load_ohlcv(pair, tf)
        if df is None:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        df["fwd"] = df["close"].shift(-h) / df["close"] - 1.0
        df = df.merge(bll, on="date", how="left")
        df["date"] = df["date"].astype("datetime64[ns, UTC]")
        sym = pair.split("/")[0] + "USDT"
        ff = funding_feats(sym)
        if ff is not None:
            ff["date"] = ff["date"].astype("datetime64[ns, UTC]")
            df = pd.merge_asof(df, ff, on="date", direction="backward")
        oo = oi_feats(sym)
        if oo is not None:
            oo["date"] = oo["date"].astype("datetime64[ns, UTC]")
            df = pd.merge_asof(df, oo, on="date", direction="backward")
        of = orderflow_feats(sym, tf)
        if of is not None:
            of["date"] = of["date"].astype("datetime64[ns, UTC]")
            df = df.merge(of, on="date", how="left")
        for w, (s, e) in WINDOWS.items():
            m = (df["date"] >= pd.Timestamp(s, tz="UTC")) & (df["date"] < pd.Timestamp(e, tz="UTC"))
            sub = df[m]
            if sub.empty:
                continue
            for f in FEATURES:
                if f not in sub.columns:
                    continue
                pair_df = sub[[f, "fwd"]].dropna()
                if len(pair_df) > 30:
                    rows[w][f][0].append(pair_df[f].to_numpy())
                    rows[w][f][1].append(pair_df["fwd"].to_numpy())

    def ic(xs, ys):
        if not xs:
            return None, 0
        x = pd.Series(np.concatenate(xs)); y = pd.Series(np.concatenate(ys))
        if x.nunique() < 5:
            return None, len(x)
        xr = x.rank().to_numpy(); yr = y.rank().to_numpy()
        if xr.std() == 0 or yr.std() == 0:
            return None, len(x)
        return round(float(np.corrcoef(xr, yr)[0, 1]), 4), len(x)

    report = {}
    for f in FEATURES:
        report[f] = {}
        for w in WINDOWS:
            val, n = ic(rows[w][f][0], rows[w][f][1])
            report[f][w] = {"ic": val, "n": n}

    graduated = []
    for f in FEATURES:
        bear_ics = [abs(report[f][w]["ic"]) for w in BEAR if report[f][w]["ic"] is not None]
        if bool(bear_ics) and max(bear_ics) > 0.05:
            graduated.append(f)

    return {"horizon": h, "report": report, "graduated": graduated}


def _print_table(result: dict, tf: str) -> None:
    report = result.get("report", {})
    h = result.get("horizon", "?")
    print(f"\n=== IC table  tf={tf}  horizon={h} ===")
    hdr = f"{'feature':18s} " + " ".join(f"{w:>13s}" for w in WINDOWS) + "   GATE(bear>0.05)"
    print(hdr); print("-" * len(hdr))
    for f in FEATURES:
        if f not in report:
            continue
        cells = [f"{report[f][w]['ic']:>13}" if report[f][w]["ic"] is not None else f"{'-':>13}"
                 for w in WINDOWS]
        passes = f in result.get("graduated", [])
        print(f"{f:18s} " + " ".join(cells) + ("   PASS ✅" if passes else "   ---"))
    print(f"\nGraduated: {result.get('graduated') or 'NONE'}")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if ALL_TF_MODE:
        # Canonical horizon per TF (wall-clock ~12h each)
        TF_HORIZONS = {"15m": 48, "30m": 24, "1h": 12, "4h": 3}
        by_tf: dict = {}
        for tf, h in TF_HORIZONS.items():
            print(f"\n[feature_ic] computing tf={tf} h={h}…")
            result = _run_single(h, tf)
            if result:
                _print_table(result, tf)
                by_tf[tf] = result
        combined = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "by_tf": by_tf,
        }
        OUT_BY_TF.write_text(json.dumps(combined, indent=2))
        print(f"\n→ written {OUT_BY_TF}")
        # Also update the single-TF file with the active TF's result (keeps existing crons happy)
        active_tf = json.loads((ROOT / "finbuddy_memory/timeframe_profiles.json").read_text()).get("active", "1h")
        if active_tf in by_tf:
            OUT.write_text(json.dumps(by_tf[active_tf], indent=2))
            print(f"→ updated {OUT} with active TF ({active_tf})")
        return 0

    # Single-TF mode (backward compat: python3 feature_ic.py [horizon [tf]])
    result = _run_single(H, TF)
    if not result:
        return 1
    _print_table(result, TF)
    OUT.write_text(json.dumps(result, indent=2))
    print(f"→ written {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
