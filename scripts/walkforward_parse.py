#!/usr/bin/env python3
"""
Walk-forward result parser — v2 (2026-05-03)

Reads the latest backtest-result ZIP, extracts trades, groups by month,
reports per-window Sharpe + WR, prints pass/fail verdict, and writes
a machine-readable JSON to experiments/wf_latest.json for auto_experiment.sh.

Usage:
    python3 scripts/walkforward_parse.py
    python3 scripts/walkforward_parse.py --result <path-to-zip>
    python3 scripts/walkforward_parse.py --out-json /path/to/output.json
"""
import argparse
import json
import math
import sys
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

BASE       = Path("/home/ubuntu/var/www/html/trade")
RESULTS_DIR = BASE / "freqtrade/user_data/backtest_results"
EXP_DIR    = BASE / "experiments"


def find_latest_zip(results_dir: Path) -> Path:
    zips = sorted(results_dir.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        print(f"ERROR: No backtest result zips in {results_dir}", file=sys.stderr)
        sys.exit(1)
    return zips[-1]


def load_trades(zip_path: Path) -> list:
    with zipfile.ZipFile(zip_path) as zf:
        json_names = [n for n in zf.namelist()
                      if n.endswith(".json") and not n.endswith(".meta.json")]
        if not json_names:
            print(f"ERROR: No trades JSON in {zip_path}", file=sys.stderr)
            sys.exit(1)
        with zf.open(json_names[0]) as f:
            data = json.load(f)
    strat = data.get("strategy", {})
    if strat:
        name = next(iter(strat))
        return strat[name].get("trades", [])
    return data.get("trades", [])


def month_key(iso_ts: str) -> str:
    return iso_ts[:7] if iso_ts else "unknown"


def sharpe_ratio(returns: list) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var  = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sd   = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(len(returns))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result",   help="Path to backtest-result ZIP")
    ap.add_argument("--out-json", help="Write JSON summary to this path (default: experiments/wf_latest.json)")
    ap.add_argument("--group-by", choices=["close", "open"], default="close")
    args = ap.parse_args()

    zip_path = Path(args.result) if args.result else find_latest_zip(RESULTS_DIR)
    print(f"Reading: {zip_path.name}")

    trades = load_trades(zip_path)
    if not trades:
        print("No trades — empty result.")
        sys.exit(0)

    date_field = "close_date" if args.group_by == "close" else "open_date"
    by_month   = defaultdict(list)
    for t in trades:
        by_month[month_key(t.get(date_field, ""))].append(t)

    print(f"\nTotal trades : {len(trades)}")
    print(f"Months found : {len(by_month)}\n")
    print(f"{'Month':<9} {'N':>4} {'Wins':>5} {'Losses':>7} {'WR%':>6} {'Sharpe':>8} {'P&L%':>8} {'Avg%':>8}")
    print("-" * 70)

    month_stats   = {}
    all_returns   = []

    for month in sorted(by_month.keys()):
        rets  = [t.get("profit_ratio", 0.0) for t in by_month[month]]
        wins  = sum(1 for r in rets if r > 0)
        losses= len(rets) - wins
        wr    = wins / len(rets) * 100 if rets else 0.0
        s     = sharpe_ratio(rets)
        pnl   = sum(rets) * 100
        avg   = sum(rets) / len(rets) * 100 if rets else 0.0
        print(f"{month:<9} {len(rets):>4} {wins:>5} {losses:>7} {wr:>6.1f} {s:>+8.2f} {pnl:>+8.2f} {avg:>+8.3f}")
        month_stats[month] = {"n": len(rets), "wins": wins, "losses": losses,
                               "wr": round(wr, 2), "sharpe": round(s, 4),
                               "pnl_pct": round(pnl, 4), "avg_pct": round(avg, 4)}
        all_returns.extend(rets)

    print("-" * 70)
    total_wins = sum(1 for r in all_returns if r > 0)
    overall_wr  = total_wins / len(all_returns) * 100 if all_returns else 0.0
    overall_s   = sharpe_ratio(all_returns)
    overall_pnl = sum(all_returns) * 100
    overall_avg = sum(all_returns) / len(all_returns) * 100 if all_returns else 0.0
    print(f"{'OVERALL':<9} {len(all_returns):>4} {total_wins:>5} {len(all_returns)-total_wins:>7} "
          f"{overall_wr:>6.1f} {overall_s:>+8.2f} {overall_pnl:>+8.2f} {overall_avg:>+8.3f}")

    # --- Stability metrics (only months with >=2 trades) ---
    evaluated = {m: s for m, s in month_stats.items() if month_stats[m]["n"] >= 2}
    eval_sharpes = [v["sharpe"] for v in evaluated.values()]
    eval_wrs     = [v["wr"]     for v in evaluated.values()]

    avg_monthly_sharpe  = sum(eval_sharpes) / len(eval_sharpes) if eval_sharpes else 0.0
    pct_positive_sharpe = sum(1 for s in eval_sharpes if s > 0) / len(eval_sharpes) * 100 if eval_sharpes else 0.0
    pct_wr_above_50     = sum(1 for w in eval_wrs     if w > 50) / len(eval_wrs)     * 100 if eval_wrs     else 0.0

    # Single-month dominance: max |P&L| month vs cumulative abs sum
    pnls = [v["pnl_pct"] for v in month_stats.values()]
    max_single = max(pnls, key=abs) if pnls else 0.0
    cum_abs    = sum(abs(p) for p in pnls)
    dominance  = abs(max_single) / cum_abs * 100 if cum_abs else 0.0

    print(f"\nStability ({len(evaluated)} months with >=2 trades evaluated):")
    print(f"  Avg monthly Sharpe   : {avg_monthly_sharpe:+.2f}  (target > 0)")
    print(f"  Months Sharpe > 0    : {sum(1 for s in eval_sharpes if s > 0)}/{len(eval_sharpes)}  ({pct_positive_sharpe:.0f}%)  (target >= 50%)")
    print(f"  Months WR > 50%      : {sum(1 for w in eval_wrs if w > 50)}/{len(eval_wrs)}  ({pct_wr_above_50:.0f}%)  (target >= 60%)")
    print(f"  Max single-month dom : {dominance:.1f}%  (target < 40%)")

    # --- Pass / fail verdict ---
    passed = (
        pct_wr_above_50     >= 60.0 and
        avg_monthly_sharpe  >  0.0  and
        dominance           <  40.0 and
        pct_positive_sharpe >= 50.0
    )
    verdict = "PASS" if passed else "FAIL"
    print(f"\n{'='*40}")
    print(f"  WALK-FORWARD VERDICT: {verdict}")
    print(f"{'='*40}\n")

    # --- Write JSON for auto_experiment.sh ---
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out_json) if args.out_json else EXP_DIR / "wf_latest.json"
    summary = {
        "timestamp":            datetime.now(timezone.utc).isoformat(),
        "zip_file":             zip_path.name,
        "total_trades":         len(all_returns),
        "overall_wr":           round(overall_wr,  2),
        "overall_sharpe":       round(overall_s,   4),
        "overall_pnl_pct":      round(overall_pnl, 4),
        "avg_monthly_sharpe":   round(avg_monthly_sharpe,  4),
        "pct_positive_sharpe":  round(pct_positive_sharpe, 2),
        "pct_wr_above_50":      round(pct_wr_above_50,     2),
        "max_single_month_dom": round(dominance, 2),
        "verdict":              verdict,
        "months":               month_stats,
    }
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"JSON summary → {out_path}")

    # --- Append one row to experiments/results_log.csv ---
    csv_path = EXP_DIR / "results_log.csv"
    header   = "timestamp,zip_file,total_trades,overall_wr,overall_sharpe,overall_pnl_pct,avg_monthly_sharpe,pct_positive_sharpe,pct_wr_above_50,max_dom_pct,verdict\n"
    row = (
        f"{summary['timestamp']},{zip_path.name},{len(all_returns)},"
        f"{overall_wr:.2f},{overall_s:.4f},{overall_pnl:.4f},"
        f"{avg_monthly_sharpe:.4f},{pct_positive_sharpe:.2f},{pct_wr_above_50:.2f},"
        f"{dominance:.2f},{verdict}\n"
    )
    if not csv_path.exists():
        csv_path.write_text(header)
    with open(csv_path, "a") as f:
        f.write(row)
    print(f"CSV log      → {csv_path}")


if __name__ == "__main__":
    main()
