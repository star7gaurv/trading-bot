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
from experiment_log import summary_stats, best_by_metric, read_log, read_queue
from hypothesis_gen import queue_seed_if_empty, generate_and_queue
from runner import run_next
from promote import find_candidates, propose
from analyst import analyse


def cmd_status(_args) -> int:
    stats = summary_stats()
    print("== FinBuddy Brain Status ==")
    print(f"  Queued      : {stats['queued']}")
    print(f"  Completed   : {stats['completed']}")
    print(f"  Failed      : {stats['failed']}")
    print(f"  By band     : {stats['by_band']}")
    print(f"  Last result : {stats['last_completion']}")
    best = best_by_metric("profit_pct", min_trades=20)
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
    report = analyse(dry_run=args.dry_run, no_llm=args.no_llm)
    pruned  = report.get("pruned", 0)
    actions = report.get("actions", [])
    insight = report.get("llm_insight", "")
    print(f"\nPruned {pruned} dead experiments. Queued {len(actions)} targeted batches.")
    if insight:
        print(f"\nLLM insight: {insight}")
    return 0


def cmd_best(_args) -> int:
    best = best_by_metric("profit_pct", min_trades=20)
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

    a = sub.add_parser("analyse", help="self-diagnose experiment results, prune queue, inject targeted hypotheses")
    a.add_argument("--dry-run", action="store_true", help="report only, no queue changes")
    a.add_argument("--no-llm",  action="store_true", help="skip DeepSeek call")
    a.set_defaults(func=cmd_analyse)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
