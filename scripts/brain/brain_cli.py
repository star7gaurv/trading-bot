#!/usr/bin/env python3
"""
brain_cli.py — single entry point for the FinBuddy autonomous brain.

Subcommands:
  status     — print current queue / log summary
  seed       — queue the seed config on all windows (idempotent)
  generate   — generate safe + aggressive variants, queue them
  run        — pop one (or N) hypotheses from queue, run them, log results
  scan       — find promotion candidates, send Telegram alert if any
  best       — show the current best-known config by profit
  analyse    — self-diagnose results, prune dead queue entries, inject targeted hypotheses

Cron deployment (5 entries):
  */30 * * * *  python /home/ubuntu/var/www/html/trade/scripts/brain/brain_cli.py run --max 1
  0    */6 * * * python /home/ubuntu/var/www/html/trade/scripts/brain/brain_cli.py generate
  30   */6 * * * python /home/ubuntu/var/www/html/trade/scripts/brain/brain_cli.py analyse
  0    7   * * * python /home/ubuntu/var/www/html/trade/scripts/brain/brain_cli.py scan
  0    0   * * * python /home/ubuntu/var/www/html/trade/scripts/brain/brain_cli.py status
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_log import summary_stats, best_by_metric, read_log, read_queue, queue_hypothesis
from hypothesis_gen import queue_seed_if_empty, generate_and_queue, WINDOWS
from runner import run_next
from promote import find_candidates, propose, _config_hash
# Fix 14 (2026-05-22): analyst import moved inside cmd_analyse() so an analyst.py
# import error only breaks 'analyse' subcommand, not run/generate/scan/seed.


def cmd_status(_args) -> int:
    stats = summary_stats()
    print("== FinBuddy Brain Status ==")
    print(f"  Queued      : {stats['queued']}")
    print(f"  Completed   : {stats['completed']}")
    print(f"  Failed      : {stats['failed']}")
    print(f"  By band     : {stats['by_band']}")
    print(f"  Last result : {stats['last_completion']}")
    best = best_by_metric("profit_pct", min_trades=10)
    if best:
        m = best["metrics"]
        arch = best.get("config", {}).get("arch", "?")
        print(f"\n  Best so far : profit={m['profit_pct']}% WR={m['wr']*100:.1f}% Sharpe={m['sharpe']}")
        print(f"  Hypothesis  : {best['hypothesis_id']}  ({arch}, {best['band']}, {best['window']})")
        print(f"  Rationale   : {best['rationale']}")
    return 0


def cmd_seed(_args) -> int:
    n = queue_seed_if_empty()
    print(f"Queued {n} seed hypotheses (0 if log/queue already had entries)")
    return 0


def cmd_generate(args) -> int:
    n = generate_and_queue(safe_n=args.safe, aggressive_n=args.aggr,
                            windows=args.windows.split(",") if args.windows else None)
    print(f"Queued {n} new hypotheses (safe={args.safe} × aggr={args.aggr} × windows)")
    return 0


def cmd_run(args) -> int:
    completed = run_next(max_runs=args.max)
    print(f"Completed {completed} runs.")
    return 0


def cmd_scan(_args) -> int:
    cands = find_candidates()
    if not cands:
        print("No promotion candidates.")
        return 0
    propose(cands[0])
    return 0


def cmd_analyse(args) -> int:
    from analyst import analyse   # Fix 14: lazy import — analyst errors don't break other commands
    report = analyse(dry_run=args.dry_run, no_llm=args.no_llm)
    pruned  = report.get("pruned", 0)
    actions = report.get("actions", [])
    insight = report.get("llm_insight", "")
    print(f"\nPruned {pruned} dead experiments. Queued {len(actions)} targeted batches.")
    if insight:
        print(f"\nLLM insight: {insight}")
    return 0


def cmd_requeue(args) -> int:
    """Force-queue runs for given config_hash(es) to reach 2 bull + 2 bear samples.

    Added 2026-05-19. Lets the operator unblock single-shot cross-window winners
    that the promotion gate refuses for lack of sample count.
    """
    target_n = args.target
    hashes = args.hashes
    log = read_log()
    queue = read_queue()

    # Build (hash → most recent completed config) lookup
    hash_to_config: dict[str, dict] = {}
    for r in log:
        cfg = r.get("config")
        if not cfg:
            continue
        h = _config_hash(cfg)
        hash_to_config[h] = cfg  # last-write wins → most recent
    # Also check queued (might be needed if a hash only exists pending)
    for r in queue:
        cfg = r.get("config")
        if not cfg:
            continue
        h = _config_hash(cfg)
        hash_to_config.setdefault(h, cfg)

    # Count existing (hash, window) in log+queue
    from collections import defaultdict
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in log + queue:
        cfg = r.get("config")
        if not cfg:
            continue
        h = _config_hash(cfg)
        w = r.get("window", "")
        counts[(h, w)] += 1

    print(f"== requeue (target {target_n} per window per hash) ==")
    print(f"{'hash':14s}  " + "  ".join(f"{w:14s}" for w in WINDOWS) + "  queued_now")
    total_queued = 0
    for h in hashes:
        if h not in hash_to_config:
            print(f"  {h}  ⚠ no completed run with this hash — skipped")
            continue
        cfg = hash_to_config[h]
        per_window_added = {}
        for window_name, timerange in WINDOWS.items():
            existing = counts[(h, window_name)]
            need = max(0, target_n - existing)
            for _ in range(need):
                queue_hypothesis(
                    config=cfg,
                    band="safe",
                    rationale=f"manual requeue: reach {target_n}+{target_n} sample count",
                    window=window_name,
                    timerange=timerange,
                )
            per_window_added[window_name] = (existing, need)
            total_queued += need
        cells = "  ".join(
            f"{existing}→{existing + need:2d}".ljust(14)
            for existing, need in (per_window_added[w] for w in WINDOWS)
        )
        added = sum(n for _, n in per_window_added.values())
        print(f"  {h}  {cells}  +{added}")
    print(f"-- Total queued: {total_queued} --")
    return 0


def cmd_best(_args) -> int:
    best = best_by_metric("profit_pct", min_trades=10)
    if not best:
        print("No completed experiments yet.")
        return 0
    print(json.dumps(best, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FinBuddy autonomous brain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("seed").set_defaults(func=cmd_seed)

    g = sub.add_parser("generate")
    g.add_argument("--safe", type=int, default=4)
    g.add_argument("--aggr", type=int, default=6)
    g.add_argument("--windows", default=None, help="comma-separated window names")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run")
    r.add_argument("--max", type=int, default=1)
    r.set_defaults(func=cmd_run)

    sub.add_parser("scan").set_defaults(func=cmd_scan)
    sub.add_parser("best").set_defaults(func=cmd_best)

    rq = sub.add_parser("requeue",
        help="force-queue runs for given config_hash(es) to reach 2 bull + 2 bear")
    rq.add_argument("hashes", nargs="+", help="config_hash values (12-hex) from `brain best` or analysis")
    rq.add_argument("--target", type=int, default=2,
        help="target count per window (default 2, matches promote.py MIN_*_RUNS)")
    rq.set_defaults(func=cmd_requeue)

    a = sub.add_parser("analyse", help="self-diagnose experiment results, prune queue, inject targeted hypotheses")
    a.add_argument("--dry-run", action="store_true", help="report only, no queue changes")
    a.add_argument("--no-llm",  action="store_true", help="skip DeepSeek call")
    a.set_defaults(func=cmd_analyse)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
