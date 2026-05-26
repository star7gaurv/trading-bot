#!/usr/bin/env python3
"""
FinBuddy — Per-pair performance tracker
Reads closed trades from FreqTrade API and prints a WR/PF/profit table by pair.
Usage:
  python3 pair_performance.py              # all closed trades
  python3 pair_performance.py --strategy v15  # filter by enter_tag containing v15
  python3 pair_performance.py --since 2026-05-05  # trades closed after date
"""

import argparse
import requests
from collections import defaultdict
from datetime import datetime

API = "http://localhost:8080/api/v1"
import os
AUTH = (os.environ.get("FT_USER", "bot"), os.environ.get("FT_API_PASS", "REDACTED-FREQTRADE__API_SERVER__PASSWORD"))


def fetch_trades(since_date=None):
    trades = []
    offset = 0
    batch = 500
    while True:
        r = requests.get(f"{API}/trades", auth=AUTH,
                         params={"limit": batch, "offset": offset}, timeout=10)
        r.raise_for_status()
        data = r.json()
        batch_trades = data["trades"]
        if not batch_trades:
            break
        trades.extend(batch_trades)
        if len(trades) >= data["total_trades"]:
            break
        offset += batch

    closed = [t for t in trades if not t["is_open"]]

    if since_date:
        cutoff = datetime.fromisoformat(since_date)
        closed = [t for t in closed
                  if datetime.fromisoformat(t["close_date"].replace(" ", "T")) >= cutoff]
    return closed


def build_stats(trades, strategy_filter=None):
    pairs = defaultdict(lambda: {"wins": 0, "losses": 0, "gross_win": 0.0,
                                  "gross_loss": 0.0, "profit": 0.0, "trades": 0,
                                  "durations": []})
    for t in trades:
        tag = t.get("enter_tag", "")
        if strategy_filter and strategy_filter.lower() not in tag.lower():
            continue

        pair = t["pair"].replace("/USDT", "").replace(":USDT", "")
        profit = t["close_profit_abs"]
        duration_h = t["trade_duration_s"] / 3600

        pairs[pair]["trades"] += 1
        pairs[pair]["profit"] += profit
        pairs[pair]["durations"].append(duration_h)

        if profit >= 0:
            pairs[pair]["wins"] += 1
            pairs[pair]["gross_win"] += profit
        else:
            pairs[pair]["losses"] += 1
            pairs[pair]["gross_loss"] += abs(profit)

    return pairs


def print_table(pairs, total_trades):
    if not pairs:
        print("No trades found matching filters.")
        return

    # Sort by total profit descending
    rows = []
    for pair, s in pairs.items():
        n = s["trades"]
        wr = s["wins"] / n * 100 if n else 0
        pf = s["gross_win"] / s["gross_loss"] if s["gross_loss"] > 0 else float("inf")
        avg_dur = sum(s["durations"]) / len(s["durations"]) if s["durations"] else 0
        rows.append((pair, n, wr, pf, s["profit"], avg_dur, s["wins"], s["losses"]))

    rows.sort(key=lambda x: -x[4])  # sort by profit

    # Totals
    total_profit = sum(r[4] for r in rows)
    total_wins = sum(r[6] for r in rows)
    total_losses = sum(r[7] for r in rows)
    total_gw = sum(s["gross_win"] for s in pairs.values())
    total_gl = sum(s["gross_loss"] for s in pairs.values())
    overall_wr = total_wins / (total_wins + total_losses) * 100 if (total_wins + total_losses) else 0
    overall_pf = total_gw / total_gl if total_gl > 0 else float("inf")

    header = f"{'Pair':<8} {'Trades':>6} {'W':>4} {'L':>4} {'WR%':>6} {'PF':>6} {'Profit':>9} {'AvgDur':>8}"
    sep = "-" * len(header)
    print(f"\n{'FinBuddy — Per-Pair Performance':^{len(header)}}")
    print(f"{'(closed trades only)':^{len(header)}}\n")
    print(header)
    print(sep)

    for pair, n, wr, pf, profit, avg_dur, wins, losses in rows:
        pf_str = f"{pf:.2f}" if pf != float("inf") else "  ∞"
        dur_str = f"{avg_dur:.1f}h"
        profit_str = f"{profit:+.2f}"
        flag = " ✅" if (wr >= 50 and pf >= 1.2) else (" ⚠️" if wr >= 50 else " ❌")
        print(f"{pair:<8} {n:>6} {wins:>4} {losses:>4} {wr:>5.1f}% {pf_str:>6} {profit_str:>9} {dur_str:>8}{flag}")

    print(sep)
    pf_str = f"{overall_pf:.2f}" if overall_pf != float("inf") else "  ∞"
    print(f"{'TOTAL':<8} {total_wins+total_losses:>6} {total_wins:>4} {total_losses:>4} "
          f"{overall_wr:>5.1f}% {pf_str:>6} {total_profit:>+9.2f}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", help="Filter by enter_tag substring (e.g. v15)")
    parser.add_argument("--since", help="Only trades closed on/after this date (YYYY-MM-DD)")
    args = parser.parse_args()

    print(f"Fetching trades from FreqTrade API...")
    trades = fetch_trades(since_date=args.since)
    print(f"Found {len(trades)} closed trades" +
          (f" since {args.since}" if args.since else "") + ".")

    pairs = build_stats(trades, strategy_filter=args.strategy)
    print_table(pairs, len(trades))


if __name__ == "__main__":
    main()
