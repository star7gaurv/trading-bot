#!/usr/bin/env python3
"""meta_auc.py — score the meta-model's out-of-sample separation (the Phase-3 GO/NO-GO gate).

Reads the per-pair parquets dumped by CortexaAI_v23 when a backtest runs with
FREQAI_META_DUMP=1 (cols: date, do_predict, pred_long, pred_short, y_long, y_short), pools
them, and computes ROC AUC of the meta predictions vs the freshly-recomputed ground-truth
labels over do_predict==1 candles.

AUC interpretation (the gate the 2026-06-17 run skipped):
  > 0.55  → meta has real entry-time signal → sweep meta_threshold + validate trade-level A/B.
  0.52-0.55 → weak; marginal, likely not worth deploying.
  <= 0.52 → no separable signal at entry → meta-labeling is genuinely dead → Phase 4b (features).

Usage:  python3 scripts/brain/meta_auc.py [--dir freqtrade/user_data/meta_eval]
Writes a summary to finbuddy_memory/analytics/meta_auc.json.
"""
import argparse, glob, json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "freqtrade" / "user_data" / "meta_eval"
OUT = ROOT / "finbuddy_memory" / "analytics" / "meta_auc.json"


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """ROC AUC via the Mann-Whitney U / rank formula (handles ties with average ranks)."""
    labels = labels.astype(int)
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    sum_pos = ranks[labels == 1].sum()
    return float((sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def score_side(df: pd.DataFrame, pred_col: str, y_col: str) -> dict:
    m = (df["do_predict"] == 1) & df[y_col].notna() & df[pred_col].notna()
    sub = df[m]
    if sub.empty:
        return {"n": 0, "auc": None, "base_rate": None}
    return {
        "n": int(len(sub)),
        "auc": round(auc(sub[pred_col].to_numpy(), sub[y_col].to_numpy()), 4),
        "base_rate": round(float((sub[y_col] == 1).mean()), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.parquet")))
    if not files:
        print(f"[meta_auc] no parquet dumps in {args.dir} — run a backtest with FREQAI_META_DUMP=1 first")
        return 1

    # Group files by their "__<d0>_<d1>" window suffix so bull/bear windows are scored separately.
    groups: dict[str, list[str]] = {}
    for f in files:
        stem = Path(f).stem
        win = stem.split("__", 1)[1] if "__" in stem else "all"
        groups.setdefault(win, []).append(f)

    def score_group(flist: list[str]) -> dict:
        frames = []
        for f in flist:
            try:
                frames.append(pd.read_parquet(f))
            except Exception as e:
                print(f"[meta_auc] skip {f}: {e}")
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        long_ = score_side(df, "pred_long", "y_long")
        short_ = score_side(df, "pred_short", "y_short")
        pp, py = [], []
        for pc, yc in (("pred_long", "y_long"), ("pred_short", "y_short")):
            m = (df["do_predict"] == 1) & df[yc].notna() & df[pc].notna()
            pp.append(df.loc[m, pc].to_numpy()); py.append(df.loc[m, yc].to_numpy())
        pp = np.concatenate(pp) if pp else np.array([])
        py = np.concatenate(py) if py else np.array([])
        pooled = {"n": int(len(py)),
                  "auc": round(auc(pp, py), 4) if len(py) else None,
                  "base_rate": round(float((py == 1).mean()), 4) if len(py) else None}
        return {"pairs": len(flist), "long": long_, "short": short_, "pooled": pooled}

    windows = {win: score_group(fl) for win, fl in sorted(groups.items())}

    all_aucs = []
    for w in windows.values():
        for side in ("long", "short", "pooled"):
            a = w.get(side, {}).get("auc")
            if a is not None:
                all_aucs.append(a)
    best = max(all_aucs) if all_aucs else float("nan")
    if np.isnan(best):
        verdict = "NO DATA"
    elif best > 0.55:
        verdict = "GO — meta has entry-time signal; sweep threshold + validate trade-level A/B"
    elif best > 0.52:
        verdict = "WEAK — marginal separation; likely not worth deploying"
    else:
        verdict = "DEAD — no separable signal at entry; go to Phase 4b (new features)"

    summary = {"files": len(files), "windows": windows,
               "best_auc": None if np.isnan(best) else best, "verdict": verdict}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\n→ {verdict}")
    print(f"→ written {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
