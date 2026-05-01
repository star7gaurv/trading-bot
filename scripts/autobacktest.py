#!/usr/bin/env python3
"""
autobacktest.py v3 — Automated parameter grid search for FinBuddyFreqAI.

Purpose
-------
Instead of manually tweaking one parameter at a time and re-running the
backtest by hand (expensive in AI tokens and time), this script:
  1. Reads a parameter grid from autobacktest_grid.json
  2. For each combination: writes a TEMP COPY of the strategy (no in-place
     patching — avoids all opc ownership/chmod issues), runs run_backtest.sh
     pointing to the temp file, and parses the result
  3. Logs every run to _autobacktest_results.csv
  4. Stops as soon as it finds a combination that meets ALL acceptance criteria
  5. Prints a clear summary at the end

Engineering principle
---------------------
  "If it can be automated with code, do it once and don't waste AI on it."

v3 fix: Temp-file strategy approach
-------------------------------------
  Previous approach: patch FinBuddyFreqAI.py in-place, run backtest, restore.
  Problem: Docker volume resets file ownership to opc between runs.
           chmod without sudo fails silently → all 12 combos test same params.
  v3 fix: Write patched strategy to /tmp/FinBuddyFreqAI_test.py (always
          writable). Pass --strategy-path /tmp to Freqtrade so it finds the
          temp file. Original strategy never touched.

Usage (Claude Code)
-------------------
  cd /home/ubuntu/var/www/html/trade
  git pull origin gaurav
  sudo chown ubuntu:ubuntu freqtrade/user_data/strategies/FinBuddyFreqAI.py
  sudo chown -R ubuntu:ubuntu freqtrade/user_data/backtest_results/
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

Bug history
-----------
  v1: Docker volume resets ownership to opc → write_text PermissionError.
  v2: _ensure_writable() runs chmod 666 via subprocess (no sudo → still fails).
  v3: Temp-file approach — write to /tmp, point Freqtrade there. No chmod needed.
"""

import json
import csv
import re
import subprocess
import itertools
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone

# ------------------------------------------------------------------ #
# Config                                                               #
# ------------------------------------------------------------------ #

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
GRID_FILE = SCRIPT_DIR / "autobacktest_grid.json"

# Temp strategy file written to /tmp — always writable regardless of opc ownership
TEMP_STRATEGY_PATH = Path("/tmp/FinBuddyFreqAI_test.py")


def load_grid():
    with open(GRID_FILE) as f:
        return json.load(f)


# ------------------------------------------------------------------ #
# Strategy patcher (v3: writes to temp file, never touches original)  #
# ------------------------------------------------------------------ #

PATCH_RULES = {
    "ml_threshold": (
        r"(dataframe\[\"&-s_close\"\]\s*>\s*)([0-9.]+)(\)\s*# v5)",
        lambda v: rf"\g<1>{v}\g<3>",
    ),
    "rsi_entry_ceiling": (
        r"(\(dataframe\[\"rsi_14\"\]\s*<\s*)([0-9]+)(\))",
        lambda v: rf"\g<1>{int(v)}\g<3>",
    ),
    "stoploss": (
        r"(stoploss\s*=\s*)(-[0-9.]+)",
        lambda v: rf"\g<1>{float(v)}",
    ),
    "roi_multiplier": (
        # Scales the 0-minute ROI entry: "0": X.XX
        r'(\"0\":\s*)([0-9.]+)',
        lambda v: rf"\g<1>{float(v)}",
    ),
    "atr_threshold": (
        r"(dataframe\[\"atr_ratio\"\]\s*>\s*)([0-9.]+)",
        lambda v: rf"\g<1>{float(v)}",
    ),
}


def write_patched_strategy(original_path: Path, params: dict) -> Path:
    """
    v3: Read original strategy, apply params, write to /tmp.
    Returns path to temp file. Original is never modified.
    """
    original = original_path.read_text()
    patched = original

    for param, value in params.items():
        if param not in PATCH_RULES:
            continue
        pattern, replacement_fn = PATCH_RULES[param]
        if not re.search(pattern, patched):
            print(f"  [WARN] Patch for '{param}' found no match in strategy file.")
            continue
        patched = re.sub(pattern, replacement_fn(value), patched)

    patched = patched.replace(
        "class FinBuddyFreqAI(IStrategy):",
        "class FinBuddyFreqAI_test(IStrategy):"
    )
    TEMP_STRATEGY_PATH.write_text(patched)
    return TEMP_STRATEGY_PATH


# ------------------------------------------------------------------ #
# Cache cleaner                                                        #
# ------------------------------------------------------------------ #

def clear_cache(config: dict):
    """Clear FreqAI prediction cache and previous backtest results."""
    models_path = PROJECT_ROOT / config["model_cache_path"]
    results_path = PROJECT_ROOT / config["backtest_results_path"]

    cleared = 0
    for feather in models_path.rglob("predictions_backtest_*.feather"):
        feather.unlink()
        cleared += 1

    for f in results_path.iterdir():
        if f.name != ".gitkeep":
            try:
                f.unlink()
            except Exception:
                pass

    print(f"  Cache cleared: {cleared} prediction file(s) removed.")


# ------------------------------------------------------------------ #
# Backtest runner (v3: passes --strategy-path /tmp)                   #
# ------------------------------------------------------------------ #

def run_backtest(config: dict, temp_strategy_path: Path) -> dict:
    """
    Run backtest using the temp strategy file.
    Passes --strategy-path /tmp so Freqtrade finds FinBuddyFreqAI_test.py.
    Returns dict with metrics.
    """
    parse_script = PROJECT_ROOT / config["parse_script"]
    results_dir_host = PROJECT_ROOT / config["backtest_results_path"]
    results_dir_container = "/freqtrade/user_data/backtest_results"

    result = {
        "win_rate": None, "sharpe": None,
        "max_drawdown": None, "profit_factor": None,
        "total_profit": None, "trades": None,
        "raw_output": "", "error": None,
    }

    # Step 1: Download data (idempotent — skip if already fresh)
    try:
        dl_proc = subprocess.run(
            [
                "docker", "exec", "freqtrade",
                "freqtrade", "download-data",
                "--config", "/freqtrade/scripts/backtest_config.json",
                "--timerange", "20250101-20260401",
                "--timeframes", "5m", "15m", "1h",
                "--pairs", "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            ],
            capture_output=True, text=True, timeout=600
        )
        # Non-zero is ok here — data may already be fresh
    except subprocess.TimeoutExpired:
        result["error"] = "Data download timed out"
        return result

    # Step 2: Copy temp strategy into container
    try:
        cp_proc = subprocess.run(
            ["docker", "cp", str(temp_strategy_path), "freqtrade:/tmp/FinBuddyFreqAI_test.py"],
            capture_output=True, text=True, timeout=30
        )
        if cp_proc.returncode != 0:
            result["error"] = f"docker cp failed: {cp_proc.stderr.strip()}"
            return result
    except Exception as e:
        result["error"] = f"docker cp exception: {e}"
        return result

    # Step 3: Run backtest using temp strategy in /tmp inside container
    try:
        bt_proc = subprocess.run(
            [
                "docker", "exec",
                "-e", "GROQ_API_KEY=disabled_for_backtest",
                "freqtrade",
                "freqtrade", "backtesting",
                "--config", "/freqtrade/scripts/backtest_config.json",
                "--strategy", "FinBuddyFreqAI_test",
                "--strategy-path", "/tmp",
                "--freqaimodel", "FinBuddyLLMModel",
                "--timerange", "20250101-20260401",
                "--timeframe", "15m",
                "--export", "trades",
            ],
            capture_output=True, text=True, timeout=1800
        )
        result["raw_output"] = bt_proc.stdout + bt_proc.stderr
        # Don't check returncode — parse result file instead
    except subprocess.TimeoutExpired:
        result["error"] = "Backtest timed out (>30 min)"
        return result

    # Step 4: Parse results
    try:
        parse_proc = subprocess.run(
            ["python3", str(parse_script), "--json", "--results-dir", str(results_dir_host)],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60
        )
        if not parse_proc.stdout.strip():
            result["error"] = f"parse_backtest.py empty output: {parse_proc.stderr[:300]}"
            return result
        metrics = json.loads(parse_proc.stdout)
        result.update(metrics)
    except Exception as e:
        result["error"] = f"parse_backtest.py failed: {e}"

    return result


# ------------------------------------------------------------------ #
# Pass/fail checker                                                    #
# ------------------------------------------------------------------ #

def check_pass(metrics: dict, criteria: dict) -> bool:
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
    "run", "timestamp", "ml_threshold", "stoploss", "roi_multiplier", "atr_threshold",
    "trades", "win_rate", "sharpe", "max_drawdown", "profit_factor",
    "total_profit", "pass", "error",
]


def append_csv(csv_path: Path, row: dict):
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

    param_names = list(grid.keys())
    param_values = list(grid.values())
    combos = list(itertools.product(*param_values))
    total = len(combos)

    print(f"\n{'='*60}")
    print(f"FinBuddy AutoBacktest Grid Search v3")
    print(f"Grid: {total} combinations to test")
    print(f"Acceptance: {criteria}")
    print(f"Results CSV: {csv_path.name}")
    print(f"Temp strategy: {TEMP_STRATEGY_PATH}")
    print(f"{'='*60}\n")

    winner = None

    for run_num, combo in enumerate(combos, 1):
        params = dict(zip(param_names, combo))
        label = ", ".join(f"{k}={v}" for k, v in params.items())
        print(f"\n[{run_num}/{total}] Testing: {label}")

        # Write patched strategy to /tmp (no opc ownership issues)
        write_patched_strategy(strategy_path, params)
        print(f"  Temp strategy written to {TEMP_STRATEGY_PATH}")

        # Clear cache
        clear_cache(config)

        # Run backtest
        print("  Running backtest...")
        metrics = run_backtest(config, TEMP_STRATEGY_PATH)

        # Check pass/fail
        passed = check_pass(metrics, criteria) if not metrics["error"] else False
        status = "PASS ✅" if passed else "FAIL ❌"
        print(f"  Result: {status}")
        if not metrics["error"]:
            print(f"  Trades={metrics['trades']} | WR={metrics['win_rate']} | "
                  f"Sharpe={metrics['sharpe']} | DD={metrics['max_drawdown']} | "
                  f"PF={metrics['profit_factor']}")
        else:
            print(f"  Error: {metrics['error']}")

        # Log to CSV
        row = {
            "run": run_num,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
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

    # Cleanup temp file
    if TEMP_STRATEGY_PATH.exists():
        TEMP_STRATEGY_PATH.unlink()
        print("\nTemp strategy file cleaned up.")

    # Final summary
    print(f"\n{'='*60}")
    if winner:
        print("GRID SEARCH COMPLETE — WINNER FOUND")
        print(f"Best params: {winner}")
        print("\nNext step for Perplexity: apply winner params permanently to strategy.")
    else:
        print(f"GRID SEARCH COMPLETE — NO WINNER in {total} combinations.")
        print(f"All results saved to: {csv_path.name}")
        print("Next step for Perplexity: review CSV, expand grid or rethink approach.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
