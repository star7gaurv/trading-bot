#!/usr/bin/env python3
"""
ic_monitor.py — weekly out-of-sample Information Coefficient report.

Measures whether the live model's predictions actually predict: Spearman rank
correlation between every live prediction in historic_predictions.pkl and the
realized forward return over the label horizon, per pair, for (a) the full
stored history and (b) a rolling 30-day window.

Output:
  - finbuddy_memory/analytics/pair_ic.json   (consumed by dashboards / edge_monitor.py)
  - Telegram digest (best/worst pairs, pooled IC)

Measurement only for the weekly per-pair breakdown — does NOT gate anything
itself. The system-wide pooled 30d number this script computes is now ALSO
consumed live (every 30min) by edge_monitor.py, which DOES gate new entries
when it goes non-positive — see that script + CLAUDE.md 2026-09-07 session.

Cron: weekly. Pure pandas — runs on the host, no docker needed.

2026-09-07: LABEL_PERIOD used to be hardcoded to 12 — went stale on
2026-06-21 when the live 1h switch moved label_period_candles to 6, so this
report silently measured the wrong horizon for ~2.5 months. Now reads it from
config.json via scripts/lib/live_predictions.py (same source the strategy's
own _label_period_candles() uses) so it can never drift again.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402
from lib.live_predictions import (  # noqa: E402
    label_period_candles, load_predictions, pair_ic, pooled_ic,
)

OUT_FILE = ROOT / "finbuddy_memory/analytics/pair_ic.json"


def main() -> int:
    label_period = label_period_candles()
    hp = load_predictions()

    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    report: dict = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "label_period_candles": label_period,
        "pairs": {},
    }
    for pair, df in hp.items():
        full = pair_ic(df, label_period)
        if full is None:
            continue
        recent = pair_ic(df, label_period, since=cutoff_30d)
        report["pairs"][pair] = {"full": full, "rolling_30d": recent}

    pooled = pooled_ic(hp, label_period)
    if pooled is not None:
        report["pooled"] = pooled
    pooled_30d = pooled_ic(hp, label_period, since=cutoff_30d)
    if pooled_30d is not None:
        report["pooled_30d"] = pooled_30d

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
            "Pooled IC (all-time)": pooled.get("ic") if pooled else "n/a",
            "Pooled IC (30d)": pooled_30d.get("ic") if pooled_30d else "n/a",
            "Pairs IC>0": f"{pos}/{len(ranked)}",
            "Best": best,
            "Worst": worst,
        },
        context=f"Spearman IC vs {label_period}-candle forward return "
                f"({pooled.get('n', 0) if pooled else 0} OOS predictions). "
                f"Full report: finbuddy_memory/analytics/pair_ic.json",
        silent=True,
    )
    print(f"[ic_monitor] wrote {OUT_FILE} — pooled IC="
          f"{pooled.get('ic') if pooled else None} (30d: "
          f"{pooled_30d.get('ic') if pooled_30d else None}) "
          f"over {len(ranked)} pairs, label_period={label_period}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
