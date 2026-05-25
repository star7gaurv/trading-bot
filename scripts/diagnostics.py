"""FreqAI model diagnostics — see what the model actually values.

Phase 2 of the 2026-05-25 plan (exit-rate-0-968-usdt-peaceful-flame).

Loads every per-pair LightGBM model under freqtrade/user_data/models/sub-train-*/
and reports:
  1. Top-K feature importance per pair (gain)
  2. Aggregated mean/median importance across all pairs
  3. Prediction distribution percentiles + fraction above |z| thresholds
  4. Dead-feature warning (mean importance < threshold)

Optional CSV export, optional --compare against an older snapshot.

Read-only. Safe to run on the live server at any time.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

DEFAULT_MODELS_DIR = Path("/freqtrade/user_data/models")
HOST_MODELS_DIR = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/models")
MODELS_DIR = DEFAULT_MODELS_DIR if DEFAULT_MODELS_DIR.exists() else HOST_MODELS_DIR
HISTORIC_PRED_PKL = MODELS_DIR / "historic_predictions.pkl"


def latest_per_pair(models_dir: Path, since_ts: int = 0) -> dict[str, Path]:
    """Return {pair_name: latest_sub_train_dir} keeping only the newest per pair."""
    latest: dict[str, tuple[int, Path]] = {}
    for sub in models_dir.glob("sub-train-*"):
        if not sub.is_dir():
            continue
        # sub-train-{PAIR}_{ts}
        name = sub.name[len("sub-train-"):]
        try:
            pair, ts_str = name.rsplit("_", 1)
            ts = int(ts_str)
        except (ValueError, IndexError):
            continue
        if ts < since_ts:
            continue
        prev = latest.get(pair)
        if prev is None or ts > prev[0]:
            latest[pair] = (ts, sub)
    return {p: d for p, (_, d) in latest.items()}


def _find_model_file(pair_dir: Path) -> Path | None:
    candidates = list(pair_dir.glob("*_model.joblib"))
    return candidates[0] if candidates else None


def _find_metadata_file(pair_dir: Path) -> Path | None:
    candidates = list(pair_dir.glob("*_metadata.json"))
    return candidates[0] if candidates else None


def _feature_importances(model: Any, feature_names: list[str]) -> dict[str, float]:
    """Extract gain-importance dict from whichever LightGBM wrapper is in use."""
    booster = None
    if hasattr(model, "booster_"):
        booster = model.booster_
    elif hasattr(model, "feature_importance"):
        booster = model
    if booster is not None:
        try:
            imps = booster.feature_importance(importance_type="gain")
            names = booster.feature_name()
            return dict(zip(names, [float(x) for x in imps]))
        except Exception:
            pass
    if hasattr(model, "feature_importances_"):
        arr = np.asarray(model.feature_importances_, dtype=float)
        if len(arr) == len(feature_names):
            return dict(zip(feature_names, arr.tolist()))
    return {}


def load_per_pair_importances(pair_dirs: dict[str, Path]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for pair, pair_dir in sorted(pair_dirs.items()):
        model_file = _find_model_file(pair_dir)
        meta_file = _find_metadata_file(pair_dir)
        if model_file is None or meta_file is None:
            print(f"  [skip] {pair}: missing model or metadata in {pair_dir}", file=sys.stderr)
            continue
        try:
            meta = json.loads(meta_file.read_text())
            features = meta.get("training_features_list", [])
            model = joblib.load(model_file)
            imps = _feature_importances(model, features)
            if not imps:
                print(f"  [skip] {pair}: could not extract importances", file=sys.stderr)
                continue
            out[pair] = imps
        except Exception as e:
            print(f"  [skip] {pair}: {e}", file=sys.stderr)
    return out


def aggregate_importances(per_pair: dict[str, dict[str, float]]) -> pd.DataFrame:
    rows: dict[str, list[float]] = defaultdict(list)
    for _, imps in per_pair.items():
        # Normalize each pair's importances to sum=1 so big-and-noisy pairs don't dominate
        total = sum(imps.values()) or 1.0
        for feat, v in imps.items():
            # Strip per-pair suffix so "%-rsi-period_10_ETH/USDTUSDT_15m" → "%-rsi-period_10_{TF}"
            generic = _generic_feature_name(feat)
            rows[generic].append(v / total)
    data = []
    for feat, vals in rows.items():
        arr = np.asarray(vals)
        data.append({
            "feature": feat,
            "n_pairs": len(vals),
            "mean_norm_imp": float(arr.mean()),
            "median_norm_imp": float(np.median(arr)),
            "max_norm_imp": float(arr.max()),
        })
    df = pd.DataFrame(data).sort_values("mean_norm_imp", ascending=False).reset_index(drop=True)
    return df


def _generic_feature_name(feat: str) -> str:
    """Collapse per-pair suffixes so features can be compared across pairs.

    "%-rsi-period_10_ETH/USDTUSDT_15m"          -> "%-rsi-period_10_{TF15m}"
    "%-rsi-period_10_BTC/USDTUSDT_1h"           -> "%-rsi-period_10_{BTC_INF_1h}"
    "%-fear_greed"                              -> "%-fear_greed"
    """
    if "BTC/USDTUSDT" in feat:
        # informative BTC features; keep the BTC marker so we don't merge with own-pair
        for tf in ("_15m", "_30m", "_1h", "_4h", "_1d"):
            if feat.endswith(tf):
                return feat.replace("BTC/USDTUSDT", "{BTC_INF}")
        return feat.replace("BTC/USDTUSDT", "{BTC_INF}")
    for tf in ("_15m", "_30m", "_1h", "_4h", "_1d"):
        if feat.endswith(tf):
            # strip "_{pair}/USDTUSDT{tf}" → keep tf marker only
            base = feat[: -len(tf)]
            if "/USDTUSDT" in base:
                pair_start = base.rfind("_")
                base = base[:pair_start]
            return f"{base}_{{TF{tf}}}"
    return feat


def prediction_distribution(historic_pkl: Path) -> pd.DataFrame:
    if not historic_pkl.exists():
        print(f"  [warn] {historic_pkl} not found — skipping prediction distribution", file=sys.stderr)
        return pd.DataFrame()
    try:
        data = pd.read_pickle(historic_pkl)
    except Exception as e:
        print(f"  [warn] could not read {historic_pkl}: {e}", file=sys.stderr)
        return pd.DataFrame()
    rows = []
    # historic_predictions.pkl is a dict {pair: DataFrame} in FreqAI
    if isinstance(data, dict):
        for pair, df in data.items():
            if not isinstance(df, pd.DataFrame) or "&-future_return" not in df.columns:
                continue
            preds = df["&-future_return"].dropna().to_numpy()
            if len(preds) == 0:
                continue
            rows.append(_pred_stats(pair, preds))
    elif isinstance(data, pd.DataFrame) and "&-future_return" in data.columns:
        preds = data["&-future_return"].dropna().to_numpy()
        rows.append(_pred_stats("ALL", preds))
    return pd.DataFrame(rows).sort_values("pair").reset_index(drop=True)


def _pred_stats(pair: str, preds: np.ndarray) -> dict[str, Any]:
    return {
        "pair": pair,
        "n": int(len(preds)),
        "mean": float(preds.mean()),
        "std": float(preds.std()),
        "p01": float(np.percentile(preds, 1)),
        "p05": float(np.percentile(preds, 5)),
        "p25": float(np.percentile(preds, 25)),
        "p50": float(np.percentile(preds, 50)),
        "p75": float(np.percentile(preds, 75)),
        "p95": float(np.percentile(preds, 95)),
        "p99": float(np.percentile(preds, 99)),
        "frac_abs_gt_0.5": float((np.abs(preds) > 0.5).mean()),
        "frac_abs_gt_0.8": float((np.abs(preds) > 0.8).mean()),
        "frac_abs_gt_1.0": float((np.abs(preds) > 1.0).mean()),
    }


def print_top_k_per_pair(per_pair: dict[str, dict[str, float]], k: int) -> None:
    print("\n" + "=" * 78)
    print(f"TOP-{k} FEATURE IMPORTANCE PER PAIR")
    print("=" * 78)
    for pair, imps in sorted(per_pair.items()):
        if not imps:
            continue
        ranked = sorted(imps.items(), key=lambda kv: kv[1], reverse=True)[:k]
        total = sum(imps.values()) or 1.0
        print(f"\n  {pair}  (n_features={len(imps)}, total_gain={total:.1f})")
        for feat, v in ranked:
            print(f"    {v / total * 100:6.2f}%   {feat}")


def print_aggregate(agg: pd.DataFrame, k: int, dead_threshold: float) -> None:
    print("\n" + "=" * 78)
    print(f"AGGREGATED IMPORTANCE — TOP {k} GENERIC FEATURES (mean of per-pair normalized gain)")
    print("=" * 78)
    head = agg.head(k)
    for _, r in head.iterrows():
        print(f"  {r['mean_norm_imp'] * 100:6.3f}%  med={r['median_norm_imp'] * 100:5.2f}%  max={r['max_norm_imp'] * 100:5.2f}%  n={int(r['n_pairs']):2d}  {r['feature']}")
    dead = agg[agg["mean_norm_imp"] < dead_threshold]
    print(f"\n  Dead-feature candidates (mean_norm_imp < {dead_threshold}): {len(dead)} / {len(agg)} ({len(dead) / max(len(agg), 1) * 100:.1f}%)")
    if 0 < len(dead) <= 40:
        for f in dead["feature"].tolist():
            print(f"    {f}")


def print_pred_distribution(pred_df: pd.DataFrame) -> None:
    if pred_df.empty:
        print("\n[no prediction distribution available]")
        return
    print("\n" + "=" * 78)
    print("PREDICTION DISTRIBUTION (from historic_predictions.pkl)")
    print("=" * 78)
    print(pred_df.to_string(index=False, float_format=lambda x: f"{x:7.3f}"))
    overall_frac = pred_df["frac_abs_gt_0.8"].mean()
    print(f"\n  Avg fraction of candles with |pred| > 0.8 (current threshold): {overall_frac:.3%}")
    if overall_frac < 0.01:
        print("  ⚠ Predictions almost never cross the entry threshold — thresholds may be too tight or model output too narrow.")


def main() -> int:
    p = argparse.ArgumentParser(description="FreqAI model diagnostics")
    p.add_argument("--top-k", type=int, default=30, help="top K features per pair and in aggregate")
    p.add_argument("--since-ts", type=int, default=0, help="only consider models with timestamp >= this unix ts")
    p.add_argument("--dead-threshold", type=float, default=0.005, help="mean_norm_imp below this is dead")
    p.add_argument("--export-csv", type=Path, default=None, help="write aggregate to this CSV path")
    p.add_argument("--quiet-per-pair", action="store_true", help="skip per-pair section, only show aggregate")
    args = p.parse_args()

    if not MODELS_DIR.exists():
        print(f"Models dir not found: {MODELS_DIR}", file=sys.stderr)
        return 2

    pair_dirs = latest_per_pair(MODELS_DIR, since_ts=args.since_ts)
    if not pair_dirs:
        print(f"No sub-train-* dirs found in {MODELS_DIR}", file=sys.stderr)
        return 2
    print(f"Found {len(pair_dirs)} pairs with trained models.")

    per_pair = load_per_pair_importances(pair_dirs)
    if not per_pair:
        print("No importances could be extracted.", file=sys.stderr)
        return 2

    agg = aggregate_importances(per_pair)
    pred_df = prediction_distribution(HISTORIC_PRED_PKL)

    if not args.quiet_per_pair:
        print_top_k_per_pair(per_pair, args.top_k)
    print_aggregate(agg, args.top_k, args.dead_threshold)
    print_pred_distribution(pred_df)

    if args.export_csv:
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        agg.to_csv(args.export_csv, index=False)
        print(f"\nAggregate written to {args.export_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
