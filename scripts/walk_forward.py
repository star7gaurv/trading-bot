#!/usr/bin/env python3
"""
FinBuddy Walk-Forward Validator

Runs FreqTrade backtests in rolling folds (train N months, test 1 month, slide).
The aggregated out-of-sample stats are the real test — anything
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


def run_backtest(strategy: str, tf: str, train_start: datetime,
                 test_start: datetime, test_end: datetime,
                 run_dir: Path, fold: int,
                 freqai_identifier: str | None = None,
                 config: str | None = None) -> Path | None:
    """Run a single backtest fold via docker-compose. Returns path to result json or None.

    Timerange = train_start → test_end (full window so FreqAI can train on the
    first portion and predict on the test portion).  FreqAI internally uses
    train_period_days (90) to decide how much data is training vs prediction.

    If `freqai_identifier` is set, it overrides config.json via the
    FREQTRADE__FREQAI__IDENTIFIER env var. CRITICAL for walk-forward: without
    a fresh identifier, FreqAI loads cached live-bot models that were trained
    on FUTURE data, causing lookahead bias.
    """
    timerange = f"{train_start.strftime('%Y%m%d')}-{test_end.strftime('%Y%m%d')}"
    test_label = f"{test_start.strftime('%Y%m%d')}-{test_end.strftime('%Y%m%d')}"
    log_path = run_dir / f"fold_{fold:02d}_{test_label}.log"
    id_str = f"  [identifier={freqai_identifier}]" if freqai_identifier else ""
    print(f"[fold {fold}] backtesting {test_label} (full window {timerange}){id_str} ...")
    cmd = [
        "docker-compose", "run", "--rm",
        # Use a large backtest wallet so stake depletion never silences the test window.
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
    ]
    # Bug A fix (2026-05-20): WF was NOT passing live env vars, so it tested
    # the strategy class defaults (LT=1.5, ST=-1.5, K_SL=1.0, ...) instead of
    # the live values (LT=3.25, ST=-2.75, K_SL=2.0, ...). Every WF result of
    # the last 11 days was structurally evaluating a different strategy.
    # Read from freqtrade/.env so WF always tests the exact live config.
    for env_key in (
        "FREQAI_K_SL", "FREQAI_K_TP",
        "FREQAI_LONG_THRESHOLD", "FREQAI_SHORT_THRESHOLD",
        "FREQAI_STABILITY_N", "FREQAI_FEATURE_SET",
        "FINBUDDY_RECENT_WR",
    ):
        env_path = COMPOSE_DIR / ".env"
        val = None
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith(f"{env_key}="):
                    val = line.split("=", 1)[1].strip()
                    break
        if val is None:
            val = os.environ.get(env_key)
        if val is not None:
            cmd += ["-e", f"{env_key}={val}"]
    if freqai_identifier:
        # Override config.json's freqai.identifier without editing the file
        cmd += ["-e", f"FREQTRADE__FREQAI__IDENTIFIER={freqai_identifier}"]
    cmd += [
        "freqtrade",
        "backtesting",
        "--strategy", strategy,
        "--timeframe", tf,
        "--timerange", timerange,
        "--export", "trades",
        "--cache", "none",
    ]
    if config:
        cmd += ["--config", f"/freqtrade/user_data/{config}"]
    else:
        cmd += ["--config", "/freqtrade/user_data/config.json"]

    LAST_RESULT.unlink(missing_ok=True)  # prevent stale prior-fold result being silently reused

    with log_path.open("w") as logf:
        # Bumped 2026-05-20: 3600 → 7200 → 10800s. Each fold trains 25 pairs
        # across ~30 sliding-train cycles on 533 features. With DI=1.0 +
        # use_SVM_to_remove_outliers=true added to live config (Bug E fix), the
        # per-cycle cost grew enough that fold 1 needed ~3h instead of ~2h.
        # 13:21 UTC WF run hit the 7200s ceiling at ~75% (18/25 pairs trained).
        proc = subprocess.run(cmd, cwd=COMPOSE_DIR, stdout=logf, stderr=subprocess.STDOUT, timeout=10800)
    if proc.returncode != 0:
        print(f"  FAIL — see {log_path}")
        return None
    if not LAST_RESULT.exists():
        print(f"  FAIL — no .last_result.json after run")
        return None
    target = run_dir / f"fold_{fold:02d}_result.json"
    target.write_bytes(LAST_RESULT.read_bytes())
    return target


def _compute_metrics_from_trades(trades: list[dict], starting_balance: float = 10000.0) -> dict:
    """Compute trades/WR/PF/max_drawdown/sharpe from a per-trade list.

    Sharpe is annualised from daily aggregated PnL (not per-trade) — the
    standard Freqtrade convention. Drawdown is computed from the equity
    curve built by replaying trades in close_date order.
    """
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "wins": 0, "win_rate": 0.0,
            "profit_total_abs": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "sharpe": 0.0,
        }

    profits = [float(t.get("profit_abs") or 0.0) for t in trades]
    wins = sum(1 for p in profits if p > 0)
    total = sum(profits)
    gross_win = sum(p for p in profits if p > 0)
    gross_loss = -sum(p for p in profits if p < 0)
    if gross_loss > 0:
        pf = gross_win / gross_loss
    else:
        # all wins (or no losers) — clamp to a high but finite number
        pf = float("inf") if gross_win > 0 else 0.0

    # Equity curve & max drawdown (account-relative, like Freqtrade reports)
    sorted_trades = sorted(trades, key=lambda t: t.get("close_date") or "")
    equity = starting_balance
    peak = equity
    max_dd = 0.0
    daily: dict[str, float] = {}
    for t in sorted_trades:
        p = float(t.get("profit_abs") or 0.0)
        equity += p
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
        # bucket by close-date for daily Sharpe
        day = (t.get("close_date") or "")[:10]
        if day:
            daily[day] = daily.get(day, 0.0) + p

    # Daily-aggregated annualised Sharpe (252 trading days/yr convention)
    if len(daily) >= 2:
        import statistics
        # Convert to daily-return ratios on starting balance
        daily_returns = [v / starting_balance for v in daily.values()]
        mean = statistics.mean(daily_returns)
        sd = statistics.stdev(daily_returns)
        sharpe = (mean / sd) * (252 ** 0.5) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "trades": n,
        "wins": wins,
        "win_rate": wins / n,
        "profit_total_abs": total,
        "profit_factor": pf if pf != float("inf") else 999.0,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
    }


def parse_fold(result_path: Path, fold: int, test_start: datetime, test_end: datetime) -> FoldResult | None:
    """Parse a fold's backtest result, filtering trades to the OOS test window only.

    The backtest timerange is `train_start → test_end` (so FreqAI has data to
    train on), but the strategy emits signals across the whole window. For walk-
    forward integrity we MUST evaluate only the test slice [test_start, test_end).
    Aggregate fields like `sharpe` and `max_drawdown_account` from FreqTrade's
    JSON cover the full window and are unusable here — we recompute from the
    per-trade list.
    """
    pointer = json.loads(result_path.read_text())
    actual_zip = pointer.get("latest_backtest")
    if not actual_zip:
        return None
    actual_path = COMPOSE_DIR / "user_data" / "backtest_results" / actual_zip
    if actual_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(actual_path) as zf:
            # the main result JSON is the one without a suffix marker like _config
            candidates = [n for n in zf.namelist()
                          if n.endswith(".json") and "_config" not in n]
            if not candidates:
                print(f"  [fold {fold}] no result JSON found in {actual_zip}")
                return None
            data = json.loads(zf.read(candidates[0]).decode())
    else:
        data = json.loads(actual_path.read_text())

    strat_data = next(iter(data.get("strategy", {}).values()), {})
    all_trades = strat_data.get("trades", []) or []
    starting_balance = float(strat_data.get("starting_balance", 1000.0))

    # Filter to test window only — close_date is "YYYY-MM-DD HH:MM:SS+00:00"
    ts_iso = test_start.strftime("%Y-%m-%d")
    te_iso = test_end.strftime("%Y-%m-%d")
    test_trades = [
        t for t in all_trades
        if (cd := (t.get("close_date") or "")[:10]) and ts_iso <= cd < te_iso
    ]

    print(f"  [fold {fold}] window {ts_iso}→{te_iso}: "
          f"all_trades={len(all_trades)} test_window={len(test_trades)}")

    m = _compute_metrics_from_trades(test_trades, starting_balance)
    return FoldResult(
        fold=fold,
        test_start=ts_iso,
        test_end=te_iso,
        trades=m["trades"],
        win_rate=m["win_rate"],
        sharpe=m["sharpe"],
        max_drawdown=m["max_drawdown"],
        profit_factor=m["profit_factor"],
        profit_total_abs=m["profit_total_abs"],
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


def reparse_existing_run(run_dir: Path,
                         start: str, end: str,
                         train_m: int, test_m: int, slide_m: int) -> int:
    """Re-aggregate an already-completed walkforward_results/<run_id>/ using the
    current parse_fold() logic, without re-running any backtests. Use this after
    fixing a parser bug — overwrites summary.json with corrected metrics."""
    if not run_dir.exists():
        print(f"ERR: {run_dir} does not exist", file=sys.stderr)
        return 1
    folds: list[FoldResult] = []
    for fold, ts, te, vs, ve in daterange_folds(start, end, train_m, test_m, slide_m):
        result_pointer = run_dir / f"fold_{fold:02d}_result.json"
        if not result_pointer.exists():
            print(f"  [fold {fold}] missing pointer file — skipping")
            continue
        fr = parse_fold(result_pointer, fold, vs, ve)
        if fr is None:
            print(f"  [fold {fold}] parse failed — skipping")
            continue
        folds.append(fr)
        print(f"  [fold {fold}] trades={fr.trades} WR={fr.win_rate:.1%} "
              f"Sharpe={fr.sharpe:.3f} DD={fr.max_drawdown:.1%} PF={fr.profit_factor:.3f} "
              f"P&L={fr.profit_total_abs:+.2f}")

    summary_path = run_dir / "summary.json"
    agg = aggregate(folds)
    ok, msgs = grade(agg) if agg.get("total_trades") else (False, ["❌ no trades across all folds"])
    summary = {"folds": [asdict(f) for f in folds], "aggregate": agg, "pass": ok, "verdict": msgs}
    summary_path.write_text(json.dumps(summary, indent=2))

    print("\n=== Walk-Forward Summary (reparsed) ===")
    for m in msgs:
        print(" ", m)
    print(f"\nFolds: {len(folds)}  Total trades: {agg.get('total_trades', 0)}")
    print(f"Summary: {summary_path}")
    return 0 if ok else 2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="YYYY-MM-DD outer window start")
    p.add_argument("--end", required=True, help="YYYY-MM-DD outer window end")
    p.add_argument("--train-months", type=int, default=6)
    p.add_argument("--test-months", type=int, default=1)
    p.add_argument("--slide-months", type=int, default=1)
    p.add_argument("--strategy", default="FinBuddyFreqAI_v23")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--config", help="Custom config filename inside user_data/")
    p.add_argument("--skip-download", action="store_true", help="Skip data download (use if data already downloaded)")
    p.add_argument("--reparse", metavar="RUN_DIR",
                   help="Re-aggregate an existing walkforward_results/<run_id>/ "
                        "using current parser (no backtests re-run). Pass full path or just run_id.")
    args = p.parse_args()

    if args.reparse:
        run_dir = Path(args.reparse)
        if not run_dir.is_absolute():
            run_dir = RESULTS_BASE / args.reparse
        sys.exit(reparse_existing_run(
            run_dir, args.start, args.end,
            args.train_months, args.test_months, args.slide_months
        ))

    run_stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = f"{args.strategy}_{args.start}_{args.end}_{run_stamp}"
    run_dir = RESULTS_BASE / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Walk-forward run: {run_dir}")

    # Use a unique throwaway FreqAI identifier per fold to FORCE fresh training
    # from scratch within each fold's data window. Without this, FreqAI loads
    # cached live-bot models trained on data that's in the future relative to
    # the fold's window — lookahead bias that invalidates walk-forward.
    fold_identifier_base = f"wf_{run_stamp}"

    if not args.skip_download:
        download_data(args.start, args.end, args.timeframe)
    else:
        print("[data] Skipping download (--skip-download set).")

    folds: list[FoldResult] = []
    for fold, ts, te, vs, ve in daterange_folds(
        args.start, args.end, args.train_months, args.test_months, args.slide_months
    ):
        fold_id = f"{fold_identifier_base}_f{fold:02d}"
        rp = run_backtest(args.strategy, args.timeframe, ts, vs, ve, run_dir, fold,
                          freqai_identifier=fold_id, config=args.config)
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
