#!/usr/bin/env python3
"""
FinBuddy Walk-Forward Validator

Runs FreqTrade backtests in rolling folds (train N months, test 1 month, slide).
The aggregated out-of-sample stats are the real test of v15/v16 — anything
better in-sample is suspected overfit until walk-forward agrees.

Usage:
    python3 scripts/walk_forward.py \
        --start 2024-01-01 --end 2025-01-01 \
        --train-months 6 --test-months 1 --slide-months 1 \
        --strategy FinBuddyFreqAI --timeframe 1h

Each fold runs `docker compose run --rm freqtrade backtesting` and parses
`user_data/backtest_results/.last_result.json`. Per-fold results are
saved under `walkforward_results/<run_id>/` and aggregated stats are
printed at the end.

Designed to run manually overnight — folds are heavy. Not cron'd.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta  # type: ignore

REPO = Path("/home/ubuntu/var/www/html/trade")
COMPOSE_DIR = REPO / "freqtrade"
RESULTS_BASE = REPO / "walkforward_results"
LAST_RESULT = COMPOSE_DIR / "user_data" / "backtest_results" / ".last_result.json"


@dataclass
class FoldResult:
    fold: int
    test_start: str
    test_end: str
    trades: int
    win_rate: float
    sharpe: float
    max_drawdown: float
    profit_factor: float
    profit_total_abs: float


def daterange_folds(start: str, end: str, train_m: int, test_m: int, slide_m: int):
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    cursor = s
    fold = 0
    while True:
        train_start = cursor
        train_end = train_start + relativedelta(months=train_m)
        test_start = train_end
        test_end = test_start + relativedelta(months=test_m)
        if test_end > e:
            break
        fold += 1
        yield fold, train_start, train_end, test_start, test_end
        cursor = cursor + relativedelta(months=slide_m)


def run_backtest(strategy: str, tf: str, train_start: datetime, test_start: datetime, test_end: datetime, run_dir: Path, fold: int) -> Path | None:
    """Run a single backtest fold via docker-compose. Returns path to result json or None.

    Timerange = train_start → test_end (full window so FreqAI can train on the
    first portion and predict on the test portion).  FreqAI internally uses
    train_period_days (90) to decide how much data is training vs prediction.
    """
    timerange = f"{train_start.strftime('%Y%m%d')}-{test_end.strftime('%Y%m%d')}"
    test_label = f"{test_start.strftime('%Y%m%d')}-{test_end.strftime('%Y%m%d')}"
    log_path = run_dir / f"fold_{fold:02d}_{test_label}.log"
    print(f"[fold {fold}] backtesting {test_label} (full window {timerange}) ...")
    cmd = [
        "docker-compose", "run", "--rm", "freqtrade",
        "backtesting",
        "--strategy", strategy,
        "--timeframe", tf,
        "--timerange", timerange,
        "--export", "trades",
        "--cache", "none",
    ]
    with log_path.open("w") as logf:
        proc = subprocess.run(cmd, cwd=COMPOSE_DIR, stdout=logf, stderr=subprocess.STDOUT, timeout=3600)
    if proc.returncode != 0:
        print(f"  FAIL — see {log_path}")
        return None
    if not LAST_RESULT.exists():
        print(f"  FAIL — no .last_result.json after run")
        return None
    target = run_dir / f"fold_{fold:02d}_result.json"
    target.write_bytes(LAST_RESULT.read_bytes())
    return target


def parse_fold(result_path: Path, fold: int, test_start: datetime, test_end: datetime) -> FoldResult | None:
    """Read FreqTrade's .last_result.json (which points to the actual result file)."""
    pointer = json.loads(result_path.read_text())
    actual_zip = pointer.get("latest_backtest")
    if not actual_zip:
        return None
    actual_path = COMPOSE_DIR / "user_data" / "backtest_results" / actual_zip
    if actual_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(actual_path) as zf:
            inner = [n for n in zf.namelist() if n.endswith(".json")][0]
            data = json.loads(zf.read(inner).decode())
    else:
        data = json.loads(actual_path.read_text())
    strat_data = next(iter(data.get("strategy", {}).values()), {})
    summary = strat_data.get("results_per_pair", [{}])[-1]  # TOTAL row last
    return FoldResult(
        fold=fold,
        test_start=test_start.date().isoformat(),
        test_end=test_end.date().isoformat(),
        trades=int(summary.get("trades", 0)),
        win_rate=float(summary.get("wins", 0)) / max(int(summary.get("trades", 1)), 1),
        sharpe=float(strat_data.get("sharpe", 0.0)),
        max_drawdown=float(strat_data.get("max_drawdown", 0.0)),
        profit_factor=float(strat_data.get("profit_factor", 0.0)),
        profit_total_abs=float(strat_data.get("profit_total_abs", 0.0)),
    )


def aggregate(folds: list[FoldResult]) -> dict:
    if not folds:
        return {}
    total_trades = sum(f.trades for f in folds)
    if total_trades == 0:
        return {"total_trades": 0}
    weighted_wr = sum(f.win_rate * f.trades for f in folds) / total_trades
    weighted_sharpe = sum(f.sharpe * f.trades for f in folds) / total_trades
    worst_dd = max((f.max_drawdown for f in folds), default=0.0)
    weighted_pf = sum(f.profit_factor * f.trades for f in folds) / total_trades
    total_profit = sum(f.profit_total_abs for f in folds)
    return {
        "folds": len(folds),
        "total_trades": total_trades,
        "weighted_win_rate": weighted_wr,
        "weighted_sharpe": weighted_sharpe,
        "worst_drawdown": worst_dd,
        "weighted_profit_factor": weighted_pf,
        "total_profit_abs": total_profit,
    }


def grade(agg: dict) -> tuple[bool, list[str]]:
    """Acceptance: WR>0.5, Sharpe>0.5, DD<0.2, PF>1.2."""
    msgs = []
    ok = True
    if agg.get("weighted_win_rate", 0) <= 0.5:
        ok = False; msgs.append(f"❌ WR {agg['weighted_win_rate']:.1%} (need >50%)")
    else:
        msgs.append(f"✅ WR {agg['weighted_win_rate']:.1%}")
    if agg.get("weighted_sharpe", -1) <= 0.5:
        ok = False; msgs.append(f"❌ Sharpe {agg['weighted_sharpe']:.3f} (need >0.5)")
    else:
        msgs.append(f"✅ Sharpe {agg['weighted_sharpe']:.3f}")
    if agg.get("worst_drawdown", 1) >= 0.2:
        ok = False; msgs.append(f"❌ Worst DD {agg['worst_drawdown']:.1%} (need <20%)")
    else:
        msgs.append(f"✅ Worst DD {agg['worst_drawdown']:.1%}")
    if agg.get("weighted_profit_factor", 0) <= 1.2:
        ok = False; msgs.append(f"❌ PF {agg['weighted_profit_factor']:.3f} (need >1.2)")
    else:
        msgs.append(f"✅ PF {agg['weighted_profit_factor']:.3f}")
    return ok, msgs


def download_data(start: str, end: str, tf: str) -> bool:
    """Download futures OHLCV + mark + funding data for all whitelisted pairs."""
    timerange = f"{start.replace('-', '')}-{end.replace('-', '')}"
    print(f"[data] Downloading futures data for {timerange} @ {tf} ...")
    cmd = [
        "docker-compose", "run", "--rm", "freqtrade",
        "download-data",
        "--timeframe", tf,
        "--timerange", timerange,
        "--trading-mode", "futures",
        "--prepend",
    ]
    proc = subprocess.run(cmd, cwd=COMPOSE_DIR, timeout=7200)
    if proc.returncode != 0:
        print("[data] WARNING: download-data returned non-zero — some pairs may be missing data.")
        return False
    print("[data] Download complete.")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="YYYY-MM-DD outer window start")
    p.add_argument("--end", required=True, help="YYYY-MM-DD outer window end")
    p.add_argument("--train-months", type=int, default=6)
    p.add_argument("--test-months", type=int, default=1)
    p.add_argument("--slide-months", type=int, default=1)
    p.add_argument("--strategy", default="FinBuddyFreqAI")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--skip-download", action="store_true", help="Skip data download (use if data already downloaded)")
    args = p.parse_args()

    run_id = f"{args.strategy}_{args.start}_{args.end}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    run_dir = RESULTS_BASE / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Walk-forward run: {run_dir}")

    if not args.skip_download:
        download_data(args.start, args.end, args.timeframe)
    else:
        print("[data] Skipping download (--skip-download set).")

    folds: list[FoldResult] = []
    for fold, ts, te, vs, ve in daterange_folds(
        args.start, args.end, args.train_months, args.test_months, args.slide_months
    ):
        rp = run_backtest(args.strategy, args.timeframe, ts, vs, ve, run_dir, fold)
        if rp is None:
            continue
        fr = parse_fold(rp, fold, vs, ve)
        if fr is None:
            print(f"  [fold {fold}] result parse failed, skipping")
            continue
        folds.append(fr)
        print(f"  [fold {fold}] trades={fr.trades} WR={fr.win_rate:.1%} Sharpe={fr.sharpe:.3f} DD={fr.max_drawdown:.1%} PF={fr.profit_factor:.3f}")

    summary_path = run_dir / "summary.json"
    agg = aggregate(folds)
    ok, msgs = grade(agg) if agg.get("total_trades") else (False, ["❌ no trades across all folds"])
    summary = {"folds": [asdict(f) for f in folds], "aggregate": agg, "pass": ok, "verdict": msgs}
    summary_path.write_text(json.dumps(summary, indent=2))

    print("\n=== Walk-Forward Summary ===")
    for m in msgs:
        print(" ", m)
    print(f"\nFolds: {len(folds)}  Total trades: {agg.get('total_trades', 0)}")
    print(f"Summary: {summary_path}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
