#!/usr/bin/env python3
"""
autobacktest.py — Automated parameter grid search for FinBuddyFreqAI.

Purpose
-------
Instead of manually tweaking one parameter at a time and re-running the
backtest by hand (expensive in AI tokens and time), this script:
  1. Reads a parameter grid from autobacktest_grid.json
  2. For each combination: patches FinBuddyFreqAI.py, clears the FreqAI
     prediction cache, runs run_backtest.sh, and parses the result
  3. Logs every run to _autobacktest_results.csv
  4. Stops as soon as it finds a combination that meets ALL acceptance criteria
  5. Prints a clear summary at the end

Engineering principle
---------------------
  "If it can be automated with code, do it once and don't waste AI on it."
This script encodes the manual tune-and-retry loop we were doing by hand.

Usage (Claude Code)
-------------------
  cd /home/ubuntu/var/www/html/trade/freqtrade
  git pull origin gaurav
  python3 scripts/autobacktest.py

Output
------
  _autobacktest_results.csv   — all runs with metrics (committed by Claude)
  stdout                      — progress + final PASS/FAIL summary

After running
-------------
  - Claude Code: commit _autobacktest_results.csv, update graveyard/winners
    memory files, update CLAUDE_HANDOFF.md with outcome
  - Perplexity:  read CSV, promote winner params into strategy permanently

Dependencies
------------
  Python 3.8+, subprocess, json, csv, re, itertools, shutil, pathlib
  No external packages required — all stdlib.

Notes
-----
  - Script patches FinBuddyFreqAI.py in-place for each run, then restores
    the original at the end (safe even on CTRL+C via try/finally).
  - Prediction cache is cleared between runs so FreqAI always uses fresh
    predictions (the bug that made stoploss changes look like no-ops).
  - Grid is defined in autobacktest_grid.json. Edit that file, not this one.
"""

import json
import csv
import re
import subprocess
import itertools
import shutil
import sys
from pathlib import Path
from datetime import datetime

# ------------------------------------------------------------------ #
# Config                                                               #
# ------------------------------------------------------------------ #

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
GRID_FILE = SCRIPT_DIR / "autobacktest_grid.json"


def load_grid():
    with open(GRID_FILE) as f:
        return json.load(f)


# ------------------------------------------------------------------ #
# Strategy patcher                                                     #
# Patches specific lines in FinBuddyFreqAI.py without full rewrite.   #
# DRY: all param → regex mappings live here, not scattered.           #
# ------------------------------------------------------------------ #

PATCH_RULES = {
    "ml_threshold": (
        r"(\(dataframe\[\"&-s_close\"\]\s*>\s*)([0-9.]+)(\).*# v4)",
        lambda v: rf"\g<1>{v}\g<3>",
    ),
    "rsi_entry_ceiling": (
        r"(\(dataframe\[\"rsi_14\"\]\s*<\s*)([0-9]+)(\).*# v4)",
        lambda v: rf"\g<1>{int(v)}\g<3>",
    ),
    "trend_ema_period_1h": (
        r"(informative_1h\[\"ema_50_1h\"\]\s*=\s*ta\.EMA\(\s*informative_1h,\s*timeperiod=)([0-9]+)(\s*\))",
        lambda v: rf"\g<1>{int(v)}\g<3>",
    ),
}


def patch_strategy(strategy_path: Path, params: dict) -> str:
    """Apply param dict to strategy file. Returns original content for restore."""
    original = strategy_path.read_text()
    patched = original
    for param, value in params.items():
        if param not in PATCH_RULES:
            continue
        pattern, replacement_fn = PATCH_RULES[param]
        new_text = re.sub(pattern, replacement_fn(value), patched)
        if new_text == patched:
            print(f"  [WARN] Patch for '{param}' found no match in strategy file.")
        patched = new_text
    strategy_path.write_text(patched)
    return original


def restore_strategy(strategy_path: Path, original_content: str):
    """Restore strategy file to original content."""
    strategy_path.write_text(original_content)


# ------------------------------------------------------------------ #
# Cache cleaner                                                        #
# Must run before every backtest or FreqAI reuses stale predictions.  #
# ------------------------------------------------------------------ #

def clear_cache(config: dict):
    """Clear FreqAI prediction cache and previous backtest results."""
    models_path = PROJECT_ROOT / config["model_cache_path"]
    results_path = PROJECT_ROOT / config["backtest_results_path"]

    # Clear prediction feather files (not trained models — those are reusable)
    cleared = 0
    for feather in models_path.rglob("predictions_backtest_*.feather"):
        feather.unlink()
        cleared += 1

    # Clear previous backtest result ZIPs (gitignored, safe to delete)
    for f in results_path.iterdir():
        if f.name != ".gitkeep":
            try:
                f.unlink()
            except Exception:
                pass

    print(f"  Cache cleared: {cleared} prediction file(s) removed.")


# ------------------------------------------------------------------ #
# Backtest runner                                                      #
# ------------------------------------------------------------------ #

def run_backtest(config: dict) -> dict:
    """
    Run run_backtest.sh and parse_backtest.py.
    Returns dict with keys: win_rate, sharpe, max_drawdown, profit_factor,
    total_profit, trades, raw_output, error.
    """
    backtest_script = PROJECT_ROOT / config["backtest_script"]
    parse_script = PROJECT_ROOT / config["parse_script"]

    result = {
        "win_rate": None, "sharpe": None,
        "max_drawdown": None, "profit_factor": None,
        "total_profit": None, "trades": None,
        "raw_output": "", "error": None,
    }

    # Run backtest
    try:
        proc = subprocess.run(
            ["bash", str(backtest_script)],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=1800
        )
        result["raw_output"] = proc.stdout + proc.stderr
        if proc.returncode != 0:
            result["error"] = f"run_backtest.sh exited with code {proc.returncode}"
            return result
    except subprocess.TimeoutExpired:
        result["error"] = "Backtest timed out (>30 min)"
        return result

    # Parse results
    try:
        parse_proc = subprocess.run(
            ["python3", str(parse_script), "--json"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60
        )
        metrics = json.loads(parse_proc.stdout)
        result.update(metrics)
    except Exception as e:
        result["error"] = f"parse_backtest.py failed: {e}"

    return result


# ------------------------------------------------------------------ #
# Pass/fail checker                                                    #
# ------------------------------------------------------------------ #

def check_pass(metrics: dict, criteria: dict) -> bool:
    """Return True only if ALL acceptance criteria are met."""
    try:
        return (
            metrics["win_rate"] > criteria["win_rate"]
            and metrics["sharpe"] > criteria["sharpe"]
            and metrics["max_drawdown"] < criteria["max_drawdown"]
            and metrics["profit_factor"] > criteria["profit_factor"]
        )
    except (TypeError, KeyError):
        return False


# ------------------------------------------------------------------ #
# CSV logger                                                           #
# ------------------------------------------------------------------ #

CSV_HEADERS = [
    "run", "timestamp", "ml_threshold", "trend_ema_period_1h", "rsi_entry_ceiling",
    "trades", "win_rate", "sharpe", "max_drawdown", "profit_factor",
    "total_profit", "pass", "error",
]


def append_csv(csv_path: Path, row: dict):
    """Append one result row to the CSV. Creates file with headers if needed."""
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ------------------------------------------------------------------ #
# Main grid search loop                                                #
# ------------------------------------------------------------------ #

def main():
    config = load_grid()
    grid = config["grid"]
    criteria = config["acceptance_criteria"]
    strategy_path = PROJECT_ROOT / config["strategy_file"]
    csv_path = PROJECT_ROOT / config["results_csv"]

    # Build all param combinations
    param_names = list(grid.keys())
    param_values = list(grid.values())
    combos = list(itertools.product(*param_values))
    total = len(combos)

    print(f"\n{'='*60}")
    print(f"FinBuddy AutoBacktest Grid Search")
    print(f"Grid: {total} combinations to test")
    print(f"Acceptance: {criteria}")
    print(f"Results CSV: {csv_path.name}")
    print(f"{'='*60}\n")

    # Save original strategy content for restore
    original_strategy = strategy_path.read_text()
    winner = None

    try:
        for run_num, combo in enumerate(combos, 1):
            params = dict(zip(param_names, combo))
            label = ", ".join(f"{k}={v}" for k, v in params.items())
            print(f"\n[{run_num}/{total}] Testing: {label}")

            # Patch strategy
            patch_strategy(strategy_path, params)

            # Clear cache
            clear_cache(config)

            # Run backtest
            print("  Running backtest...")
            metrics = run_backtest(config)

            # Check pass/fail
            passed = check_pass(metrics, criteria) if not metrics["error"] else False
            status = "PASS ✅" if passed else "FAIL ❌"
            print(f"  Result: {status}")
            if not metrics["error"]:
                print(f"  Trades={metrics['trades']} | WR={metrics['win_rate']}% | "
                      f"Sharpe={metrics['sharpe']} | DD={metrics['max_drawdown']}% | "
                      f"PF={metrics['profit_factor']}")
            else:
                print(f"  Error: {metrics['error']}")

            # Log to CSV
            row = {
                "run": run_num,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                **params,
                **{k: metrics.get(k) for k in
                   ["trades", "win_rate", "sharpe", "max_drawdown",
                    "profit_factor", "total_profit"]},
                "pass": passed,
                "error": metrics.get("error") or "",
            }
            append_csv(csv_path, row)

            if passed:
                winner = params.copy()
                winner.update({k: metrics.get(k) for k in
                               ["trades", "win_rate", "sharpe",
                                "max_drawdown", "profit_factor"]})
                print(f"\n{'='*60}")
                print("WINNER FOUND — stopping grid search.")
                print(json.dumps(winner, indent=2))
                print(f"{'='*60}")
                break

    finally:
        # Always restore original strategy (even on CTRL+C or error)
        restore_strategy(strategy_path, original_strategy)
        print("\nStrategy file restored to original.")

    # Final summary
    print(f"\n{'='*60}")
    if winner:
        print("GRID SEARCH COMPLETE — WINNER FOUND")
        print(f"Best params: {winner}")
        print(f"\nNext step for Perplexity: apply winner params permanently to strategy.")
    else:
        print(f"GRID SEARCH COMPLETE — NO WINNER in {total} combinations.")
        print(f"All results saved to: {csv_path.name}")
        print("Next step for Perplexity: review CSV, expand grid or rethink approach.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
