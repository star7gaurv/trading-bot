"""
live_predictions.py — shared helpers for reading the live FreqAI predictions
store and measuring live prediction quality (Information Coefficient).

Factored out 2026-09-07 so every consumer (ic_monitor.py weekly report,
edge_monitor.py live circuit breaker) uses the SAME predictions file and the
SAME label horizon. Before this, ic_monitor.py hardcoded LABEL_PERIOD=12 —
stale since the 2026-06-21 1h/label_period_candles=6 switch, so the weekly IC
report was silently measuring the wrong horizon for 2.5 months. Single
source of truth now: config.json's freqai.feature_parameters.label_period_candles,
same field the live strategy itself reads via _label_period_candles().
"""
from __future__ import annotations

import json
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "freqtrade/user_data/config.json"


def resolve_predictions_pkl(root: Path = ROOT) -> Path:
    """The LIVE bot writes historic_predictions.pkl inside its IDENTIFIER
    subdir — the root models/historic_predictions.pkl is a stale orphan.
    Resolve the identifier from freqtrade/.env; fall back to the newest
    identifier-dir pickle, then the root file."""
    env = root / "freqtrade/.env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("FREQTRADE__FREQAI__IDENTIFIER="):
                ident = line.split("=", 1)[1].strip()
                p = root / f"freqtrade/user_data/models/{ident}/historic_predictions.pkl"
                if p.exists():
                    return p
    candidates = sorted(
        root.glob("freqtrade/user_data/models/*/historic_predictions.pkl"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if candidates:
        return candidates[0]
    return root / "freqtrade/user_data/models/historic_predictions.pkl"


def label_period_candles(root: Path = ROOT, default: int = 12) -> int:
    """Single source of truth for the model's prediction horizon — same
    config field the live strategy's _label_period_candles() reads. NEVER
    hardcode this elsewhere; the brain and the UI timeframe switcher both
    change it, and every measurement of prediction quality must track it."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        return int(cfg["freqai"]["feature_parameters"]["label_period_candles"])
    except Exception:
        return default


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Rank correlation without a scipy dependency (host python lacks it)."""
    return float(a.rank().corr(b.rank()))


def load_predictions() -> dict:
    with open(resolve_predictions_pkl(), "rb") as f:
        return pickle.load(f)


def pair_ic(df: pd.DataFrame, label_period: int, since: datetime | None = None) -> dict | None:
    """IC + sample size + sign-hit-rate for one pair's stored predictions,
    optionally restricted to rows on/after `since`."""
    df = df.copy()
    df["date_pred"] = pd.to_datetime(df["date_pred"], utc=True)
    df = df.sort_values("date_pred").drop_duplicates("date_pred")
    close = pd.to_numeric(df["close_price"], errors="coerce").replace(0, np.nan)
    pred = pd.to_numeric(df["&-future_return"], errors="coerce")
    do_pred = pd.to_numeric(df["do_predict"], errors="coerce")
    fwd = close.shift(-label_period) / close - 1
    mask = (do_pred == 1) & fwd.notna() & pred.notna()
    if since is not None:
        mask &= df["date_pred"] >= since
    n = int(mask.sum())
    if n < 30:
        return None
    return {
        "n": n,
        "ic": round(spearman(pred[mask], fwd[mask]), 4),
        "sign_hit": round(float((np.sign(pred[mask]) == np.sign(fwd[mask])).mean()), 4),
    }


def pooled_ic(hp: dict, label_period: int, since: datetime | None = None) -> dict | None:
    """Pooled (all-pairs-concatenated) IC + do_predict rate over a window.
    Used for a single system-wide "is the model working right now?" number —
    per-pair IC is noisier at 30-day sample sizes with 25+ pairs."""
    pooled_pred, pooled_fwd, do_pred_vals = [], [], []
    for pair, df in hp.items():
        d = df.copy()
        d["date_pred"] = pd.to_datetime(d["date_pred"], utc=True)
        d = d.sort_values("date_pred").drop_duplicates("date_pred")
        if since is not None:
            d = d[d["date_pred"] >= since]
        if d.empty:
            continue
        close = pd.to_numeric(d["close_price"], errors="coerce").replace(0, np.nan)
        pred = pd.to_numeric(d["&-future_return"], errors="coerce")
        do_pred = pd.to_numeric(d["do_predict"], errors="coerce")
        do_pred_vals.append(do_pred)
        fwd = close.shift(-label_period) / close - 1
        m = (do_pred == 1) & fwd.notna() & pred.notna()
        pooled_pred += pred[m].tolist()
        pooled_fwd += fwd[m].tolist()
    if not pooled_pred:
        return None
    do_pred_rate = (
        float(pd.concat(do_pred_vals).eq(1).mean()) if do_pred_vals else None
    )
    return {
        "n": len(pooled_pred),
        "ic": round(spearman(pd.Series(pooled_pred), pd.Series(pooled_fwd)), 4),
        "do_predict_rate": round(do_pred_rate, 3) if do_pred_rate is not None else None,
    }


def rolling_30d_pooled_ic() -> dict | None:
    """Convenience: pooled IC over the last 30 days at the CURRENT config's
    label horizon, using the currently-live predictions file."""
    horizon = label_period_candles()
    hp = load_predictions()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = pooled_ic(hp, horizon, since=cutoff)
    if result is not None:
        result["label_period_candles"] = horizon
    return result
