#!/usr/bin/env python3
"""
shadow_rule_extraction.py — interpretable rule extraction from Cortexa's own
profitable trade history (pattern borrowed from Vibe-Trading's "Shadow Account"
feature, adapted to this repo's conventions — see 2026-07-16 comparison).

Every entry-alpha attempt on this project so far has been a variant of "predict
the future return" (LightGBM regression, meta-labeling classifier, cross-sectional
ranking) — all independently confirmed dead (IC≈0.03-0.05, meta AUC=0.50, no
signal survives fees). This asks a different question: not "what will happen
next", but "what did Cortexa's own actual winning trades already have in
common". KMeans clusters the profitable trades, a shallow decision tree per
cluster extracts a human-readable entry_condition.

This is a MEASUREMENT/RESEARCH script. Read-only against the FreqTrade API,
writes only a Markdown report. It never touches queue.jsonl, the live
strategy, or any file the strategy reads. Any candidate rule this surfaces
MUST go through the normal hypothesis_gen.py -> runner.py backtest ->
promote.py pipeline like every other hypothesis before it could ever affect
live trading — this script has no fast path to production.

Usage (run inside the venv that has scikit-learn — see 2026-07-16 session,
host python3 does not have sklearn and PEP 668 blocks a bare pip install):
  /home/ubuntu/.finbuddy/venvs/research/bin/python3 scripts/research/shadow_rule_extraction.py
  ... --cohort exit_signal   # only exit_signal-exited trades (the ~90-100% WR cohort)
  ... --cohort all           # all closed trades
  ... --limit 3              # force the degenerate <5-profitable-trades path (testing)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from ft_creds import get_ft_auth  # noqa: E402

ROOT = Path("/home/ubuntu/var/www/html/trade")
API = "http://127.0.0.1:8080/api/v1"
REGIME_PARQUET = ROOT / "finbuddy_memory/regimes/historical_regime.parquet"
REPORT_DIR = ROOT / "finbuddy_memory/research"

MIN_PROFITABLE_TRADES = 5
MAX_RULES_PER_COHORT = 5


def fetch_closed_trades() -> pd.DataFrame:
    """Same pagination pattern as pair_performance.py:26-49."""
    import requests

    auth = get_ft_auth()
    trades: list[dict] = []
    offset = 0
    while True:
        r = requests.get(f"{API}/trades", auth=auth, params={"limit": 500, "offset": offset}, timeout=15)
        r.raise_for_status()
        data = r.json()
        batch = data["trades"]
        if not batch:
            break
        trades.extend(batch)
        if len(trades) >= data["total_trades"]:
            break
        offset += 500

    closed = [t for t in trades if not t["is_open"] and t.get("close_date")]
    df = pd.DataFrame(closed)
    df["open_date"] = pd.to_datetime(df["open_date"], utc=True)
    df["close_date"] = pd.to_datetime(df["close_date"], utc=True)
    return df


def attach_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Join regime-at-entry via the same historical_regime.parquet the strategy
    itself builds from (finbuddy_memory/regimes/historical_regime.parquet)."""
    if not REGIME_PARQUET.exists():
        df["regime_at_entry"] = "UNKNOWN"
        return df
    regime = pd.read_parquet(REGIME_PARQUET)[["date", "regime"]].sort_values("date")
    regime["date"] = regime["date"].astype("datetime64[us, UTC]")
    df = df.sort_values("open_date")
    df["open_date"] = df["open_date"].astype("datetime64[us, UTC]")
    merged = pd.merge_asof(
        df, regime, left_on="open_date", right_on="date", direction="backward"
    )
    merged["regime_at_entry"] = merged["regime"].fillna("UNKNOWN")
    return merged.drop(columns=["date", "regime"])


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["holding_hours"] = df["trade_duration_s"] / 3600.0
    df["pnl_pct"] = df["close_profit_pct"]
    df["entry_hour_utc"] = df["open_date"].dt.hour
    df["entry_weekday"] = df["open_date"].dt.weekday
    df["direction"] = np.where(df["is_short"], "short", "long")
    df["pair_short"] = df["pair"].str.replace("/USDT:USDT", "", regex=False)
    return df


def extract_rules(df: pd.DataFrame, cohort_name: str) -> list[str]:
    """KMeans (k auto 2-5 by silhouette) on profitable trades, shallow decision
    tree per cluster, decision path -> plain-English rule. Mirrors Vibe-Trading's
    extractor.py degrade-gracefully design (models.py / extractor.py, 2026-07-16
    comparison notes)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.tree import DecisionTreeClassifier, export_text

    profitable = df[df["pnl_pct"] > 0].copy()
    lines: list[str] = [f"### Cohort: {cohort_name}", ""]
    lines.append(f"Total trades in cohort: {len(df)}. Profitable: {len(profitable)}.")

    if len(profitable) < MIN_PROFITABLE_TRADES:
        lines.append(
            f"\n**Degenerate case**: fewer than {MIN_PROFITABLE_TRADES} profitable trades "
            "in this cohort — not enough data to cluster. No rule extracted."
        )
        return lines

    # Clustering uses outcome-shape features too (pnl_pct, holding_hours) — this is
    # intentional and NOT the leakage bug: it's finding sub-*types* of wins (e.g.
    # "quick clean scalps" vs "slow grinding runners"), same as the source design.
    # The DECISION TREE below must NOT see these — a tree trained on the trade's own
    # outcome to "predict" cluster membership defined by that same outcome is circular
    # (it just re-derives the pnl threshold, not anything knowable before the trade
    # closes). entry_time_cols is deliberately the only feature set the tree ever sees.
    clustering_numeric_cols = ["holding_hours", "pnl_pct", "entry_hour_utc", "entry_weekday"]
    entry_time_numeric_cols = ["entry_hour_utc", "entry_weekday"]
    cat_cols = ["pair_short", "direction", "regime_at_entry"]

    X_num = StandardScaler().fit_transform(profitable[clustering_numeric_cols])
    enc = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    X_cat = enc.fit_transform(profitable[cat_cols])
    X = np.hstack([X_num, X_cat])

    n = len(profitable)
    max_k = min(5, n - 1)
    if max_k < 2:
        lines.append("\n**Degenerate case**: fewer than 2 viable clusters possible. "
                      "Falling back to a single-cluster heuristic.")
        k = 1
    else:
        best_k, best_score = 2, -1.0
        for k_try in range(2, max_k + 1):
            km = KMeans(n_clusters=k_try, n_init=10, random_state=42).fit(X)
            if len(set(km.labels_)) < 2:
                continue
            score = silhouette_score(X, km.labels_)
            if score > best_score:
                best_k, best_score = k_try, score
        k = best_k
        lines.append(f"\nAuto-selected k={k} clusters (silhouette={best_score:.3f}).")

    if k == 1:
        # single-cluster heuristic: just summarize the profitable cohort directly
        lines.append("\n**Single-cluster summary (heuristic, no tree):**")
        lines.append(f"- Avg holding time: {profitable['holding_hours'].mean():.1f}h")
        lines.append(f"- Avg pnl: {profitable['pnl_pct'].mean():.2f}%")
        lines.append(f"- Most common pair: {profitable['pair_short'].mode().iloc[0]}")
        lines.append(f"- Most common regime: {profitable['regime_at_entry'].mode().iloc[0]}")
        lines.append(f"- Most common direction: {profitable['direction'].mode().iloc[0]}")
        return lines

    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
    profitable["cluster"] = km.labels_

    # Build an all-trades matrix (profitable + losing) labeled by cluster membership
    # (1 = in this profitable cluster, 0 = everything else including losers) so the
    # tree learns what distinguishes this winning cluster from the rest of the cohort
    # — using ONLY entry-time-knowable features (see note above on why pnl_pct/
    # holding_hours are excluded here even though they fed the clustering step).
    entry_scaler = StandardScaler().fit(profitable[entry_time_numeric_cols])
    X_all_num = entry_scaler.transform(df[entry_time_numeric_cols])
    X_all_cat = enc.transform(df[cat_cols])
    X_all = np.hstack([X_all_num, X_all_cat])
    feature_names = entry_time_numeric_cols + list(enc.get_feature_names_out(cat_cols))

    for c in range(k):
        cluster_trades = profitable[profitable["cluster"] == c]
        if len(cluster_trades) < 3:
            continue
        y = np.zeros(len(df))
        cluster_idx = set(profitable[profitable["cluster"] == c].index)
        y = df.index.to_series().isin(cluster_idx).astype(int).values

        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=3, random_state=42)
        tree.fit(X_all, y)

        # Quantify separability instead of just eyeballing the tree text: in-sample
        # precision/recall of the best leaf vs the cluster's base rate in the cohort.
        # If precision barely beats the base rate, the tree found no real signal —
        # it's just carving out a few overfit corners on a shallow imbalanced split.
        base_rate = y.mean()
        preds = tree.predict(X_all)
        if preds.sum() > 0:
            precision = (preds & y.astype(bool)).sum() / preds.sum()
        else:
            precision = 0.0
        lift = precision / base_rate if base_rate > 0 else 0.0

        lines.append(f"\n**Cluster {c}** ({len(cluster_trades)} trades, "
                      f"avg pnl {cluster_trades['pnl_pct'].mean():.2f}%, "
                      f"avg hold {cluster_trades['holding_hours'].mean():.1f}h):")
        lines.append(f"- Base rate (this cluster's share of the cohort): {base_rate*100:.1f}%")
        lines.append(f"- Tree in-sample precision when it predicts membership: {precision*100:.1f}% "
                      f"(lift {lift:.2f}x over base rate)")
        if lift < 1.5:
            lines.append("- **No meaningful entry-time signal found** — precision barely beats "
                          "chance. Consistent with this project's other findings (IC≈0.03-0.05, "
                          "meta-labeling AUC=0.50): entry-time features don't separate winners "
                          "from the rest, even with a completely different technique.")
        rule_text = export_text(tree, feature_names=feature_names, max_depth=3)
        lines.append("```")
        lines.append(rule_text.strip())
        lines.append("```")

    return lines


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cohort", choices=["exit_signal", "all", "both"], default="both")
    p.add_argument("--limit", type=int, default=None,
                    help="Truncate to first N trades (testing the degenerate path)")
    args = p.parse_args()

    print("Fetching closed trades from FreqTrade API...")
    df = fetch_closed_trades()
    print(f"Fetched {len(df)} closed trades.")

    if args.limit:
        df = df.head(args.limit)
        print(f"--limit applied: truncated to {len(df)} trades.")

    df = attach_regime(df)
    df = engineer_features(df)

    report_lines = [
        "# Shadow Rule Extraction Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Interpretable rule extraction (KMeans clustering + shallow decision trees) "
        "applied to Cortexa's own closed-trade history — a different technique class "
        "than the ML regression/classification approaches already exhausted on this "
        "project (meta-labeling AUC=0.50, cross-sectional IC negative, order-flow/OI/"
        "funding features all noise). Asks 'what did the winners already have in "
        "common' rather than 'predict the future return'.",
        "",
        "**Any candidate rule below is a hypothesis, not a conclusion.** It must go "
        "through the normal `hypothesis_gen.py` -> `runner.py` backtest -> "
        "`promote.py` gate pipeline like every other hypothesis before it could ever "
        "affect live trading. This script has no fast path to production.",
        "",
    ]

    cohorts_to_run = []
    if args.cohort in ("exit_signal", "both"):
        cohorts_to_run.append(("exit_signal only", df[df["exit_reason"] == "exit_signal"]))
    if args.cohort in ("all", "both"):
        cohorts_to_run.append(("all closed trades", df))

    for name, cohort_df in cohorts_to_run:
        print(f"\nExtracting rules for cohort: {name} ({len(cohort_df)} trades)...")
        report_lines.extend(extract_rules(cohort_df, name))
        report_lines.append("")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = REPORT_DIR / f"shadow_rule_extraction_{date_str}.md"
    out_path.write_text("\n".join(report_lines))
    print(f"\nReport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
