#!/usr/bin/env python3
"""
edge_monitor.py — the autonomous "am I actually working right now?" circuit
breaker (2026-09-07 session).

Why this exists: the 2026-09-07 diagnosis found the system already measures
its own failure honestly and continuously — walk_forward.py's grade() has
correctly returned pass=False on the live config for 197 STRAIGHT runs since
2026-06-05 (three months), and the live model's rolling IC has been ~0 since
the 2026-08-25 regime flip — but NOTHING reads that verdict and acts on it.
Trading has continued unchanged through the entire losing streak. CLAUDE.md's
core mandate is a brain that "dynamically changes parameters to adjust
tuning itself" — measuring failure without responding to it is not that.

What this script does (every 30 min, cheap — no docker, no backtest):
  1. Reads the live model's rolling 30-day pooled IC at the model's ACTUAL
     current label horizon (via lib/live_predictions.py — single source of
     truth, config.json feature_parameters.label_period_candles).
  2. Reads the consecutive walk-forward FAIL streak from walkforward_results/
     summary.json files (walk_forward.py already computes pass/fail
     correctly — grade() — this just counts how many times in a row it's
     been False).
  3. Sets gate_active=True (block NEW entries only — see strategy side,
     never touches exit/management logic) when EITHER:
       - live 30d pooled IC <= FREQAI_EDGE_GATE_IC_MIN (default 0.0), with a
         minimum sample size so a data gap can't trip it, OR
       - WF fail streak >= FREQAI_EDGE_GATE_WF_STREAK (default 5, ~2-3 days
         of daily WF runs)
  4. Writes finbuddy_memory/analytics/edge_state.json — read live by the
     strategy (CortexaAI_v23._load_edge_gate(), LIVE/DRY-RUN runmode only —
     see that method's docstring for why it must never affect backtests).
  5. Sends a Telegram alert ONLY on a state FLIP (not every run) so this is
     signal, not noise.

This is a circuit breaker, not a fix: gate_active does not create edge, it
stops the bot from taking new directional risk while there measurably isn't
any, while leaving existing positions to their normal exits. It is on by
default (FREQAI_EDGE_GATE=1 in the strategy), same posture as the existing
daily-loss-limit / daily-flatten circuit breakers, because "don't open new
risk on a measured-zero edge" cannot make the live system worse than it is
today — every historical loss this session diagnosed happened because this
control did not exist.
"""
from __future__ import annotations

import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402
from lib.live_predictions import rolling_30d_pooled_ic  # noqa: E402

OUT_FILE = ROOT / "finbuddy_memory/analytics/edge_state.json"
WF_RESULTS_DIR = ROOT / "walkforward_results"

IC_MIN_SAMPLE = 300          # below this, a data gap could produce a spurious IC
DEFAULT_IC_MIN = 0.0
DEFAULT_WF_STREAK_MIN = 5


def _env_float(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    import os
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def wf_fail_streak() -> tuple[int, str | None, str | None]:
    """Count consecutive pass=False summaries, newest-first, stopping at the
    first pass=True (or the end of history). Returns
    (streak, since_run_id, last_pass_run_id)."""
    files = sorted(
        glob.glob(str(WF_RESULTS_DIR / "*/summary.json")),
        key=lambda p: Path(p).stat().st_mtime,
    )
    streak = 0
    since_run = None
    last_pass_run = None
    for f in reversed(files):  # newest first
        try:
            s = json.loads(Path(f).read_text())
        except Exception:
            continue
        run_id = Path(f).parent.name
        if s.get("pass") is True:
            last_pass_run = run_id
            break
        if s.get("pass") is False:
            streak += 1
            since_run = run_id
        # pass is None (malformed/partial run) — skip, doesn't break the streak
    return streak, since_run, last_pass_run


def main() -> int:
    generated = datetime.now(timezone.utc).isoformat()

    ic_min = _env_float("FREQAI_EDGE_GATE_IC_MIN", DEFAULT_IC_MIN)
    wf_streak_min = _env_int("FREQAI_EDGE_GATE_WF_STREAK", DEFAULT_WF_STREAK_MIN)

    ic_report = None
    try:
        ic_report = rolling_30d_pooled_ic()
    except Exception as e:
        print(f"[edge_monitor] WARN: could not compute live IC: {e}", file=sys.stderr)

    streak, since_run, last_pass_run = wf_fail_streak()

    reasons = []
    ic_val = ic_report.get("ic") if ic_report else None
    ic_n = ic_report.get("n") if ic_report else 0
    if ic_report is not None and ic_n >= IC_MIN_SAMPLE and ic_val is not None and ic_val <= ic_min:
        reasons.append(
            f"live 30d IC {ic_val:+.4f} <= {ic_min:+.2f} (n={ic_n}, "
            f"horizon={ic_report.get('label_period_candles')} candles)"
        )
    if streak >= wf_streak_min:
        reasons.append(f"{streak} consecutive walk-forward FAILs (since {since_run})")

    gate_active = bool(reasons)

    # Read previous state to detect a flip (for alerting only).
    prev_active = None
    try:
        prev = json.loads(OUT_FILE.read_text())
        prev_active = prev.get("gate_active")
    except Exception:
        pass

    state = {
        "generated": generated,
        "gate_active": gate_active,
        "reasons": reasons,
        "live_ic_30d": ic_val,
        "live_ic_30d_n": ic_n,
        "live_ic_30d_do_predict_rate": ic_report.get("do_predict_rate") if ic_report else None,
        "label_period_candles": ic_report.get("label_period_candles") if ic_report else None,
        "wf_fail_streak": streak,
        "wf_fail_streak_since": since_run,
        "wf_last_pass_run": last_pass_run,
        "thresholds": {"ic_min": ic_min, "wf_streak_min": wf_streak_min},
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(state, indent=2))

    print(f"[edge_monitor] gate_active={gate_active} ic_30d={ic_val} "
          f"(n={ic_n}) wf_fail_streak={streak} reasons={reasons}")

    if prev_active is not None and prev_active != gate_active:
        if gate_active:
            send(
                Subsystem.WATCHDOG, Status.ACTION,
                "Edge gate ACTIVATED — new entries paused",
                fields={
                    "Live IC (30d)": f"{ic_val:+.4f}" if ic_val is not None else "n/a",
                    "WF fail streak": streak,
                    "Reasons": "; ".join(reasons),
                },
                context="No new long/short entries will open until the model's measured "
                        "edge recovers. Open trades are unaffected — normal exits still fire. "
                        "Set FREQAI_EDGE_GATE=0 in freqtrade/.env to override.",
                action="Investigate before overriding — this fired because the system's own "
                       "measurements (live IC, walk-forward) say the current config has no edge.",
            )
        else:
            send(
                Subsystem.WATCHDOG, Status.OK,
                "Edge gate CLEARED — entries resumed",
                fields={
                    "Live IC (30d)": f"{ic_val:+.4f}" if ic_val is not None else "n/a",
                    "WF fail streak": streak,
                },
                context="Measured edge recovered above threshold; new entries allowed again.",
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
