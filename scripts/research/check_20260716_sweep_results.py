#!/usr/bin/env python3
"""
One-off (cron-scheduled, self-removing) checker for the two backtest sweeps
queued 2026-07-16 to diagnose the post-07-08 losing streak:
  1. Entry-threshold re-sweep at live K_SL=3.5/K_TP=3.0 geometry (12 experiments)
  2. K_SL re-test at 2.5/3.0 (8 experiments)

Reads finbuddy_memory/experiments/{queue,log}.jsonl, summarizes completion status
and results for both sweeps, cross-checks promote.py's find_candidates() for any
new promotable config, and sends a Telegram report. Fires once via a self-cleaning
crontab entry (removes its own line after running) rather than a recurring cron.

Read-only against everything except sending the Telegram message and editing the
crontab to remove its own entry — never touches queue.jsonl/log.jsonl/live config.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "brain"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from experiment_log import read_log, read_queue  # noqa: E402
from telegram_template import send as tg_send, Subsystem, Status  # noqa: E402

CRON_MARKER = "check_20260716_sweep_results.py"

SWEEP1_COMBOS = {(lt, st) for lt in (0.7, 0.9, 1.1) for st in (-0.8, -1.0, -1.2)}
SWEEP1_WINDOWS = {"bear_2026Q1", "bull_2024Q4"}
SWEEP2_KSL = {2.5, 3.0}
SWEEP2_WINDOWS = {"bull_2024Q1", "bull_2024Q4", "bear_2025Q1", "bear_2026Q1"}

# Live baseline for reference (already-completed experiments at the exact live config)
BASELINE_KEY = (0.7, -0.6, 3.5, 3.0)


def _is_sweep1(cfg: dict) -> bool:
    return (
        cfg.get("k_sl") == 3.5 and cfg.get("k_tp") == 3.0
        and cfg.get("target_version") == "zscore"
        and (cfg.get("long_threshold"), cfg.get("short_threshold")) in SWEEP1_COMBOS
    )


def _is_sweep2(cfg: dict) -> bool:
    return (
        cfg.get("k_sl") in SWEEP2_KSL and cfg.get("k_tp") == 3.0
        and cfg.get("long_threshold") == 0.7 and cfg.get("short_threshold") == -0.6
        and cfg.get("target_version") == "zscore"
    )


def _fmt_row(r: dict, key_desc: str) -> str:
    m = r.get("metrics") or {}
    return (f"  {key_desc:<22} win={r.get('window'):<12} trades={m.get('trades','?'):>4} "
            f"wr={m.get('wr', 0)*100:.1f}% pf={m.get('pf', 0):.3f} "
            f"profit={m.get('profit_pct', 0):+.2f}%")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                    help="print the report but skip the Telegram send and crontab self-clean")
    args = p.parse_args()

    log = read_log()
    queue = read_queue()

    sweep1_log = [r for r in log if _is_sweep1(r.get("config", {}))]
    sweep2_log = [r for r in log if _is_sweep2(r.get("config", {}))]
    sweep1_queue = [r for r in queue if _is_sweep1(r.get("config", {}))]
    sweep2_queue = [r for r in queue if _is_sweep2(r.get("config", {}))]

    lines = ["Cortexa sweep-results check (2026-07-16 sweeps, 24h later)", ""]

    lines.append(f"Sweep 1 (threshold re-sweep, 12 queued): "
                 f"{sum(1 for r in sweep1_log if r['status']=='completed')} completed, "
                 f"{sum(1 for r in sweep1_log if r['status']=='scout_failed')} scout_failed, "
                 f"{len(sweep1_queue)} still queued")
    for r in sorted([r for r in sweep1_log if r["status"] == "completed"],
                     key=lambda r: -(r.get("metrics") or {}).get("pf", 0)):
        cfg = r["config"]
        lines.append(_fmt_row(r, f"lt={cfg['long_threshold']} st={cfg['short_threshold']}"))

    lines.append("")
    lines.append(f"Sweep 2 (K_SL re-test, 8 queued): "
                 f"{sum(1 for r in sweep2_log if r['status']=='completed')} completed, "
                 f"{sum(1 for r in sweep2_log if r['status']=='scout_failed')} scout_failed, "
                 f"{len(sweep2_queue)} still queued")
    for r in sorted([r for r in sweep2_log if r["status"] == "completed"],
                     key=lambda r: -(r.get("metrics") or {}).get("pf", 0)):
        cfg = r["config"]
        lines.append(_fmt_row(r, f"k_sl={cfg['k_sl']}"))

    all_completed = [r for r in sweep1_log + sweep2_log if r["status"] == "completed"]
    best = max(all_completed, key=lambda r: (r.get("metrics") or {}).get("pf", 0), default=None)
    baseline_pf = 0.84  # live PF since 07-08, from the 07-16 diagnosis session

    lines.append("")
    if best:
        best_pf = (best.get("metrics") or {}).get("pf", 0)
        lines.append(f"Best PF found so far: {best_pf:.3f} "
                     f"({'beats' if best_pf > baseline_pf else 'does NOT beat'} "
                     f"live baseline PF={baseline_pf})")
    else:
        lines.append("No experiments from either sweep have completed yet.")

    # Cross-check promote.py's actual candidate-finding logic (read-only import)
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
        title="Sweep results check (24h)",
        fields={},
        context=report,
        action="Reply in chat if you want any candidate applied — nothing is auto-promoted.",
        silent=False,
    )

    # Self-clean: remove this script's own line from crontab now that it has run.
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
