#!/usr/bin/env python3
"""
ic_monitor.py — weekly out-of-sample Information Coefficient report.

Measures whether the live model's predictions actually predict: Spearman rank
correlation between every live prediction in historic_predictions.pkl and the
realized forward return over the label horizon (12 candles), per pair, for
(a) the full stored history and (b) a rolling 30-day window.

Output:
  - finbuddy_memory/analytics/pair_ic.json   (consumed by dashboards / future gating)
  - Telegram digest (best/worst pairs, pooled IC)

Measurement only — does NOT gate anything. Pair IC-gating is a pending product
decision (2026-06-11 plan, C4); this script supplies the evidence.

Cron: weekly. Pure pandas — runs on the host, no docker needed.
"""
from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402

OUT_FILE = ROOT / "finbuddy_memory/analytics/pair_ic.json"
LABEL_PERIOD = 12  # candles; matches config.json label_period_candles


def _predictions_pkl() -> Path:
    """The LIVE bot writes historic_predictions.pkl inside its IDENTIFIER
    subdir — the root models/historic_predictions.pkl is an orphan frozen at
    2026-06-07 (bug found 2026-06-12: first IC report silently analyzed it).
    Resolve the identifier from freqtrade/.env; fall back to the newest
    identifier-dir pickle, then the root file."""
    env = ROOT / "freqtrade/.env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("FREQTRADE__FREQAI__IDENTIFIER="):
                ident = line.split("=", 1)[1].strip()
                p = ROOT / f"freqtrade/user_data/models/{ident}/historic_predictions.pkl"
                if p.exists():
                    return p
    candidates = sorted(
        ROOT.glob("freqtrade/user_data/models/*/historic_predictions.pkl"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if candidates:
        return candidates[0]
    return ROOT / "freqtrade/user_data/models/historic_predictions.pkl"


PREDICTIONS_PKL = _predictions_pkl()


def _spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank()))


def _pair_ic(df: pd.DataFrame, since: datetime | None = None) -> dict | None:
    df = df.copy()
    df["date_pred"] = pd.to_datetime(df["date_pred"], utc=True)
    df = df.sort_values("date_pred").drop_duplicates("date_pred")
    close = pd.to_numeric(df["close_price"], errors="coerce").replace(0, np.nan)
    pred = pd.to_numeric(df["&-future_return"], errors="coerce")
    do_pred = pd.to_numeric(df["do_predict"], errors="coerce")
    fwd = close.shift(-LABEL_PERIOD) / close - 1
    mask = (do_pred == 1) & fwd.notna() & pred.notna()
    if since is not None:
        mask &= df["date_pred"] >= since
    n = int(mask.sum())
    if n < 50:
        return None
    return {
        "n": n,
        "ic": round(_spearman(pred[mask], fwd[mask]), 4),
        "sign_hit": round(float((np.sign(pred[mask]) == np.sign(fwd[mask])).mean()), 4),
    }


def main() -> int:
    with open(PREDICTIONS_PKL, "rb") as f:
        hp = pickle.load(f)

    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    report: dict = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "label_period_candles": LABEL_PERIOD,
        "pairs": {},
    }
    pooled_pred, pooled_fwd = [], []
    for pair, df in hp.items():
        full = _pair_ic(df)
        if full is None:
            continue
        recent = _pair_ic(df, since=cutoff_30d)
        report["pairs"][pair] = {"full": full, "rolling_30d": recent}
        # pooled (full history)
        d = df.copy()
        d["date_pred"] = pd.to_datetime(d["date_pred"], utc=True)
        d = d.sort_values("date_pred").drop_duplicates("date_pred")
        close = pd.to_numeric(d["close_price"], errors="coerce").replace(0, np.nan)
        pred = pd.to_numeric(d["&-future_return"], errors="coerce")
        fwd = close.shift(-LABEL_PERIOD) / close - 1
        m = (pd.to_numeric(d["do_predict"], errors="coerce") == 1) & fwd.notna() & pred.notna()
        pooled_pred += pred[m].tolist()
        pooled_fwd += fwd[m].tolist()

    if pooled_pred:
        report["pooled"] = {
            "n": len(pooled_pred),
            "ic": round(_spearman(pd.Series(pooled_pred), pd.Series(pooled_fwd)), 4),
        }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(report, indent=2))

    ranked = sorted(
        ((p, v["full"]["ic"]) for p, v in report["pairs"].items()),
        key=lambda x: -x[1],
    )
    pos = sum(1 for _, ic in ranked if ic > 0)
    best = ", ".join(f"{p.split('/')[0]} {ic:+.2f}" for p, ic in ranked[:4])
    worst = ", ".join(f"{p.split('/')[0]} {ic:+.2f}" for p, ic in ranked[-3:])
    send(
        Subsystem.BRAIN_CYCLE,
        Status.INFO,
        "Weekly prediction-quality (IC) report",
        fields={
            "Pooled IC": report.get("pooled", {}).get("ic", "n/a"),
            "Pairs IC>0": f"{pos}/{len(ranked)}",
            "Best": best,
            "Worst": worst,
        },
        context=f"Spearman IC vs {LABEL_PERIOD}-candle forward return, "
                f"{report.get('pooled', {}).get('n', 0)} OOS predictions. "
                f"Full report: finbuddy_memory/analytics/pair_ic.json",
        silent=True,
    )
    print(f"[ic_monitor] wrote {OUT_FILE} — pooled IC="
          f"{report.get('pooled', {}).get('ic')} over {len(ranked)} pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
