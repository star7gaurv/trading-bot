#!/usr/bin/env python3
"""
One-off (cron-scheduled, self-removing) checker for the progress_cut/probe_scale
experiments queued 2026-07-17 — the first real tests of either mechanism, after
fixing their 3-layer env-forwarding gap (runner.py/promote.py/docker-compose.yml)
the same day. 16 experiments total: 6 progress_cut candle-timing, 6 probe_scale
fraction, 4 combined, all at the live K_SL=3.5/K_TP=3.0/LT=0.7/ST=-0.6 geometry.

Reads finbuddy_memory/experiments/{queue,log}.jsonl, summarizes completion status
and results, cross-checks promote.py's find_candidates() for any new promotable
config, and sends a Telegram report. Fires once via a self-cleaning crontab entry
(removes its own line after running) rather than a recurring cron.

Read-only against everything except sending the Telegram message and editing the
crontab to remove its own entry — never touches queue.jsonl/log.jsonl/live config.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "brain"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from experiment_log import read_log, read_queue  # noqa: E402
from telegram_template import send as tg_send, Subsystem, Status  # noqa: E402

CRON_MARKER = "check_20260717_progress_probe_results.py"

LIVE_GEOMETRY = dict(k_sl=3.5, k_tp=3.0, long_threshold=0.7, short_threshold=-0.6)


def _is_progress_cut_only(cfg: dict) -> bool:
    return (
        cfg.get("progress_cut") is True and not cfg.get("probe_scale")
        and cfg.get("target_version") == "zscore"
        and all(cfg.get(k) == v for k, v in LIVE_GEOMETRY.items())
    )


def _is_probe_scale_only(cfg: dict) -> bool:
    return (
        cfg.get("probe_scale") is True and not cfg.get("progress_cut")
        and cfg.get("target_version") == "zscore"
        and all(cfg.get(k) == v for k, v in LIVE_GEOMETRY.items())
    )


def _is_combined(cfg: dict) -> bool:
    return (
        cfg.get("progress_cut") is True and cfg.get("probe_scale") is True
        and cfg.get("target_version") == "zscore"
        and all(cfg.get(k) == v for k, v in LIVE_GEOMETRY.items())
    )


def _fmt_row(r: dict, key_desc: str) -> str:
    m = r.get("metrics") or {}
    return (f"  {key_desc:<30} win={r.get('window'):<12} trades={m.get('trades','?'):>4} "
            f"wr={m.get('wr', 0)*100:.1f}% pf={m.get('pf', 0):.3f} "
            f"profit={m.get('profit_pct', 0):+.2f}%")


def _summarize(log: list, queue: list, matcher, label: str, expected_n: int) -> tuple[list, list]:
    log_rows = [r for r in log if matcher(r.get("config", {}))]
    queue_rows = [r for r in queue if matcher(r.get("config", {}))]
    completed = [r for r in log_rows if r["status"] == "completed"]
    failed = [r for r in log_rows if r["status"] == "scout_failed"]
    return completed, failed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                    help="print the report but skip the Telegram send and crontab self-clean")
    args = p.parse_args()

    log = read_log()
    queue = read_queue()

    lines = ["FinBuddy progress_cut/probe_scale results (2026-07-17 sweeps)", ""]
    all_completed = []

    for matcher, label, key_fn, expected_n in [
        (_is_progress_cut_only, "PROGRESS_CUT only", lambda cfg: f"candles={cfg.get('progress_cut_candles')}", 6),
        (_is_probe_scale_only, "PROBE_SCALE only", lambda cfg: f"frac={cfg.get('probe_fraction')}", 6),
        (_is_combined, "Combined (both)", lambda cfg: f"candles={cfg.get('progress_cut_candles')} frac={cfg.get('probe_fraction')}", 4),
    ]:
        completed, failed = _summarize(log, queue, matcher, label, expected_n)
        queue_rows = [r for r in queue if matcher(r.get("config", {}))]
        lines.append(f"{label} ({expected_n} queued): {len(completed)} completed, "
                     f"{len(failed)} scout_failed, {len(queue_rows)} still queued")
        for r in sorted(completed, key=lambda r: -(r.get("metrics") or {}).get("pf", 0)):
            lines.append(_fmt_row(r, key_fn(r["config"])))
        lines.append("")
        all_completed.extend(completed)

    baseline_pf = 0.84  # live PF since 07-08
    best_lever_pf = 0.870  # best from the 07-16 threshold/K_SL sweeps (also below baseline-beating threshold)

    if all_completed:
        best = max(all_completed, key=lambda r: (r.get("metrics") or {}).get("pf", 0))
        best_pf = (best.get("metrics") or {}).get("pf", 0)
        lines.append(f"Best PF found: {best_pf:.3f} "
                     f"(live baseline={baseline_pf}, best from 07-16 threshold/K_SL sweeps={best_lever_pf})")
        if best_pf > 1.0:
            lines.append("*** ABOVE BREAKEVEN — worth a closer look, not just a lift over baseline ***")
    else:
        lines.append("No progress_cut/probe_scale experiments have completed yet.")

    try:
        import promote  # type: ignore
        candidates = promote.find_candidates()
        lines.append(f"\npromote.py find_candidates(): {len(candidates)} candidate(s) surfaced "
                     "(would trigger a Telegram APPLY prompt on next 07:00 scan)")
    except Exception as e:
        lines.append(f"\npromote.py find_candidates() check failed: {e}")

    report = "\n".join(lines)
    print(report)

    if args.dry_run:
        print("\n[--dry-run] skipping Telegram send and crontab self-clean")
        return 0

    tg_send(
        subsystem=Subsystem.BRAIN_CYCLE,
        status=Status.INFO,
        title="progress_cut / probe_scale results",
        fields={},
        context=report,
        action="Reply in chat if you want any candidate applied — nothing is auto-promoted.",
        silent=False,
    )

    try:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True).stdout
        remaining = "\n".join(l for l in current.splitlines() if CRON_MARKER not in l)
        subprocess.run(["crontab", "-"], input=remaining + "\n", text=True, check=True)
        print("Removed self from crontab.")
    except Exception as e:
        print(f"WARNING: failed to self-clean crontab entry: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
