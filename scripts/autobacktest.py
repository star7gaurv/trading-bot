#!/usr/bin/env python3
"""
autobacktest.py v4 — Automated parameter grid search for FinBuddyFreqAI.

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

v4 changes (v6 strategy support)
---------------------------------
  - Added PATCH_RULES for trailing_offset and ml_exit_threshold (new v3 grid params)
  - trailing_offset patches trailing_stop_positive_offset in strategy
  - ml_exit_threshold patches the exit threshold in populate_exit_trend
  - Removed roi_multiplier from PATCH_RULES and CONFIG_PATCH_KEYS (confirmed dead lever)
  - Updated CSV headers to include new params, remove roi_multiplier

v3 fix: Temp-file strategy approach (unchanged)
---------------------------------------------
  Write patched strategy to /tmp/FinBuddyFreqAI_test.py (always writable).
  Pass --strategy-path /tmp to Freqtrade. Original strategy never touched.

Usage (Claude Code)
-------------------
  cd /home/ubuntu/var/www/html/trade
  git pull origin gaurav
  sudo chown -R ubuntu:ubuntu freqtrade/user_data/
  python3 scripts/autobacktest.py

Output
------
  _autobacktest_results.csv   — all runs with metrics (committed by Claude)
  stdout                      — progress + final PASS/FAIL summary
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

# Timerange is configurable via BACKTEST_TIMERANGE env var.
# Default = bear/spot legacy window. Bull futures campaign: 20240101-20250101
import os
BACKTEST_TIMERANGE = os.environ.get("BACKTEST_TIMERANGE", "20250101-20260401")


def load_grid():
    with open(GRID_FILE) as f:
        return json.load(f)


# ------------------------------------------------------------------ #
# Strategy patcher (v4: adds trailing_offset + ml_exit_threshold)     #
# ------------------------------------------------------------------ #

# v11 PATCH_RULES — strategy now uses LightGBMClassifier proba thresholds,
# not regression on &-s_close. Old regex matched zero locations — every grid
# combo ran on the unpatched strategy and produced 0 trades.
#
# v11 mapping:
#   ml_threshold       → entry confidence on proba_long / proba_short (default 0.55)
#                        Also bumps the bear-tighten 0.60 by the same delta.
#   ml_exit_threshold  → exit confidence on opposite-class proba (default 0.45)
#   stoploss           → class attr `stoploss = -0.08`
#   atr_threshold      → `dataframe["atr_ratio"] > 0.003`
#   trailing_offset    → DROPPED. v11 disables framework trailing
#                        (custom_stoploss owns the trail) so this lever is dead.
def _replace_after(pattern_with_prefix, value):
    """Replace numeric literal that follows the captured prefix(es)."""
    def repl(m):
        prefix = next((g for g in m.groups() if g is not None), "")
        return f"{prefix}{float(value)}"
    return repl

PATCH_RULES = {
    # Both 0.55 entry-confidence thresholds (long + short)
    "ml_threshold": (
        r"(proba_long\s*>\s*)0\.55|(proba_short\s*>\s*)0\.55",
        0,
    ),
    # Bear-tighten branch (0.60) — bumped by ml_threshold + 0.05 if present
    "ml_threshold_bear": (
        r"(proba_long\s*>\s*)0\.60",
        0,
    ),
    # Module-level class attribute stoploss
    "stoploss": (
        r"(^    stoploss\s*=\s*)(?:-[0-9.]+)",
        re.MULTILINE,
    ),
    # Both exit thresholds (0.45 default)
    "ml_exit_threshold": (
        r"(proba_long\s*>\s*)0\.45|(proba_short\s*>\s*)0\.45",
        0,
    ),
    # ATR ratio gate (default 0.003)
    "atr_threshold": (
        r"(dataframe\[\"atr_ratio\"\]\s*>\s*)0\.003",
        0,
    ),
}


def write_patched_strategy(original_path: Path, params: dict) -> Path:
    """
    v4: Read original strategy, apply params, write to /tmp.
    Returns path to temp file. Original is never modified.
    """
    original = original_path.read_text()
    patched = original

    # Auto-derive bear-tightened threshold from ml_threshold (preserve +0.05 gap)
    effective = dict(params)
    if "ml_threshold" in effective and "ml_threshold_bear" not in effective:
        effective["ml_threshold_bear"] = round(float(effective["ml_threshold"]) + 0.05, 4)

    for param, value in effective.items():
        if param not in PATCH_RULES:
            continue
        pattern, flags = PATCH_RULES[param]
        if not re.search(pattern, patched, flags):
            print(f"  [WARN] Patch for '{param}' found no match in strategy file.")
            continue
        patched, n = re.subn(pattern, _replace_after(pattern, value), patched, flags=flags)
        if n == 0:
            print(f"  [WARN] Patch for '{param}' applied 0 substitutions.")

    patched = patched.replace(
        "class FinBuddyFreqAI(IStrategy):",
        "class FinBuddyFreqAI_test(IStrategy):"
    )
    TEMP_STRATEGY_PATH.write_text(patched)
    return TEMP_STRATEGY_PATH


# ------------------------------------------------------------------ #
# Config patcher (patches backtest_config.json + docker cp)           #
# ------------------------------------------------------------------ #

BACKTEST_CONFIG_HOST = SCRIPT_DIR / "backtest_config.json"
TEMP_CONFIG_PATH = Path("/tmp/backtest_config_patched.json")
CONTAINER_CONFIG_PATH = "/freqtrade/scripts/backtest_config.json"


def write_patched_config(params: dict) -> None:
    """
    Patch backtest_config.json with stoploss from params.
    roi_multiplier removed (dead lever). Write to /tmp, docker cp to container.
    """
    with open(BACKTEST_CONFIG_HOST) as f:
        cfg = json.load(f)

    if "stoploss" in params:
        cfg["stoploss"] = float(params["stoploss"])

    # Remove minimal_roi override — let strategy control it
    cfg.pop("minimal_roi", None)

    with open(TEMP_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

    cp_proc = subprocess.run(
        ["docker", "cp", str(TEMP_CONFIG_PATH), f"freqtrade:{CONTAINER_CONFIG_PATH}"],
        capture_output=True, text=True, timeout=30
    )
    if cp_proc.returncode != 0:
        print(f"  [WARN] docker cp config failed: {cp_proc.stderr.strip()}")


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
# Backtest runner                                                      #
# ------------------------------------------------------------------ #

def run_backtest(config: dict, temp_strategy_path: Path) -> dict:
    """
    Run backtest using the temp strategy file.
    Passes --strategy-path /tmp so Freqtrade finds FinBuddyFreqAI_test.py.
    Returns dict with metrics.
    """
    parse_script = PROJECT_ROOT / config["parse_script"]
    results_dir_host = PROJECT_ROOT / config["backtest_results_path"]

    result = {
        "win_rate": None, "sharpe": None,
        "max_drawdown": None, "profit_factor": None,
        "total_profit": None, "trades": None,
        "raw_output": "", "error": None,
    }

    # Step 1: Download data (idempotent — skip if already fresh)
    try:
        subprocess.run(
            [
                "docker", "exec", "freqtrade",
                "freqtrade", "download-data",
                "--config", "/freqtrade/scripts/backtest_config.json",
                "--timerange", BACKTEST_TIMERANGE,
                "--timeframes", "5m", "15m", "1h", "4h", "1d",
                "--pairs", "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            ],
            capture_output=True, text=True, timeout=600
        )
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

    # Step 3: Run backtest
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
                # v11 expects LightGBMClassifier proba columns. backtest_config.json
                # already sets freqaimodel=LightGBMClassifier — don't override here
                # (FinBuddyLLMModel inherits from LightGBMRegressor, output schema mismatch).
                "--timerange", BACKTEST_TIMERANGE,
                "--timeframe", "15m",
                "--export", "trades",
                "--cache", "none",
            ],
            capture_output=True, text=True, timeout=1800
        )
        result["raw_output"] = bt_proc.stdout + bt_proc.stderr
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
    "run", "timestamp", "ml_threshold", "stoploss",
    "ml_exit_threshold", "atr_threshold",
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
    print(f"FinBuddy AutoBacktest Grid Search v4")
    print(f"Strategy: v6 (Option C — trailing stop + tighter ML exit)")
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

        # Write patched strategy to /tmp
        write_patched_strategy(strategy_path, params)
        print(f"  Temp strategy written to {TEMP_STRATEGY_PATH}")

        # Patch config (stoploss only, roi removed)
        write_patched_config(params)
        print(f"  Config patched: stoploss={params.get('stoploss')}")

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

    # Cleanup
    if TEMP_STRATEGY_PATH.exists():
        TEMP_STRATEGY_PATH.unlink()
    if TEMP_CONFIG_PATH.exists():
        TEMP_CONFIG_PATH.unlink()
    subprocess.run(
        ["docker", "cp", str(BACKTEST_CONFIG_HOST), f"freqtrade:{CONTAINER_CONFIG_PATH}"],
        capture_output=True, text=True, timeout=30
    )
    print("\nTemp files cleaned up. Original config restored in container.")

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
