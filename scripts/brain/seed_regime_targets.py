#!/usr/bin/env python3
"""seed_regime_targets.py — Regime-targeted brain seeding.

Finds the top-N best-performing configs from the experiment log and:
  1. Cross-seeds any windows not yet tested/queued for those configs.
  2. Reorders the queue so current-regime windows run first.

This accelerates promotion by:
  - Ensuring near-passing configs are tested on ALL 5 windows (not just the
    windows the brain happened to pick at random).
  - Front-loading the windows that match the live market regime (BEAR/BULL)
    so the brain accumulates the regime-specific passes needed for promotion
    as fast as possible (promotion gate: ≥2 bull AND ≥2 bear passing experiments).

Usage:
    python3 scripts/brain/seed_regime_targets.py [--top-n 5] [--regime auto] [--dry-run]
    python3 scripts/brain/brain_cli.py seed-regime [--top-n 5] [--regime auto] [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "brain"))

from experiment_log import (
    queue_hypothesis,
    read_queue,
    read_log,
    _config_signature,
    prioritize_regime_windows,
)
from hypothesis_gen import WINDOWS


def _score(metrics: dict | None) -> float:
    """Composite quality score for an experiment.

    0.4×Sharpe + 0.3×(WR − 0.5) + 0.3×profit_pct
    Higher is better. All three components are signed — a negative Sharpe
    or WR below 50% drags the score down.
    """
    if not metrics:
        return -1e9
    sharpe = metrics.get("sharpe") or 0.0
    wr     = metrics.get("wr")     or 0.0
    profit = metrics.get("profit_pct") or 0.0
    return 0.4 * sharpe + 0.3 * (wr - 0.5) + 0.3 * profit


def _get_current_regime() -> str:
    regime_file = ROOT / "finbuddy_memory" / "regimes" / "current.json"
    try:
        with regime_file.open() as f:
            data = json.load(f)
        return data.get("regime", "NEUTRAL").upper()
    except Exception:
        return "NEUTRAL"


def seed_regime_targets(
    top_n: int = 5,
    regime: str = "auto",
    dry_run: bool = False,
    min_trades: int = 3,
) -> dict:
    """Main seeding logic. Returns a summary dict suitable for printing.

    Args:
        top_n:      Number of unique top-scoring configs to cross-seed.
        regime:     "auto" reads current.json; or explicit "BEAR"/"BULL".
        dry_run:    If True, reports what would happen without writing anything.
        min_trades: Minimum trade count to consider an experiment eligible
                    (avoids seeding configs that barely fired).
    """
    if regime == "auto":
        regime = _get_current_regime()

    log   = read_log()
    queue = read_queue()

    # ── Phase 1: Find top-N unique configs ───────────────────────────────────
    # Filter: z-scored target only, completed, enough trades to trust metrics
    eligible = [
        r for r in log
        if r.get("status") == "completed"
        and r.get("config", {}).get("target_version") == "zscore"
        and (r.get("metrics") or {}).get("trades", 0) >= min_trades
    ]

    if not eligible:
        return {
            "regime": regime,
            "error": "No eligible zscore experiments with trades>0 in log",
            "seeded": 0,
            "reordered": 0,
        }

    # Group by config signature; track best-scoring entry per unique config
    sig_best:  dict[str, dict]  = {}
    sig_score: dict[str, float] = {}
    for r in eligible:
        sig   = _config_signature(r.get("config", {}))
        score = _score(r.get("metrics"))
        if sig not in sig_best or score > sig_score[sig]:
            sig_best[sig]  = r
            sig_score[sig] = score

    sorted_sigs = sorted(sig_best, key=lambda s: sig_score[s], reverse=True)
    top_sigs    = sorted_sigs[:top_n]

    # ── Phase 2: Cross-seed missing windows ──────────────────────────────────
    # Build the full set of (sig, window) pairs already covered
    covered: set[tuple[str, str]] = set()
    for entry in queue + log:
        sig = _config_signature(entry.get("config", {}))
        win = entry.get("window", "")
        if sig and win:
            covered.add((sig, win))

    seeded         = 0
    seeded_details = []

    for sig in top_sigs:
        best   = sig_best[sig]
        config = best.get("config", {})
        score  = sig_score[sig]
        lt     = config.get("long_threshold", "?")
        st     = config.get("short_threshold", "?")
        m      = best.get("metrics") or {}

        missing = [
            (win_name, tr)
            for win_name, tr in WINDOWS.items()
            if (sig, win_name) not in covered
        ]

        if not missing:
            continue

        for win_name, timerange in missing:
            rationale = (
                f"regime-seed: top-{top_n} config "
                f"(score={score:.3f} profit={m.get('profit_pct', 0):+.2f}% "
                f"WR={m.get('wr', 0)*100:.1f}% Sharpe={m.get('sharpe', 0):+.2f}) "
                f"src={best['hypothesis_id'][:8]} @ {best.get('window', '?')}"
            )
            if not dry_run:
                queue_hypothesis(
                    config=config,
                    band="seed",
                    rationale=rationale,
                    window=win_name,
                    timerange=timerange,
                    parent_id=best["hypothesis_id"],
                )
            seeded += 1
            seeded_details.append(f"lt={lt}/st={st} → {win_name}")

    # ── Phase 3: Reorder queue for current regime ─────────────────────────────
    if not dry_run:
        reordered = prioritize_regime_windows(regime)
    else:
        # Just count how many bear/bull entries are in the queue currently
        regime_key = regime.lower()
        reordered = sum(
            1 for e in queue
            if regime_key in e.get("window", "").lower()
        )

    # ── Phase 4: Build report ─────────────────────────────────────────────────
    top_configs_info = []
    for sig in top_sigs:
        best = sig_best[sig]
        m    = best.get("metrics") or {}
        top_configs_info.append({
            "sig_prefix": sig[:16],
            "score":      round(sig_score[sig], 4),
            "best_window": best.get("window"),
            "lt":          best.get("config", {}).get("long_threshold"),
            "st":          best.get("config", {}).get("short_threshold"),
            "k_sl":        best.get("config", {}).get("k_sl"),
            "k_tp":        best.get("config", {}).get("k_tp"),
            "profit_pct":  round(m.get("profit_pct", 0), 3),
            "wr":          round(m.get("wr", 0), 3),
            "sharpe":      round(m.get("sharpe", 0), 3),
            "trades":      m.get("trades", 0),
        })

    return {
        "regime":               regime,
        "dry_run":              dry_run,
        "eligible_experiments": len(eligible),
        "unique_configs":       len(sig_best),
        "top_n":                top_n,
        "top_configs":          top_configs_info,
        "seeded":               seeded,
        "seeded_details":       seeded_details,
        "reordered_to_front":   reordered,
        "queue_head_after":     None if dry_run else _peek_queue_head(5),
    }


def _peek_queue_head(n: int) -> list[dict]:
    """Return a summary of the first N queued experiments."""
    queue = read_queue()
    out = []
    for e in queue[:n]:
        cfg = e.get("config", {})
        out.append({
            "window": e.get("window"),
            "lt":     cfg.get("long_threshold"),
            "st":     cfg.get("short_threshold"),
            "band":   e.get("band"),
        })
    return out


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Regime-targeted brain seeding")
    p.add_argument("--top-n",   type=int, default=5,      help="Top-N configs to cross-seed (default 5)")
    p.add_argument("--regime",  default="auto",            help="BEAR|BULL|auto (default auto reads current.json)")
    p.add_argument("--min-trades", type=int, default=3,   help="Min trades for eligible experiment (default 3)")
    p.add_argument("--dry-run", action="store_true",       help="Report only — no writes")
    args = p.parse_args()

    result = seed_regime_targets(
        top_n=args.top_n,
        regime=args.regime,
        dry_run=args.dry_run,
        min_trades=args.min_trades,
    )
    print(json.dumps(result, indent=2))
