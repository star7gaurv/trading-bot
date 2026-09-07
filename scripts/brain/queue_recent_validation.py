#!/usr/bin/env python3
"""
queue_recent_validation.py — daily "does anything actually work on TODAY's
market?" check (2026-09-07 session).

The 2026-09-07 diagnosis found the brain had never tested three things that
matter most:
  1. The EXACT config the live bot is actually running (LIVE_SEED_CONFIG_V23
     — most brain experiments used label_period_candles=12 / thresholds
     0.3/-0.3; live runs 6 / 0.7/-0.6 / K_SL=3.5).
  2. The brain's own default seed (SEED_CONFIG_V23) against the CURRENT
     market — every fixed window is 2024 or 2025 history.
  3. Whether the brain's current "best" candidates (from analyst_report.json,
     found by testing on those same fixed historical quarters) hold up on
     the actual last-90-days market at all.

This queues all three onto hypothesis_gen.py's RECENT_WINDOW_NAME
("recent_90d" — a window that recomputes to "today minus 90 days" every time
this script runs, so it never goes stale like a fixed calendar quarter does).
promote.py's RECENT_WINDOW_REQUIRED gate then blocks any future promotion of
a config that was tested here and failed (WR<50%) on the real current market.

Dedup: same (config_hash, window) pair already queued or logged → skipped,
same rule as generate_and_queue() (CLAUDE.md Fix 13).

Cron: daily, ahead of the other brain crons, so recent_90d's date keeps
sliding forward and the brain never stops checking itself against "now".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hypothesis_gen as hg  # noqa: E402
from experiment_log import queue_hypothesis, read_queue, read_log  # noqa: E402
from promote import _config_hash  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ANALYST_REPORT = ROOT / "finbuddy_memory/experiments/analyst_report.json"


def _already_covered() -> set[tuple[str, str]]:
    queued = {(_config_hash(r["config"]), r.get("window", "")) for r in read_queue()}
    logged = {(_config_hash(r["config"]), r.get("window", ""))
              for r in read_log() if r.get("status") in ("queued", "running", "completed")}
    return queued | logged


def main() -> int:
    win = hg.RECENT_WINDOW_NAME
    timerange = hg.WINDOWS[win]
    covered = _already_covered()
    queued_now = []

    candidates: list[tuple[dict, str, str]] = []  # (config, band, rationale)

    live_cfg = hg.LIVE_SEED_CONFIG_V23()
    candidates.append((
        live_cfg, "seed",
        "recent-market validation: EXACT live .env config (2026-09-07 gap — "
        "the brain had never tested what's actually trading)",
    ))

    candidates.append((
        dict(hg.SEED_CONFIG_V23), "seed",
        "recent-market validation: brain's own default seed vs the actual current market",
    ))

    if ANALYST_REPORT.exists():
        try:
            report = json.loads(ANALYST_REPORT.read_text())
            for key in ("best_bull", "best_bear", "best_overall"):
                cand = report.get("findings", {}).get(key) or report.get(key)
                cfg = (cand or {}).get("config")
                if cfg:
                    candidates.append((
                        dict(cfg), "seed",
                        f"recent-market validation: does analyst's {key} "
                        f"(found on {cand.get('window')}) hold up on the current market?",
                    ))
        except Exception as e:
            print(f"[queue_recent_validation] WARN: could not read analyst report: {e}",
                  file=sys.stderr)

    for cfg, band, rationale in candidates:
        cfg = hg._stamp_target_version(dict(cfg))
        key = (_config_hash(cfg), win)
        if key in covered:
            continue
        hid = queue_hypothesis(cfg, band, rationale, win, timerange)
        queued_now.append((hid, rationale))
        covered.add(key)

    print(f"[queue_recent_validation] window={win} ({timerange}) — "
          f"queued {len(queued_now)} new experiment(s)")
    for hid, rationale in queued_now:
        print(f"  {hid}: {rationale}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
