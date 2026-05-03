#!/usr/bin/env python3
"""
Walk-forward result parser.

Reads the latest backtest-result ZIP from
freqtrade/user_data/backtest_results/, extracts trades, groups them by
test-window (month), and reports per-window Sharpe and Win Rate.

Usage:
    python3 scripts/walkforward_parse.py
    python3 scripts/walkforward_parse.py --result <path-to-zip>
"""
import argparse
import json
import math
import sys
import zipfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict

RESULTS_DIR = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/backtest_results")


def find_latest_zip(results_dir: Path) -> Path:
    zips = sorted(results_dir.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        print(f"No backtest result zips found in {results_dir}", file=sys.stderr)
        sys.exit(1)
    return zips[-1]


def load_trades(zip_path: Path) -> list:
    with zipfile.ZipFile(zip_path) as zf:
        # FT writes one .json with detail in the zip
        json_names = [n for n in zf.namelist() if n.endswith(".json") and not n.endswith(".meta.json")]
        if not json_names:
            print(f"No trades json in {zip_path}", file=sys.stderr); sys.exit(1)
        with zf.open(json_names[0]) as f:
            data = json.load(f)
    # FT result schema: data["strategy"]["FinBuddyFreqAI"]["trades"]
    strat = data.get("strategy", {})
    if not strat:
        # Some FT versions: trades at root
        return data.get("trades", [])
    name = next(iter(strat))
    return strat[name].get("trades", [])


def month_key(iso_ts: str) -> str:
    # close_date typically "2024-07-15 13:30:00" or similar
    if not iso_ts:
        return "unknown"
    return iso_ts[:7]  # "YYYY-MM"


def sharpe(returns: list) -> float:
    """Trade-level Sharpe (annualized rough): mean/std * sqrt(N_trades_per_year_estimate).
    For per-month windows we use sqrt(12) as a coarse annualizer of monthly aggregates,
    but here we compute on trade-level returns within the month and report raw mean/std ratio
    plus an annualized estimate using avg-trades-per-year proxy.
    Returns the simple mean/std ratio (sqrt(n)) for comparability with FT's "Sharpe (closed)".
    """
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(len(returns))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", help="Path to backtest-result ZIP")
    ap.add_argument("--group-by", choices=["close", "open"], default="close",
                    help="Group trades by close_date (test-window result, default) or open_date")
    args = ap.parse_args()

    zip_path = Path(args.result) if args.result else find_latest_zip(RESULTS_DIR)
    print(f"Reading: {zip_path.name}")

    trades = load_trades(zip_path)
    if not trades:
        print("No trades."); sys.exit(0)

    by_month = defaultdict(list)
    date_field = "close_date" if args.group_by == "close" else "open_date"
    for t in trades:
        by_month[month_key(t.get(date_field, ""))].append(t)

    print(f"\nTotal trades: {len(trades)}")
    print(f"Windows (months): {len(by_month)}\n")

    print(f"{'Month':<9} {'N':>4} {'Wins':>5} {'Losses':>7} {'WR%':>6} {'Sharpe':>8} {'P&L%':>8} {'Avg%':>8}")
    print("-" * 70)

    cumulative = []
    for month in sorted(by_month.keys()):
        month_trades = by_month[month]
        rets = [t.get("profit_ratio", 0.0) for t in month_trades]
        wins = sum(1 for r in rets if r > 0)
        losses = sum(1 for r in rets if r <= 0)
        wr = (wins / len(rets) * 100) if rets else 0.0
        s = sharpe(rets)
        pnl = sum(rets) * 100
        avg = (sum(rets) / len(rets) * 100) if rets else 0.0
        print(f"{month:<9} {len(rets):>4} {wins:>5} {losses:>7} {wr:>6.1f} {s:>+8.2f} {pnl:>+8.2f} {avg:>+8.3f}")
        cumulative.extend(rets)

    print("-" * 70)
    if cumulative:
        wins = sum(1 for r in cumulative if r > 0)
        wr = wins / len(cumulative) * 100
        s = sharpe(cumulative)
        pnl = sum(cumulative) * 100
        avg = sum(cumulative) / len(cumulative) * 100
        print(f"{'OVERALL':<9} {len(cumulative):>4} {wins:>5} {len(cumulative)-wins:>7} "
              f"{wr:>6.1f} {s:>+8.2f} {pnl:>+8.2f} {avg:>+8.3f}")

    # Stability metrics
    monthly_sharpes = []
    monthly_wrs = []
    for month in sorted(by_month.keys()):
        rets = [t.get("profit_ratio", 0.0) for t in by_month[month]]
        if len(rets) >= 2:
            monthly_sharpes.append(sharpe(rets))
            wins = sum(1 for r in rets if r > 0)
            monthly_wrs.append(wins / len(rets) * 100)

    if monthly_sharpes:
        avg_s = sum(monthly_sharpes) / len(monthly_sharpes)
        positive_months = sum(1 for s in monthly_sharpes if s > 0)
        positive_wr_months = sum(1 for w in monthly_wrs if w > 50)
        print(f"\nStability:")
        print(f"  Months evaluated  : {len(monthly_sharpes)}")
        print(f"  Avg monthly Sharpe: {avg_s:+.2f}")
        print(f"  Months Sharpe > 0 : {positive_months} / {len(monthly_sharpes)} "
              f"({positive_months / len(monthly_sharpes) * 100:.0f}%)")
        print(f"  Months WR > 50%   : {positive_wr_months} / {len(monthly_wrs)} "
              f"({positive_wr_months / len(monthly_wrs) * 100:.0f}%)")


if __name__ == "__main__":
    main()
