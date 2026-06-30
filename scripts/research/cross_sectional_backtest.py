#!/usr/bin/env python3
"""
cross_sectional_backtest.py — does the model's RANKING skill make money?

Thesis (2026-06-30 analysis): the 1h model has strong cross-sectional IC
(top-pair AVAX +0.52, top-8 mean +0.32) but is directionally biased long, so
absolute-threshold trading either deadlocks or bleeds. A market-neutral book —
long the highest-predicted pairs, short the lowest, dollar-neutral — should
harvest the ranking edge while cancelling market direction (and regime).

This is a MEASUREMENT script. It reads the live model's out-of-sample predictions
(historic_predictions.pkl, ~113 days of genuinely OOS hourly preds) and the close
prices stored alongside them, and simulates several books:

  A) X-sectional  all pairs           long top-N / short bottom-N, dollar-neutral
  B) X-sectional  positive-IC pairs    same, but universe gated to pairs with IC>gate
  C) long-only    top-N                (no short leg)
  D) short-only   bottom-N             (approximates the current live short-bias)
  E) long-all     equal weight         (pure market beta benchmark)

For each: gross + net (fees) total return, annualized Sharpe, hit rate, max DD.

Pure pandas/numpy. No live impact, no orders. Read-only.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
PKL = ROOT / "freqtrade/user_data/models/finbuddy_v23_tf1h_1782044602/historic_predictions.pkl"

TAKER_FEE = 0.0005       # 0.05% per transaction (futures taker)
HOLD_CANDLES = 12        # holding period = label horizon (12h on 1h)
TOP_N = 5                # long top-N / short bottom-N
IC_GATE = 0.05           # positive-IC universe threshold
ANNUALIZE = np.sqrt(365 * 24 / HOLD_CANDLES)   # non-overlapping H-candle periods/yr


def load_panel():
    """Return (pred_wide, close_wide) aligned on a common hourly index.

    CRITICAL (2026-06-30): only do_predict==1 rows are trustworthy. The
    do_predict==0 rows (DI/SVM outliers, the bulk of stored history) carry
    lookahead that fabricates a +0.55 IC — confirmed against ic_monitor.py which
    filters the same way. Predictions on do_predict==0 candles are set to NaN so
    they can never enter a book or a rank.
    """
    d = pickle.load(open(PKL, "rb"))
    preds, closes = {}, {}
    for pair, df in d.items():
        if "&-future_return" not in df.columns or "date_pred" not in df.columns:
            continue
        s = df.copy()
        s["date_pred"] = pd.to_datetime(s["date_pred"], utc=True)
        s = s.sort_values("date_pred").drop_duplicates("date_pred").set_index("date_pred")
        base = pair.split("/")[0]
        pred = pd.to_numeric(s["&-future_return"], errors="coerce")
        dp = pd.to_numeric(s["do_predict"], errors="coerce")
        pred = pred.where(dp == 1)            # leak guard: drop do_predict==0
        preds[base] = pred
        closes[base] = pd.to_numeric(s["close_price"], errors="coerce").replace(0, np.nan)
    P = pd.DataFrame(preds).sort_index()
    C = pd.DataFrame(closes).sort_index()
    return P, C


def forward_returns(C: pd.DataFrame, h: int) -> pd.DataFrame:
    return C.shift(-h) / C - 1.0


def cross_sectional_ic(P, F, min_pairs=10):
    """The thesis metric: at each timestamp, Spearman(predictions across pairs,
    forward returns across pairs). Positive mean ⇒ the model ranks pairs by
    relative forward return ⇒ a market-neutral long-top/short-bottom book has edge.
    Uses every clean timestamp (not just the rebalance grid) — the most data we have."""
    ics = []
    for t in P.index:
        row = P.loc[t].dropna()
        if len(row) < min_pairs:
            continue
        fwd = F.loc[t, row.index].dropna()
        common = row.index.intersection(fwd.index)
        if len(common) < min_pairs:
            continue
        ics.append(row[common].rank().corr(fwd[common].rank()))
    ics = pd.Series(ics)
    return ics


def per_pair_ic(P, F):
    """Spearman IC per pair over the whole sample (for the IC gate)."""
    ic = {}
    for c in P.columns:
        a, b = P[c], F[c]
        m = a.notna() & b.notna()
        if m.sum() > 30:
            ic[c] = a[m].rank().corr(b[m].rank())
    return pd.Series(ic).sort_values(ascending=False)


def run_book(P, F, idx, universe, top_n, mode="ls"):
    """Simulate a book over rebalance timestamps `idx`.

    mode: 'ls' long-short neutral | 'long' long-only | 'short' short-only | 'all' long-all
    Returns a Series of per-period NET returns.
    """
    rets = []
    for t in idx:
        row = P.loc[t, universe].dropna()
        fwd = F.loc[t, universe]
        if len(row) < max(2 * top_n, 4):
            continue
        ranked = row.sort_values(ascending=False)
        longs = ranked.index[:top_n]
        shorts = ranked.index[-top_n:]
        lr = fwd[longs].mean()
        sr = fwd[shorts].mean()
        if mode == "ls":
            gross = lr - sr                        # $1 long / $1 short
            fee = 2 * top_n * 2 * TAKER_FEE / top_n  # open+close, both legs, per-unit
        elif mode == "long":
            gross = lr
            fee = top_n * 2 * TAKER_FEE / top_n
        elif mode == "short":
            gross = -sr
            fee = top_n * 2 * TAKER_FEE / top_n
        else:  # all
            gross = fwd.mean()
            fee = 0.0
        rets.append(gross - fee)
    return pd.Series(rets)


def per_pair_timing(P, F, idx, universe, mode="long"):
    """Per-pair ABSOLUTE timing (not cross-sectional): for each pair, take a
    position when its own prediction is extreme vs its own rolling median.
    long: enter long when pred > rolling-median; long/short: also short when below.
    Equal-weight across whatever pairs are active each period. This tests whether
    the strong per-pair time-series IC is monetisable as a timing signal."""
    med = P[universe].rolling(240, min_periods=40).median()
    rets = []
    for t in idx:
        preds = P.loc[t, universe].dropna()
        if len(preds) == 0:
            continue
        m = med.loc[t, preds.index]
        fwd = F.loc[t, preds.index]
        sig = (preds - m).dropna()
        fwd = fwd.reindex(sig.index)
        longs = sig[sig > 0].index
        shorts = sig[sig < 0].index
        legs = []
        if len(longs):
            legs.append(fwd[longs].mean() - 2 * TAKER_FEE)
        if mode == "ls" and len(shorts):
            legs.append(-fwd[shorts].mean() - 2 * TAKER_FEE)
        if legs:
            rets.append(np.mean(legs))
    return pd.Series(rets)


def stats(r: pd.Series) -> dict:
    if len(r) == 0:
        return {"n": 0}
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    sharpe = (r.mean() / r.std() * ANNUALIZE) if r.std() > 0 else 0.0
    return {
        "n": len(r),
        "total_%": (eq.iloc[-1] - 1) * 100,
        "sharpe": sharpe,
        "hit_%": (r > 0).mean() * 100,
        "avg_bps": r.mean() * 1e4,
        "maxDD_%": dd * 100,
    }


def fmt(name, s):
    if s.get("n", 0) == 0:
        print(f"  {name:32} no data")
        return
    print(f"  {name:32} ret {s['total_%']:+7.1f}%  Sharpe {s['sharpe']:+5.2f}  "
          f"hit {s['hit_%']:4.1f}%  avg {s['avg_bps']:+6.1f}bps  DD {s['maxDD_%']:5.1f}%  n={s['n']}")


def main():
    P, C = load_panel()
    F = forward_returns(C, HOLD_CANDLES)
    print(f"Panel: {P.shape[1]} pairs · {P.shape[0]} hourly preds · "
          f"{P.index.min()} → {P.index.max()}")
    print(f"Holding {HOLD_CANDLES}h · top/bottom {TOP_N} · fee {TAKER_FEE*100:.3f}%/txn\n")

    # THE thesis metric — cross-sectional IC over all clean timestamps
    xic = cross_sectional_ic(P, F)
    if len(xic) > 2:
        tstat = xic.mean() / (xic.std() / np.sqrt(len(xic)))
        print(f"CROSS-SECTIONAL IC (does ranking pairs work?):")
        print(f"  mean {xic.mean():+.4f} · median {xic.median():+.4f} · "
              f">0 in {(xic>0).mean()*100:.0f}% of {len(xic)} timestamps · t-stat {tstat:+.2f}")
        print(f"  → {'SUPPORTS' if tstat>2 else 'inconclusive/weak for'} the market-neutral thesis\n")

    ic = per_pair_ic(P, F)
    pos_ic = list(ic[ic > IC_GATE].index)
    print("Per-pair IC (this sample):")
    print("  " + "  ".join(f"{k}:{v:+.2f}" for k, v in ic.head(8).items()))
    print("  " + "  ".join(f"{k}:{v:+.2f}" for k, v in ic.tail(5).items()))
    print(f"  positive-IC universe (IC>{IC_GATE}): {len(pos_ic)} pairs → {pos_ic}\n")

    # non-overlapping rebalance timestamps (avoid label overlap)
    idx = P.index[::HOLD_CANDLES]
    idx = idx[:-1]  # last has no forward return
    allp = list(P.columns)

    print("BOOKS (net of fees):")
    fmt("A) X-sectional all pairs L/S", stats(run_book(P, F, idx, allp, TOP_N, "ls")))
    if len(pos_ic) >= 2 * TOP_N:
        fmt("B) X-sectional pos-IC L/S", stats(run_book(P, F, idx, pos_ic, TOP_N, "ls")))
    elif len(pos_ic) >= 6:
        n2 = max(2, len(pos_ic) // 3)
        fmt(f"B) X-sectional pos-IC L/S (n={n2})",
            stats(run_book(P, F, idx, pos_ic, n2, "ls")))
    fmt("C) long-only top-N", stats(run_book(P, F, idx, allp, TOP_N, "long")))
    fmt("D) short-only bottom-N (current)", stats(run_book(P, F, idx, allp, TOP_N, "short")))
    fmt("E) long-all (market beta)", stats(run_book(P, F, idx, allp, TOP_N, "all")))
    fmt("F) per-pair timing long (all)", stats(per_pair_timing(P, F, idx, allp, "long")))
    fmt("G) per-pair timing L/S (all)", stats(per_pair_timing(P, F, idx, allp, "ls")))
    hi = list(ic[ic > 0.20].index)
    if len(hi) >= 4:
        fmt(f"H) per-pair timing long (IC>0.2, {len(hi)}p)",
            stats(per_pair_timing(P, F, idx, hi, "long")))

    # sensitivity: top_n sweep on the best (pos-IC L/S if available else all)
    uni = pos_ic if len(pos_ic) >= 8 else allp
    label = "pos-IC" if uni is pos_ic else "all"
    print(f"\nTop-N sweep (X-sectional L/S, {label} universe):")
    for n in (2, 3, 4, 5):
        if len(uni) >= 2 * n:
            fmt(f"  N={n}", stats(run_book(P, F, idx, uni, n, "ls")))


if __name__ == "__main__":
    main()
