#!/usr/bin/env python3
"""
FinBuddy Walk-Forward Validator  (v2 — Parallel Fold Execution)

Runs FreqTrade backtests in rolling folds (train N months, test 1 month, slide).
The aggregated out-of-sample stats are the real test — anything
better in-sample is suspected overfit until walk-forward agrees.

Usage:
    python3 scripts/walk_forward.py \
        --start 2024-01-01 --end 2025-01-01 \
        --train-months 6 --test-months 1 --slide-months 1 \
        --strategy FinBuddyFreqAI_v23 --timeframe 15m \
        --max-workers 3   # run up to 3 folds in parallel (default)

v2 changes vs v1:
  - ProcessPoolExecutor for parallel fold execution (default max_workers=3)
  - Each fold writes to its own isolated .last_result_fXX.json — eliminates
    the shared-file race condition that would corrupt results in parallel mode
  - --max-workers CLI flag (default 3; set to 1 for sequential/debug)
  - --lgbm-threads CLI flag: LightGBM num_threads per worker (default 2)
    Strategy: 3 workers x 2 threads = 6 logical threads on 4-core server
    (acceptable — hyper-threading keeps all cores near 100%)
  - _read_env_vars() extracted as helper so the .env read is DRY
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta  # type: ignore

REPO = Path("/home/ubuntu/var/www/html/trade")
COMPOSE_DIR = REPO / "freqtrade"
RESULTS_BASE = REPO / "walkforward_results"
# v2: LAST_RESULT is the shared sentinel (legacy fallback only).
# Parallel mode uses per-fold .last_result_fXX.json files.
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


def _read_env_vars() -> dict[str, str]:
    """Read live strategy env vars from freqtrade/.env (DRY helper)."""
    env_path = COMPOSE_DIR / ".env"
    keys = (
        "FREQAI_K_SL", "FREQAI_K_TP",
        "FREQAI_LONG_THRESHOLD", "FREQAI_SHORT_THRESHOLD",
        "FREQAI_STABILITY_N", "FREQAI_FEATURE_SET",
        "FINBUDDY_RECENT_WR",
    )
    result: dict[str, str] = {}
    for key in keys:
        val = None
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip()
                    break
        if val is None:
            val = os.environ.get(key)
        if val is not None:
            result[key] = val
    return result


def run_backtest(
    strategy: str, tf: str, train_start: datetime,
    test_start: datetime, test_end: datetime,
    run_dir: Path, fold: int,
    freqai_identifier: str | None = None,
    config: str | None = None,
    lgbm_threads: int = 2,
) -> Path | None:
    """Run a single backtest fold via docker-compose. Returns path to result json or None.

    Timerange = train_start → test_end (full window so FreqAI can train on the
    first portion and predict on the test portion). FreqAI internally uses
    train_period_days (90) to decide how much data is training vs prediction.

    v2: Each fold writes its result pointer to a unique per-fold sentinel file
    (.last_result_fXX.json) so parallel folds never clobber each other.
    """
    timerange = f"{train_start.strftime('%Y%m%d')}-{test_end.strftime('%Y%m%d')}"
    test_label = f"{test_start.strftime('%Y%m%d')}-{test_end.strftime('%Y%m%d')}"
    log_path = run_dir / f"fold_{fold:02d}_{test_label}.log"
    id_str = f"  [identifier={freqai_identifier}]" if freqai_identifier else ""
    print(f"[fold {fold}] backtesting {test_label} (full window {timerange}){id_str} ...", flush=True)

    # Dynamic pair filtering — drop pairs that lack history for this fold's window
    base_config_file = config if config else "config.json"
    base_config_path = f"/home/ubuntu/var/www/html/trade/freqtrade/user_data/{base_config_file}"
    filtered_config = base_config_file
    try:
        scripts_path = "/home/ubuntu/var/www/html/trade/scripts"
        if scripts_path not in sys.path:
            sys.path.append(scripts_path)
        from lib.pair_filter import filter_pairs_for_timerange
        filtered_config = filter_pairs_for_timerange(base_config_path, train_start)
    except Exception as e:
        print(f"[walk_forward] Pair filter failed, using base config: {e}", flush=True)

    # v2: per-fold isolated result sentinel — prevents race condition in parallel mode
    fold_sentinel = (
        COMPOSE_DIR / "user_data" / "backtest_results" / f".last_result_f{fold:02d}.json"
    )
    fold_sentinel.unlink(missing_ok=True)

    cmd = [
        "docker-compose", "run", "--rm",
        # Large wallet so stake depletion never silences a test window
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
        # v2: LightGBM multi-threading — fill available cores without context thrashing
        "-e", f"FREQTRADE__FREQAI__MODEL_TRAINING_PARAMETERS__NUM_THREADS={lgbm_threads}",
    ]

    # Bug A fix (2026-05-20): pass live env vars so WF tests the exact live config,
    # not the strategy class defaults (LT=1.5, ST=-1.5, K_SL=1.0 ...).
    for key, val in _read_env_vars().items():
        cmd += ["-e", f"{key}={val}"]

    if freqai_identifier:
        # Each fold gets a unique identifier → forces fresh training, no lookahead bias
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
    cmd += ["--config", f"/freqtrade/user_data/{filtered_config}"]

    # Remove shared sentinel to prevent stale prior-fold result being silently reused
    LAST_RESULT.unlink(missing_ok=True)

    try:
        with log_path.open("w") as logf:
            proc = subprocess.run(
                cmd, cwd=COMPOSE_DIR,
                stdout=logf, stderr=subprocess.STDOUT,
                timeout=16200,  # 4.5h — supports 37-pair universe
            )
    finally:
        # Clean up temporary config generated by pair_filter
        if filtered_config and filtered_config.startswith("tmp_wf_config_"):
            temp_path = COMPOSE_DIR / "user_data" / filtered_config
            temp_path.unlink(missing_ok=True)
            print(f"[walk_forward] Cleaned up temporary config: {filtered_config}", flush=True)

    if proc.returncode != 0:
        print(f"  [fold {fold}] FAIL — see {log_path}", flush=True)
        return None

    # v2: prefer fold-specific sentinel; fall back to shared sentinel for compat
    sentinel = fold_sentinel if fold_sentinel.exists() else LAST_RESULT
    if not sentinel.exists():
        print(f"  [fold {fold}] FAIL — no result sentinel found after run", flush=True)
        return None

    target = run_dir / f"fold_{fold:02d}_result.json"
    target.write_bytes(sentinel.read_bytes())
    fold_sentinel.unlink(missing_ok=True)
    return target


def _run_fold_worker(kwargs: dict) -> tuple[int, Path | None]:
    """Top-level picklable worker for ProcessPoolExecutor.
    Must be a module-level function (not a lambda/closure) to be picklable.
    Returns (fold_number, result_path_or_None).
    """
    fold = kwargs["fold"]
    try:
        rp = run_backtest(
            strategy=kwargs["strategy"],
            tf=kwargs["tf"],
            train_start=kwargs["train_start"],
            test_start=kwargs["test_start"],
            test_end=kwargs["test_end"],
            run_dir=kwargs["run_dir"],
            fold=fold,
            freqai_identifier=kwargs["freqai_identifier"],
            config=kwargs["config"],
            lgbm_threads=kwargs["lgbm_threads"],
        )
        return fold, rp
    except Exception as exc:
        print(f"  [fold {fold}] worker exception: {exc}", flush=True)
        return fold, None


def _compute_metrics_from_trades(trades: list[dict], starting_balance: float = 10000.0) -> dict:
    """Compute trades/WR/PF/max_drawdown/sharpe from a per-trade list.

    Sharpe is annualised from daily aggregated PnL (not per-trade) —
    the standard Freqtrade convention. Drawdown is from the equity curve.
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
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

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
        day = (t.get("close_date") or "")[:10]
        if day:
            daily[day] = daily.get(day, 0.0) + p

    if len(daily) >= 2:
        import statistics
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

    The backtest timerange is train_start→test_end (so FreqAI has data to train on),
    but for walk-forward integrity we evaluate ONLY the test slice [test_start, test_end).
    We recompute sharpe and drawdown from per-trade data scoped to that window.
    """
    pointer = json.loads(result_path.read_text())
    actual_zip = pointer.get("latest_backtest")
    if not actual_zip:
        return None
    actual_path = COMPOSE_DIR / "user_data" / "backtest_results" / actual_zip
    if actual_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(actual_path) as zf:
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
    """Acceptance gates: WR>0.5, Sharpe>0.5, DD<0.2, PF>1.2."""
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
    current parse_fold() logic, without re-running any backtests."""
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
    p = argparse.ArgumentParser(description="FinBuddy Walk-Forward Validator v2 (parallel)")
    p.add_argument("--start", required=True, help="YYYY-MM-DD outer window start")
    p.add_argument("--end", required=True, help="YYYY-MM-DD outer window end")
    p.add_argument("--train-months", type=int, default=6)
    p.add_argument("--test-months", type=int, default=1)
    p.add_argument("--slide-months", type=int, default=1)
    p.add_argument("--strategy", default="FinBuddyFreqAI_v23")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--config", help="Custom config filename inside user_data/")
    p.add_argument("--skip-download", action="store_true", help="Skip data download")
    p.add_argument("--max-workers", type=int, default=3,
                   help="Parallel fold workers (default=3; set 1 for sequential/debug)")
    p.add_argument("--lgbm-threads", type=int, default=2,
                   help="LightGBM num_threads per fold worker (default=2)")
    p.add_argument("--reparse", metavar="RUN_DIR",
                   help="Re-aggregate an existing walkforward_results/<run_id>/ (no backtests re-run)")
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

    max_w = min(max(args.max_workers, 1), 3)  # clamp: at least 1, at most 3 on this server
    print(f"Walk-forward run: {run_dir}")
    print(f"Mode: {'PARALLEL' if max_w > 1 else 'sequential'} "
          f"(max_workers={max_w}, lgbm_threads={args.lgbm_threads})")

    # Unique throwaway FreqAI identifier per fold — forces fresh in-fold training,
    # preventing FreqAI from loading live-bot models trained on future data (lookahead bias).
    fold_identifier_base = f"wf_{run_stamp}"

    if not args.skip_download:
        download_data(args.start, args.end, args.timeframe)
    else:
        print("[data] Skipping download (--skip-download set).")

    # Build fold specs — each is a self-contained dict passable to the worker
    fold_specs = []
    for fold, ts, te, vs, ve in daterange_folds(
        args.start, args.end, args.train_months, args.test_months, args.slide_months
    ):
        fold_specs.append({
            "fold": fold,
            "strategy": args.strategy,
            "tf": args.timeframe,
            "train_start": ts,
            "test_start": vs,
            "test_end": ve,
            "run_dir": run_dir,
            "freqai_identifier": f"{fold_identifier_base}_f{fold:02d}",
            "config": args.config,
            "lgbm_threads": args.lgbm_threads,
        })

    print(f"Total folds: {len(fold_specs)}")

    # ── Execution: parallel or sequential ──────────────────────────────────
    fold_results: dict[int, Path | None] = {}

    if max_w <= 1:
        # Sequential — identical behaviour to v1, useful for debugging
        for spec in fold_specs:
            fold = spec["fold"]
            rp = run_backtest(
                strategy=spec["strategy"], tf=spec["tf"],
                train_start=spec["train_start"], test_start=spec["test_start"],
                test_end=spec["test_end"], run_dir=spec["run_dir"], fold=fold,
                freqai_identifier=spec["freqai_identifier"], config=spec["config"],
                lgbm_threads=spec["lgbm_threads"],
            )
            fold_results[fold] = rp
    else:
        print(f"Submitting {len(fold_specs)} folds to ProcessPoolExecutor(max_workers={max_w}) ...")
        with ProcessPoolExecutor(max_workers=max_w) as executor:
            future_to_fold = {
                executor.submit(_run_fold_worker, spec): spec["fold"]
                for spec in fold_specs
            }
            for future in as_completed(future_to_fold):
                fold_num = future_to_fold[future]
                try:
                    returned_fold, rp = future.result()
                    fold_results[returned_fold] = rp
                    status = "✓ done" if rp else "✗ failed"
                    print(f"  [fold {fold_num}] {status}", flush=True)
                except Exception as exc:
                    print(f"  [fold {fold_num}] ✗ executor exception: {exc}", flush=True)
                    fold_results[fold_num] = None

    # ── Aggregate in fold order (deterministic regardless of completion order) ──
    folds: list[FoldResult] = []
    for spec in sorted(fold_specs, key=lambda s: s["fold"]):
        fold = spec["fold"]
        rp = fold_results.get(fold)
        if rp is None:
            print(f"  [fold {fold}] skipped (no result)")
            continue
        fr = parse_fold(rp, fold, spec["test_start"], spec["test_end"])
        if fr is None:
            print(f"  [fold {fold}] result parse failed, skipping")
            continue
        folds.append(fr)
        print(f"  [fold {fold}] trades={fr.trades} WR={fr.win_rate:.1%} "
              f"Sharpe={fr.sharpe:.3f} DD={fr.max_drawdown:.1%} PF={fr.profit_factor:.3f}")

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
