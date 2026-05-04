#!/usr/bin/env python3
"""
FinBuddy — Task 1.3 Backtest Result Parser

Reads the latest backtest JSON from user_data/backtest_results/
and prints a PASS/FAIL grade against FinBuddy acceptance criteria.

Usage:
    python scripts/parse_backtest.py
    python scripts/parse_backtest.py --results-dir /freqtrade/user_data/backtest_results

Acceptance criteria (Task 1.3):
    Win rate       > 50%
    Sharpe ratio   > 0.5
    Max drawdown   < 20%
    Profit factor  > 1.2
"""

import json
import os
import sys
import argparse
import zipfile
from pathlib import Path
from datetime import datetime

# --------------------------------------------------------------------------- #
# Acceptance thresholds (Task 1.3 definition of done)
# --------------------------------------------------------------------------- #
CRITERIA = {
    "win_rate":       {"threshold": 0.50, "op": "gt", "label": "Win Rate",       "fmt": ".1%"},
    "sharpe":         {"threshold": 0.50, "op": "gt", "label": "Sharpe Ratio",   "fmt": ".3f"},
    "max_drawdown":   {"threshold": 0.20, "op": "lt", "label": "Max Drawdown",   "fmt": ".1%"},
    "profit_factor":  {"threshold": 1.20, "op": "gt", "label": "Profit Factor",  "fmt": ".3f"},
}

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def find_latest_result(results_dir: Path):
    """
    Find and return parsed backtest data dict from the most recent result.
    FreqTrade stores results as backtest-result-*.zip (not plain JSON).
    Returns the parsed dict so callers don't need to know about the ZIP format.
    """
    zips = sorted(
        results_dir.glob("backtest-result-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    if zips:
        if not any(a == "--json" for a in sys.argv):
            print(f"  Parsing: {zips[0].name}")
        with zipfile.ZipFile(zips[0]) as z:
            # The first .json file inside the ZIP is the backtest result
            json_names = [n for n in z.namelist() if n.endswith(".json") and "config" not in n]
            if not json_names:
                print(f"{RED}[×] No JSON found inside {zips[0].name}{RESET}")
                sys.exit(1)
            return json.loads(z.read(json_names[0]))

    print(f"{RED}[×] No backtest-result-*.zip found in {results_dir}{RESET}")
    print("    Run the backtest first: ./scripts/run_backtest.sh")
    sys.exit(1)


def extract_metrics(data: dict) -> dict:
    """
    Extract key metrics from FreqTrade backtest JSON.
    FreqTrade stores results under data['strategy']['FinBuddyFreqAI'] or
    data['strategy_comparison'][0] depending on version.
    """
    metrics = {}

    # Try new-style FreqTrade JSON (v3+)
    strategy_data = None
    if "strategy" in data:
        strat_block = data["strategy"]
        if "FinBuddyFreqAI" in strat_block:
            strategy_data = strat_block["FinBuddyFreqAI"]
        else:
            # Take the first available strategy
            strategy_data = next(iter(strat_block.values()), None)

    if strategy_data is None and "results" in data:
        strategy_data = data["results"]

    if strategy_data is None:
        print(f"{RED}[×] Cannot parse backtest JSON structure. Dumping keys:{RESET}")
        print(json.dumps(list(data.keys()), indent=2))
        sys.exit(1)

    # --- Win rate ---
    wins  = strategy_data.get("wins", 0)
    total = strategy_data.get("total_trades", strategy_data.get("trades", 0))
    losses = strategy_data.get("losses", 0)
    draws  = strategy_data.get("draws", 0)
    if isinstance(total, list):
        total = len(total)
    if total == 0:
        total = wins + losses + draws
    metrics["win_rate"]      = wins / total if total > 0 else 0.0
    metrics["total_trades"]  = total
    metrics["wins"]          = wins
    metrics["losses"]        = losses

    # --- Sharpe ---
    metrics["sharpe"] = strategy_data.get(
        "sharpe",
        strategy_data.get("sharpe_ratio", 0.0)
    )

    # --- Max drawdown (as ratio 0–1) ---
    # FreqTrade ZIP stores it as max_relative_drawdown or max_drawdown_account
    dd = strategy_data.get(
        "max_relative_drawdown",
        strategy_data.get("max_drawdown_account",
        strategy_data.get("max_drawdown",
        strategy_data.get("max_drawdown_abs", 0.0)))
    )
    # If expressed as %, convert to ratio
    if isinstance(dd, (int, float)) and dd > 1:
        dd = dd / 100.0
    metrics["max_drawdown"] = abs(dd)

    # --- Profit factor ---
    metrics["profit_factor"] = strategy_data.get(
        "profit_factor",
        strategy_data.get("profit_all_percent", 0.0)
    )

    # --- Extra context ---
    metrics["profit_total_pct"] = strategy_data.get(
        "profit_total_abs",
        strategy_data.get("profit_total", 0.0)
    )
    metrics["duration_avg"] = strategy_data.get("holding_avg", "N/A")
    metrics["start_date"]   = strategy_data.get("backtest_start", "N/A")
    metrics["end_date"]     = strategy_data.get("backtest_end", "N/A")

    return metrics


def grade(metrics: dict) -> bool:
    """Print a PASS/FAIL table. Returns True if all criteria pass."""
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  FinBuddy Task 1.3 — Backtest Acceptance Report{RESET}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    # Context
    print(f"\n  Trades  : {metrics.get('total_trades', 'N/A'):>6}  "
          f"({metrics.get('wins', '?')}W / {metrics.get('losses', '?')}L)")
    print(f"  Period  : {metrics.get('start_date', 'N/A')} → {metrics.get('end_date', 'N/A')}")
    print(f"  Avg Hold: {metrics.get('duration_avg', 'N/A')}")
    print(f"  Total P&L: {metrics.get('profit_total_pct', 'N/A')}")

    print(f"\n  {'Metric':<20} {'Value':>10}  {'Threshold':>12}  {'Result':>8}")
    print(f"  {'-'*56}")

    all_pass = True
    for key, cfg in CRITERIA.items():
        value = metrics.get(key, 0.0)
        threshold = cfg["threshold"]
        fmt = cfg["fmt"]
        label = cfg["label"]

        if cfg["op"] == "gt":
            passed = value > threshold
            threshold_str = f"> {threshold:{fmt}}"
        else:  # lt
            passed = value < threshold
            threshold_str = f"< {threshold:{fmt}}"

        if passed:
            result_str = f"{GREEN}  PASS  {RESET}"
        else:
            result_str = f"{RED}  FAIL  {RESET}"
            all_pass = False

        value_str = format(value, fmt)
        print(f"  {label:<20} {value_str:>10}  {threshold_str:>12}  {result_str}")

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    if all_pass:
        print(f"{GREEN}{BOLD}  ✅ ALL CRITERIA PASSED — Strategy is VALIDATED{RESET}")
        print(f"\n  Next steps:")
        print(f"  1. Update strategies/registry.json → backtest.status: 'validated'")
        print(f"  2. Mark Task 1.3 as ✅ COMPLETE in tasks/phase-1-freqai-brain.md")
        print(f"  3. Proceed to Task 1.4 (switch dry-run to FinBuddyFreqAI)")
    else:
        print(f"{RED}{BOLD}  ❌ SOME CRITERIA FAILED — Strategy needs tuning{RESET}")
        print(f"\n  Suggested fixes:")
        win  = metrics.get("win_rate", 0)
        shp  = metrics.get("sharpe", 0)
        dd   = metrics.get("max_drawdown", 0)
        pf   = metrics.get("profit_factor", 0)
        if win <= 0.50:
            print(f"  {YELLOW}• Win rate low ({win:.1%}): tighten entry threshold "
                  f"(try &-s_close > 0.010 instead of 0.008){RESET}")
        if shp <= 0.50:
            print(f"  {YELLOW}• Sharpe low ({shp:.3f}): add RSI filter or tighten "
                  f"exit stoploss{RESET}")
        if dd >= 0.20:
            print(f"  {YELLOW}• Drawdown high ({dd:.1%}): reduce max_open_trades from "
                  f"4 to 2, or tighten stoploss from -3% to -2%{RESET}")
        if pf <= 1.20:
            print(f"  {YELLOW}• Profit factor low ({pf:.3f}): review exit conditions, "
                  f"consider raising min_roi{RESET}")
        print(f"\n  Do NOT mark Task 1.3 complete until all criteria pass.")
        print(f"  Leave Task 1.2 as ⚠️ NEEDS REVIEW and add tuning notes.")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    return all_pass


def main():
    parser = argparse.ArgumentParser(description="FinBuddy backtest result grader")
    parser.add_argument(
        "--results-dir",
        default="user_data/backtest_results",
        help="Path to backtest_results directory"
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Specific JSON file to parse (optional, defaults to latest)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metrics as JSON for machine consumption (used by autobacktest.py)"
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"{RED}[×] Results directory not found: {results_dir}{RESET}")
        sys.exit(1)

    if args.file:
        with open(args.file) as f:
            data = json.load(f)
    else:
        data = find_latest_result(results_dir)

    metrics = extract_metrics(data)

    if args.json:
        # Machine-readable output for autobacktest.py — print JSON then exit 0
        print(json.dumps({
            "win_rate":      metrics.get("win_rate"),
            "sharpe":        metrics.get("sharpe"),
            "max_drawdown":  metrics.get("max_drawdown"),
            "profit_factor": metrics.get("profit_factor"),
            "total_profit":  metrics.get("total_profit"),
            "trades":        metrics.get("total_trades"),
        }))
        sys.exit(0)

    passed = grade(metrics)
    # Exit code: 0 = all pass, 1 = some fail (useful for CI/scripting)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
