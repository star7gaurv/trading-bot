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
BACKTEST_TIMEOUT_S = 1800  # 30 min hard cap
LOCK_FILE = Path("/home/ubuntu/.finbuddy/state/brain_runner.lock")  # prevent overlapping cron runs


# Telegram via unified template (scripts/lib/telegram_template.py)


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


# ── Run a single hypothesis ───────────────────────────────────────────────

def run_hypothesis(h: dict) -> dict | None:
    """Execute one backtest. Routes env vars by architecture (v22 vs v23)."""
    cfg = h["config"]
    config_file = cfg.get("config_file", "v23_regression_15m_di_config.json")
    timerange   = h["timerange"]
    identifier  = f"brain_{h['hypothesis_id']}_{int(time.time())}"
    arch        = cfg.get("arch", "v23")

    # Architecture-aware env vars. Each strategy reads its own set.
    env_args = [
        "-e", f"FREQAI_K_SL={cfg.get('k_sl', 1.0)}",
        "-e", f"FREQAI_K_TP={cfg.get('k_tp', 2.0)}",
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
        "-e", f"FREQTRADE__FREQAI__IDENTIFIER={identifier}",
        "-e", f"FREQTRADE__FREQAI__FEATURE_PARAMETERS__LABEL_PERIOD_CANDLES={cfg.get('label_period_candles', 24)}",
    ]
    if arch == "v22":
        env_args += [
            "-e", f"FREQAI_ML_THRESHOLD={cfg.get('ml_threshold', 0.60)}",
        ]
    else:  # v23
        env_args += [
            "-e", f"FREQAI_LONG_THRESHOLD={cfg.get('long_threshold', 1.5)}",
            "-e", f"FREQAI_SHORT_THRESHOLD={cfg.get('short_threshold', -1.5)}",
            "-e", f"FREQAI_STABILITY_N={cfg.get('stability_n', 2)}",
        ]

    cmd = (
        ["docker-compose", "run", "--rm", "--no-deps"]
        + env_args
        + [
            "freqtrade",
            "backtesting",
            "--config", f"/freqtrade/user_data/{config_file}",
            "--strategy", cfg.get("strategy", "FinBuddyFreqAI_v23"),
            "--freqaimodel", cfg.get("freqaimodel", "LightGBMRegressor"),
            "--timerange", timerange,
            "--timeframe", cfg.get("timeframe", "15m"),
            "--export", "trades",
            "--cache", "none",
        ]
    )

    log_dir = ROOT / "backtests"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"brain_{h['hypothesis_id']}.log"

    before = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    t0 = time.time()
    try:
        with log_file.open("w") as lf:
            proc = subprocess.run(
                cmd, cwd=str(COMPOSE_DIR), stdout=lf, stderr=subprocess.STDOUT,
                timeout=BACKTEST_TIMEOUT_S,
            )
    except subprocess.TimeoutExpired:
        return None
    elapsed = int(time.time() - t0)

    if proc.returncode != 0:
        return None

    after = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    new_zips = sorted(after - before, key=lambda p: p.stat().st_mtime)
    if not new_zips:
        return None
    metrics = parse_zip(new_zips[-1])
    if metrics:
        metrics["elapsed_s"] = elapsed
    return metrics


# ── Main loop ─────────────────────────────────────────────────────────────

def _acquire_lock() -> bool:
    """Atomic file-based lock. Returns True if acquired, False if another runner is alive.

    Lock file content: PID + timestamp. If lock exists but PID is dead OR lock is older
    than 2× BACKTEST_TIMEOUT_S, it's stale — we steal it.
    """
    import os
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            content = LOCK_FILE.read_text().strip().split(":")
            pid, ts = int(content[0]), float(content[1])
        except Exception:
            pid, ts = -1, 0
        # Stale if PID dead or older than 2× timeout
        age = time.time() - ts
        pid_alive = True
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, ValueError):
            pid_alive = False
        if pid_alive and age < 2 * BACKTEST_TIMEOUT_S:
            print(f"[brain] another runner active (pid={pid}, age={int(age)}s) — skipping")
            return False
        print(f"[brain] stale lock (pid={pid}, age={int(age)}s) — stealing")
    LOCK_FILE.write_text(f"{os.getpid()}:{time.time()}")
    return True


def _release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def run_next(max_runs: int = 1, status_only: bool = False) -> int:
    if status_only:
        stats = summary_stats()
        print(json.dumps(stats, indent=2))
        return 0

    if not _acquire_lock():
        return 0

    completed = 0
    for _ in range(max_runs):
        queue = read_queue()
        if not queue:
            print("[brain] queue empty — nothing to run")
            break

        # FIFO ordering by created_at
        queue.sort(key=lambda r: r.get("created_at", ""))
        h = queue[0]
        started = datetime.now(timezone.utc).isoformat()

        print(f"[brain] running {h['hypothesis_id']} ({h['band']}) on {h['window']}: {h['rationale']}")
        metrics = run_hypothesis(h)

        if metrics is None:
            mark_failed(h, error="run_hypothesis returned None (timeout or exit non-zero)", started_at=started)
            print(f"[brain] FAILED {h['hypothesis_id']}")
            continue

        mark_completed(h, metrics, started_at=started)
        completed += 1

        # Telegram via unified template — silent for per-experiment results
        # (avoid spamming the user; only promotion candidates make a sound)
        arch = h.get("config", {}).get("arch", "?")
        status = Status.OK if metrics.get("profit_pct", -1) > 0 else Status.INFO
        tg_send(
            subsystem=Subsystem.BRAIN_EXPERIMENT,
            status=status,
            title=f"#{h['hypothesis_id']} · {arch} · {h['band']}",
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
        print(f"[brain] DONE {h['hypothesis_id']} [{arch}] → profit={metrics['profit_pct']}% WR={metrics['wr']*100:.1f}%")

    _release_lock()
    return completed


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FinBuddy Brain — autonomous experiment runner")
    p.add_argument("--max",    type=int, default=1, help="max experiments to run this invocation")
    p.add_argument("--status", action="store_true", help="print status, do not run")
    args = p.parse_args()
    sys.exit(0 if run_next(max_runs=args.max, status_only=args.status) >= 0 else 1)
