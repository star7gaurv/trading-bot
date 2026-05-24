"""
runner.py — Pop next queued hypothesis, run its backtest, log result.

Designed to be called by cron every N minutes. One run = one experiment.
Cron suggestion: every 30 min, 4 parallel runners on different hypothesis_ids
(future enhancement; v1 is single-threaded).

CLI:
  python scripts/brain/runner.py           # run next hypothesis from queue
  python scripts/brain/runner.py --max 5   # run up to 5 in sequence
  python scripts/brain/runner.py --status  # print queue + log summary, no run

Safety:
  - Never modifies the live v22 config — runs all experiments via docker-compose
    with environment-variable overrides + per-experiment freqai identifier.
  - 30-minute hard timeout per experiment to prevent runaway training.
  - Failed experiments are logged with error msg, queue advances.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Allow importing sibling module when invoked directly
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from experiment_log import (
    read_queue, mark_completed, mark_failed, summary_stats
)
from telegram_template import send as tg_send, Subsystem, Status

ROOT = Path("/home/ubuntu/var/www/html/trade")
COMPOSE_DIR = ROOT / "freqtrade"
USER_DATA = ROOT / "freqtrade" / "user_data"
RESULTS_DIR = USER_DATA / "backtest_results"
BACKTEST_TIMEOUT_S = 6000  # 100 min hard cap for the whole experiment (2026-05-24: reverted to
# single-group of all 37 pairs after CPU starvation audit. 37 pairs ~74 min on the live config; the
# 100 min cap leaves comfortable buffer without re-introducing pair-split CPU overhead.
LOCK_FILE = Path("/home/ubuntu/.finbuddy/state/brain_runner.lock")  # prevent overlapping cron runs


# Telegram via unified template (scripts/lib/telegram_template.py)


# ── Pair-group config helpers (2026-05-23 — parallel split fix) ───────────

def _load_brain_pairs(config_file: str) -> list[str]:
    """Return full pair_whitelist from the brain config JSON."""
    cfg_path = USER_DATA / config_file
    try:
        cfg = json.loads(cfg_path.read_text())
        return cfg.get("exchange", {}).get("pair_whitelist", [])
    except Exception:
        return []


def _filter_pairs_for_window(pairs: list[str], window: str) -> list[str]:
    """Remove pairs that don't have enough historical data for this brain window.

    FreqAI needs train_period_days (90) + startup_candle_count (2400 × 15m = 25 days)
    = ~115 days of data BEFORE the window start date. We use 120 days as a safe margin.

    Late-listed pairs (TON → 2024-03-01, ENA → 2024-04-02, etc.) crash the FreqTrade
    docker container mid-training with "all training data dropped due to NaNs", which
    causes the entire group backtest to fail with AttributeError: 'NoneType'.predict.

    Returns only pairs with data coverage starting at or before required_start.
    Pairs whose feather file cannot be read are kept (fail open — let FreqTrade handle it).
    """
    from datetime import timedelta

    # Map window name → window start date string (YYYYMMDD)
    _WINDOW_STARTS = {
        "bull_2024Q1": "20240101",
        "bull_2024Q2": "20240401",
        "bear_2025Q1": "20250101",
        "bull_2025Q4": "20251001",
        "bear_2026Q1": "20260101",
    }
    start_str = _WINDOW_STARTS.get(window)
    if not start_str:
        return pairs  # unknown window — pass through unchanged

    import pandas as pd
    from datetime import timezone as _tz

    window_start = datetime.strptime(start_str, "%Y%m%d").replace(tzinfo=_tz.utc)
    required_start = window_start - timedelta(days=120)  # 90 train + 30 startup buffer

    data_dir = USER_DATA / "data" / "binance" / "futures"
    filtered, skipped = [], []

    for pair in pairs:
        # BTC/USDT:USDT → BTC_USDT_USDT-15m-futures.feather
        fname = pair.replace("/", "_").replace(":", "_") + "-15m-futures.feather"
        fpath = data_dir / fname
        if not fpath.exists():
            filtered.append(pair)  # file missing → keep (fail open)
            continue
        try:
            df = pd.read_feather(fpath, columns=["date"])
            earliest = df["date"].min()
            if hasattr(earliest, "tzinfo") and earliest.tzinfo is None:
                earliest = earliest.tz_localize("UTC")
            if earliest > required_start:
                skipped.append(pair)
                continue
        except Exception:
            pass  # unreadable → keep (fail open)
        filtered.append(pair)

    if skipped:
        print(
            f"[brain] window={window}: skipped {len(skipped)} late-listed pairs "
            f"(need data before {required_start.date()}): {skipped}",
            file=sys.stderr,
        )
    return filtered


def _create_pair_group_config(config_file: str, pairs_subset: list[str], group_id: str) -> str:
    """Write a temporary config with only `pairs_subset`. Returns temp filename (not full path)."""
    cfg_path = USER_DATA / config_file
    cfg = json.loads(cfg_path.read_text())
    cfg.setdefault("exchange", {})["pair_whitelist"] = pairs_subset
    tmp_name = f"tmp_brain_group_{group_id}.json"
    (USER_DATA / tmp_name).write_text(json.dumps(cfg, indent=2))
    return tmp_name


def _parse_raw_trades_from_zip(zip_path: Path) -> list[dict]:
    """Extract the raw per-trade list from a FreqTrade backtest result zip."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            json_names = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_names:
                return []
            with zf.open(json_names[0]) as jf:
                data = json.load(jf)
        strategy_data = data.get("strategy", {})
        if not strategy_data:
            return []
        s = strategy_data[next(iter(strategy_data))]
        return s.get("trades", []) or []
    except Exception as e:
        print(f"[parse_raw] error: {e}", file=sys.stderr)
        return []


def _compute_metrics_from_raw_trades(trades: list[dict]) -> dict:
    """Compute aggregated brain metrics from a list of raw FreqTrade trade dicts."""
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "wr": 0.0, "sharpe": 0.0, "pf": 0.0,
            "profit_pct": 0.0, "max_dd": 0.0,
            "long_count": 0, "short_count": 0,
            "exit_signal_count": 0, "exit_signal_wr": 0.0,
            "stop_loss_count": 0,
        }

    wins = sum(1 for t in trades if float(t.get("profit_abs") or 0) > 0)
    losses = n - wins
    profits = [float(t.get("profit_abs") or 0.0) for t in trades]
    gross_win  = sum(p for p in profits if p > 0)
    gross_loss = -sum(p for p in profits if p < 0)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    # Profit % relative to a 10000 USDT virtual wallet (brain uses DRY_RUN_WALLET=10000)
    profit_pct = round(sum(profits) / 10000.0 * 100, 3)

    # Max drawdown from equity curve
    equity = 10000.0
    peak = equity
    max_dd = 0.0
    sorted_trades = sorted(trades, key=lambda t: t.get("close_date") or "")
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
        d = (t.get("close_date") or "")[:10]
        if d:
            daily[d] = daily.get(d, 0.0) + p

    # Sharpe from daily P&L
    daily_pnl = list(daily.values())
    if len(daily_pnl) >= 2:
        import statistics
        mu_d = statistics.mean(daily_pnl)
        sd_d = statistics.stdev(daily_pnl)
        sharpe = round((mu_d / sd_d * (252 ** 0.5)) if sd_d > 0 else 0.0, 3)
    else:
        sharpe = 0.0

    long_count  = sum(1 for t in trades if not t.get("is_short", False))
    short_count = sum(1 for t in trades if t.get("is_short", False))
    exit_signal_count = sum(1 for t in trades if t.get("exit_reason") == "exit_signal")
    exit_signal_wins  = sum(1 for t in trades if t.get("exit_reason") == "exit_signal" and float(t.get("profit_abs") or 0) > 0)
    exit_signal_wr    = (exit_signal_wins / exit_signal_count) if exit_signal_count else 0.0
    stop_loss_count   = sum(1 for t in trades if t.get("exit_reason") == "stop_loss")

    return {
        "trades":            n,
        "wr":                round(wins / n, 4),
        "sharpe":            sharpe,
        "pf":                round(pf, 3),
        "profit_pct":        profit_pct,
        "max_dd":            round(max_dd * 100, 3),
        "long_count":        long_count,
        "short_count":       short_count,
        "exit_signal_count": exit_signal_count,
        "exit_signal_wr":    round(exit_signal_wr, 4),
        "stop_loss_count":   stop_loss_count,
    }


# ── Result parsing ────────────────────────────────────────────────────────

def parse_latest_zip() -> dict | None:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None
    return parse_zip(zips[-1])


def parse_zip(zip_path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            json_names = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_names:
                return None
            with zf.open(json_names[0]) as jf:
                data = json.load(jf)

        strategy_data = data.get("strategy", {})
        if not strategy_data:
            return None
        s = strategy_data[next(iter(strategy_data))]
        trades = s.get("total_trades", 0)
        if trades == 0:
            return {
                "trades": 0, "wr": 0.0, "sharpe": 0.0, "pf": 0.0,
                "profit_pct": 0.0, "max_dd": 0.0,
                "long_count": 0, "short_count": 0,
                "exit_signal_count": 0, "exit_signal_wr": 0.0,
                "stop_loss_count": 0,
            }
        raw_wr = s.get("winrate") or (s.get("wins", 0) / trades)

        # FreqTrade schema: *_reason_summary is a LIST of dicts, each with 'key' field.
        # Normalize to {key: row_dict} for easy lookup.
        def _to_dict(value) -> dict:
            if isinstance(value, list):
                return {row.get("key", ""): row for row in value if isinstance(row, dict)}
            if isinstance(value, dict):
                return value
            return {}

        exit_reasons = _to_dict(s.get("exit_reason_summary"))
        exit_signal = exit_reasons.get("exit_signal", {})
        # FreqTrade uses 'trades' (not 'count') as the count field in *_summary rows.
        exit_signal_count = int(exit_signal.get("trades", exit_signal.get("count", 0)) or 0)
        exit_signal_wins  = int(exit_signal.get("wins", 0) or 0)
        exit_signal_wr    = (exit_signal_wins / exit_signal_count) if exit_signal_count else 0.0
        stop_loss_row     = exit_reasons.get("stop_loss", {})
        stop_loss_count   = int(stop_loss_row.get("trades", stop_loss_row.get("count", 0)) or 0)

        enter_reasons = _to_dict(s.get("enter_reason_summary"))
        long_count  = sum(int(v.get("trades", v.get("count", 0)) or 0) for k, v in enter_reasons.items() if "long" in (k or ""))
        short_count = sum(int(v.get("trades", v.get("count", 0)) or 0) for k, v in enter_reasons.items() if "short" in (k or ""))

        # Fallback: derive L/S from the trades array (always present), if summary is empty.
        if long_count == 0 and short_count == 0:
            trades_list = s.get("trades", [])
            if isinstance(trades_list, list):
                for t in trades_list:
                    if t.get("is_short"):
                        short_count += 1
                    else:
                        long_count += 1

        return {
            "trades":            int(trades),
            "wr":                round(float(raw_wr), 4),
            "sharpe":            round(float(s.get("sharpe", 0.0) or 0.0), 3),
            "pf":                round(float(s.get("profit_factor", 0.0) or 0.0), 3),
            "profit_pct":        round(float(s.get("profit_total") or 0.0) * 100, 3),
            "max_dd":            round(float(s.get("max_drawdown_account", 0.0) or 0.0) * 100, 3),
            "long_count":        long_count,
            "short_count":       short_count,
            "exit_signal_count": exit_signal_count,
            "exit_signal_wr":    round(exit_signal_wr, 4),
            "stop_loss_count":   stop_loss_count,
        }
    except Exception as e:
        print(f"[parse] error: {e}", file=sys.stderr)
        return None


# ── Run a single hypothesis (parallel pair-group split, 2026-05-23) ───────

def _build_env_args(cfg: dict, identifier: str) -> list[str]:
    """Build docker -e env args for one brain experiment."""
    arch = cfg.get("arch", "v23")
    env_args = [
        "-e", f"FREQAI_K_SL={cfg.get('k_sl', 1.0)}",
        "-e", f"FREQAI_K_TP={cfg.get('k_tp', 2.0)}",
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
        "-e", f"FREQTRADE__FREQAI__IDENTIFIER={identifier}",
        "-e", f"FREQTRADE__FREQAI__FEATURE_PARAMETERS__LABEL_PERIOD_CANDLES={cfg.get('label_period_candles', 24)}",
    ]
    if arch == "v22":
        env_args += ["-e", f"FREQAI_ML_THRESHOLD={cfg.get('ml_threshold', 0.60)}"]
    else:  # v23
        env_args += [
            "-e", f"FREQAI_LONG_THRESHOLD={cfg.get('long_threshold', 1.5)}",
            "-e", f"FREQAI_SHORT_THRESHOLD={cfg.get('short_threshold', -1.5)}",
            "-e", f"FREQAI_STABILITY_N={cfg.get('stability_n', 2)}",
            "-e", f"FREQAI_FEATURE_SET={cfg.get('feature_set', 'all')}",
            "-e", f"FREQAI_FILTER_DI={'true' if cfg.get('filter_di', True) else 'false'}",
            "-e", f"FREQAI_FILTER_SVM={'true' if cfg.get('filter_svm', True) else 'false'}",
        ]
    return env_args


def _run_hypothesis_group(
    h: dict,
    pairs_subset: list[str],
    group_suffix: str,
) -> list[dict]:
    """Run one docker backtest for a pair subset. Returns raw trade list or []."""
    cfg         = h["config"]
    config_file = cfg.get("config_file", "v23_regression_15m_di_config.json")
    timerange   = h["timerange"]
    identifier  = f"brain_{h['hypothesis_id']}_{group_suffix}_{int(time.time())}"

    tmp_config = _create_pair_group_config(config_file, pairs_subset, group_suffix)
    env_args   = _build_env_args(cfg, identifier)

    cmd = (
        ["docker-compose", "run", "--rm", "--no-deps"]
        + env_args
        + [
            "freqtrade",
            "backtesting",
            "--config", f"/freqtrade/user_data/{tmp_config}",
            "--strategy", cfg.get("strategy", "FinBuddyFreqAI_v23"),
            "--freqaimodel", cfg.get("freqaimodel", "LightGBMRegressor"),
            "--timerange", timerange,
            "--timeframe", cfg.get("timeframe", "15m"),
            "--export", "trades",
            "--cache", "none",
        ]
    )

    log_dir  = ROOT / "backtests"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"brain_{h['hypothesis_id']}_{group_suffix}.log"

    before = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    try:
        with log_file.open("w") as lf:
            proc = subprocess.run(
                cmd, cwd=str(COMPOSE_DIR), stdout=lf, stderr=subprocess.STDOUT,
                timeout=BACKTEST_TIMEOUT_S,
            )
    except subprocess.TimeoutExpired:
        _kill_orphan_containers(identifier)
        print(f"[brain] group {group_suffix} timeout for {h['hypothesis_id']}", file=sys.stderr)
        return []
    finally:
        # Always clean up temp config
        tmp_path = USER_DATA / tmp_config
        tmp_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        return []

    after    = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    new_zips = sorted(after - before, key=lambda p: p.stat().st_mtime)
    if not new_zips:
        return []
    return _parse_raw_trades_from_zip(new_zips[-1])


def run_hypothesis(h: dict) -> dict | None:
    """Execute one backtest as a single group of all pairs.

    REVERTED 2026-05-24 from the 2026-05-23 parallel pair-group split. The split was
    introduced to fit under the old 3900s timeout, but with BACKTEST_TIMEOUT_S=5400 (90m)
    a single backtest of all 37 pairs (~74 min) fits comfortably. Running a single
    container instead of two reduces concurrent CPU contention with the live bot.

    Combined with cron throttle */10 → */30 + flock (2026-05-24), this brings the brain
    down to one active backtest container at a time (~1.76 vCPU) instead of overlapping
    instances pinning the 4-core server.
    """
    cfg         = h["config"]
    config_file = cfg.get("config_file", "v23_regression_15m_di_config.json")

    all_pairs   = _load_brain_pairs(config_file)
    if not all_pairs:
        all_pairs = []

    # Drop pairs that don't have enough history for this window's training period.
    # Late-listed pairs (e.g. TON listed 2024-03-01) crash the docker container when
    # their training data is all NaNs.
    all_pairs = _filter_pairs_for_window(all_pairs, h.get("window", ""))

    t0 = time.time()

    trades = _run_hypothesis_group(h, all_pairs or [], "g0")
    elapsed = int(time.time() - t0)

    if not trades:
        return None

    metrics = _compute_metrics_from_raw_trades(trades)
    metrics["elapsed_s"] = elapsed
    return metrics


# ── Main loop ─────────────────────────────────────────────────────────────

def _kill_orphan_containers(identifier: str) -> None:
    """After a timeout/failure, kill any docker-compose run containers still running.

    Matches by FREQTRADE__FREQAI__IDENTIFIER env var on the container so we only
    kill THIS experiment's containers — never the live `freqtrade` container.
    """
    try:
        # List ephemeral run containers
        out = subprocess.run(
            ["docker", "ps", "--filter", "name=freqtrade-freqtrade-run", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        names = [n.strip() for n in out.stdout.splitlines() if n.strip()]
        for name in names:
            # Inspect env vars to find the identifier match
            try:
                env_out = subprocess.run(
                    ["docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", name],
                    capture_output=True, text=True, timeout=5,
                )
                if identifier in env_out.stdout:
                    subprocess.run(["docker", "stop", name], capture_output=True, timeout=15)
                    print(f"[brain] killed orphan container {name}")
            except Exception:
                pass
    except Exception as e:
        print(f"[brain] orphan cleanup failed: {e}", file=sys.stderr)


def _acquire_lock() -> bool:
    """OS-level exclusive lock via fcntl.flock (non-blocking).

    Returns True if the lock was acquired, False if another runner already holds it.

    Fix 16 (2026-05-23): replaced the previous PID-file TOCTOU approach with
    fcntl.flock — two cron instances starting within the same second could both
    find the lock "stale" and both proceed, causing duplicate experiments in the
    log. flock is atomic at the kernel level.

    The lock fd is stored in a module-level variable so _release_lock() can close it.
    """
    import fcntl, os as _os
    global _LOCK_FD
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_FD = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_LOCK_FD.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FD.write(f"{_os.getpid()}:{time.time()}\n")
        _LOCK_FD.flush()
        return True
    except BlockingIOError:
        _LOCK_FD.close()
        _LOCK_FD = None
        print("[brain] another runner is active (flock held) — skipping")
        return False


_LOCK_FD = None  # module-level fd kept open while lock is held


def _release_lock() -> None:
    import fcntl
    global _LOCK_FD
    if _LOCK_FD is not None:
        try:
            fcntl.flock(_LOCK_FD.fileno(), fcntl.LOCK_UN)
            _LOCK_FD.close()
        except Exception:
            pass
        _LOCK_FD = None
    LOCK_FILE.unlink(missing_ok=True)


def run_next(max_runs: int = 1, status_only: bool = False) -> int:
    if status_only:
        stats = summary_stats()
        print(json.dumps(stats, indent=2))
        return 0

    if not _acquire_lock():
        return 0

    try:
        completed = 0
        for _ in range(max_runs):
            queue = read_queue()
            if not queue:
                print("[brain] queue empty ? nothing to run")
                break

            # FIFO ordering by created_at
            queue.sort(key=lambda r: r.get("created_at", ""))
            h = queue[0]
            started = datetime.now(timezone.utc).isoformat()

            print(f"[brain] running {h['hypothesis_id']} ({h['band']}) on {h['window']}: {h['rationale']}")
            try:
                metrics = run_hypothesis(h)
            except Exception as e:
                print(f"[brain] exception running hypothesis {h['hypothesis_id']}: {e}", file=sys.stderr)
                _kill_orphan_containers(f"brain_{h['hypothesis_id']}")
                metrics = None

            if metrics is None:
                mark_failed(h, error="run_hypothesis returned None (timeout or exit non-zero)", started_at=started)
                print(f"[brain] FAILED {h['hypothesis_id']}")
                continue

            mark_completed(h, metrics, started_at=started)
            completed += 1

            # Telegram via unified template ? silent for per-experiment results
            # (avoid spamming the user; only promotion candidates make a sound)
            arch = h.get("config", {}).get("arch", "?")
            status = Status.OK if metrics.get("profit_pct", -1) > 0 else Status.INFO
            tg_send(
                subsystem=Subsystem.BRAIN_EXPERIMENT,
                status=status,
                title=f"#{h['hypothesis_id']} ? {arch} ? {h['band']}",
                fields={
                    "Window":   h["window"],
                    "Profit":   f"{metrics['profit_pct']:+.2f}%",
                    "Win Rate": f"{metrics['wr']*100:.1f}%",
                    "Sharpe":   f"{metrics['sharpe']:+.2f}",
                    "PF":       f"{metrics['pf']:.2f}",
                    "Trades":   f"{metrics['trades']} ({metrics['long_count']}L / {metrics['short_count']}S)",
                },
                context=h["rationale"],
                action=None,
                silent=True,   # auto-logged; no need to ping
            )
            print(f"[brain] DONE {h['hypothesis_id']} [{arch}] ? profit={metrics['profit_pct']}% WR={metrics['wr']*100:.1f}%")
    finally:
        _release_lock()

    return completed



if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FinBuddy Brain — autonomous experiment runner")
    p.add_argument("--max",    type=int, default=1, help="max experiments to run this invocation")
    p.add_argument("--status", action="store_true", help="print status, do not run")
    args = p.parse_args()
    sys.exit(0 if run_next(max_runs=args.max, status_only=args.status) >= 0 else 1)
