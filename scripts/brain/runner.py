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
import hashlib
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
    read_queue, mark_completed, mark_failed, mark_scout_failed,
    experiments_today_count, summary_stats,
    prioritize_same_config, queue_missing_windows,
    prioritize_regime_windows,
    next_alternating, last_completed_window_type,
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
        "bull_2021":   "20210101",   # deep-history stress windows (2026-06-17): MUST be listed
        "crash_2022":  "20220501",   # here or the filter falls through and late-listed pairs
        "bull_2024Q1": "20240101",   # reach FreqTrade with all-NaN data → model trains to None →
        "bear_2024Q2": "20240401",   # AttributeError: 'NoneType'.predict crashes the whole run.
        "bull_2024Q4": "20241001",   # This was the root cause of the recurring crash_2022 failures.
        "bear_2025Q1": "20250101",   # (honest window names 2026-06-19: bull_2024Q2→bear_2024Q2,
        "bear_2025Q4": "20251001",   #  bull_2025Q4→bear_2025Q4; added genuine bull_2024Q4.)
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


def _create_pair_group_config(
    config_file: str,
    pairs_subset: list[str],
    group_id: str,
    lgbm_overrides: dict | None = None,
) -> str:
    """Write a temporary config with only `pairs_subset` and optional LightGBM overrides.

    lgbm_overrides keys (e.g. 'num_leaves', 'learning_rate') are patched into
    freqai.model_training_parameters so each hypothesis can test different tree shapes.
    Returns temp filename (not full path).
    """
    cfg_path = USER_DATA / config_file
    cfg = json.loads(cfg_path.read_text())
    cfg.setdefault("exchange", {})["pair_whitelist"] = pairs_subset
    if lgbm_overrides:
        cfg.setdefault("freqai", {}).setdefault("model_training_parameters", {}).update(lgbm_overrides)
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
            "stop_loss_count": 0, "stop_loss_exit_rate": 0.0,
            "time_limit_exit_count": 0, "time_limit_exit_rate": 0.0,
            "pred_persist_exit_count": 0, "pred_persist_exit_wr": 0.0,
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
    time_limit_exit_count = sum(1 for t in trades if t.get("exit_reason") == "time_limit_exit")
    pred_persist_exit_count = sum(1 for t in trades if t.get("exit_reason") == "pred_persist_exit")
    pred_persist_exit_wins  = sum(1 for t in trades if t.get("exit_reason") == "pred_persist_exit" and float(t.get("profit_abs") or 0) > 0)
    pred_persist_exit_wr    = (pred_persist_exit_wins / pred_persist_exit_count) if pred_persist_exit_count else 0.0

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
        "stop_loss_exit_rate": round(stop_loss_count / n, 4),
        "time_limit_exit_count": time_limit_exit_count,
        "time_limit_exit_rate": round(time_limit_exit_count / n, 4),
        "pred_persist_exit_count": pred_persist_exit_count,
        "pred_persist_exit_wr": round(pred_persist_exit_wr, 4),
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
                "stop_loss_count": 0, "stop_loss_exit_rate": 0.0,
                "time_limit_exit_count": 0, "time_limit_exit_rate": 0.0,
                "pred_persist_exit_count": 0, "pred_persist_exit_wr": 0.0,
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
        time_limit_row    = exit_reasons.get("time_limit_exit", {})
        time_limit_exit_count = int(time_limit_row.get("trades", time_limit_row.get("count", 0)) or 0)
        pred_persist_row  = exit_reasons.get("pred_persist_exit", {})
        pred_persist_exit_count = int(pred_persist_row.get("trades", pred_persist_row.get("count", 0)) or 0)
        pred_persist_exit_wins  = int(pred_persist_row.get("wins", 0) or 0)
        pred_persist_exit_wr    = (pred_persist_exit_wins / pred_persist_exit_count) if pred_persist_exit_count else 0.0

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
            "stop_loss_exit_rate": round(stop_loss_count / trades, 4) if trades else 0.0,
            "time_limit_exit_count": time_limit_exit_count,
            "time_limit_exit_rate": round(time_limit_exit_count / trades, 4) if trades else 0.0,
            "pred_persist_exit_count": pred_persist_exit_count,
            "pred_persist_exit_wr": round(pred_persist_exit_wr, 4),
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
        # Only pass label_period_candles when explicitly set to an integer.
        # If null/None → omit env var so FreqTrade uses the config file default (12).
        # Passing "None" as a string causes FreqTrade schema validation to crash.
        *(["-e", f"FREQTRADE__FREQAI__FEATURE_PARAMETERS__LABEL_PERIOD_CANDLES={cfg['label_period_candles']}"]
          if cfg.get('label_period_candles') is not None else []),
        # Bypass the pair-regime gate in brain backtests (2026-05-26).
        # The gate uses LIVE rolling trade stats (last 30d) which are irrelevant
        # to historical test windows. e.g. OP blocked in BEAR because it has a
        # bad recent WR — but when testing bull_2024Q1, OP in 2024 is unrelated
        # to 2026 live stats. Using live stats here contaminates results.
        # Same fix applied to walk_forward.py for the same reason.
        "-e", "FREQAI_DISABLE_PAIR_REGIME_GATE=1",
        # Neutral WR override (2026-05-27): live .env has FINBUDDY_RECENT_WR=0.42
        # (current bot is losing). docker-compose.yml forwards it to all containers.
        # In BEAR+bad_WR, _compute_dynamic_thresholds applies 1.3×1.26=1.64× multiplier
        # → effective_lt = e.g. 2.0×1.64=3.28 on a z-scored N(0,1) model → near 0 trades.
        # Override to 0.55 (neutral) so the brain evaluates configs at their stated thresholds.
        # Same root cause as the WF 0-trade fix in walk_forward.py.
        "-e", "FINBUDDY_RECENT_WR=0.55",
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
        # C1/C3 entry-overhaul params (2026-06-11) — only passed when present so
        # existing configs keep their hashes and default behavior (absolute mode).
        if cfg.get("entry_mode"):
            env_args += ["-e", f"FREQAI_ENTRY_MODE={cfg['entry_mode']}"]
        if cfg.get("entry_quantile") is not None:
            env_args += ["-e", f"FREQAI_ENTRY_QUANTILE={cfg['entry_quantile']}"]
        if cfg.get("bounce_guard") is not None:
            env_args += ["-e", f"FREQAI_BOUNCE_GUARD={'1' if cfg['bounce_guard'] else '0'}"]
        # B1/C5 feature-set variants (2026-06-11)
        if cfg.get("prune_indicators") is not None:
            env_args += ["-e", f"FREQAI_PRUNE_INDICATORS={'1' if cfg['prune_indicators'] else '0'}"]
        if cfg.get("perpair_oi") is not None:
            env_args += ["-e", f"FREQAI_PERPAIR_OI={'1' if cfg['perpair_oi'] else '0'}"]
        # Phase 3 meta-labeling (2026-06-17). meta_label changes the TRAINED targets (in
        # _TRAIN_SHAPE_KEYS); meta_threshold is a serve-time gate (NOT in shape keys — same
        # trained model can A/B different thresholds). Pair with freqaimodel=
        # LightGBMRegressorMultiTarget so the extra targets get their own models.
        if cfg.get("meta_label") is not None:
            env_args += ["-e", f"FREQAI_META_LABEL={'1' if cfg['meta_label'] else '0'}"]
        if cfg.get("meta_threshold") is not None:
            env_args += ["-e", f"FREQAI_META_THRESHOLD={cfg['meta_threshold']}"]
        # Corrected meta-label geometry (2026-06-20). These change the TRAINED meta target →
        # they ARE in _TRAIN_SHAPE_KEYS (own cache family, distinct from the old broken label).
        if cfg.get("meta_tp_mult") is not None:
            env_args += ["-e", f"FREQAI_META_TP_MULT={cfg['meta_tp_mult']}"]
        if cfg.get("meta_sl_mult") is not None:
            env_args += ["-e", f"FREQAI_META_SL_MULT={cfg['meta_sl_mult']}"]
        if cfg.get("meta_horizon") is not None:
            env_args += ["-e", f"FREQAI_META_HORIZON={cfg['meta_horizon']}"]
        if cfg.get("meta_fee_pct") is not None:
            env_args += ["-e", f"FREQAI_META_FEE_PCT={cfg['meta_fee_pct']}"]
        # meta_dump is a serve-time eval side-effect (NOT in shape keys → cache still hits).
        if cfg.get("meta_dump") is not None:
            env_args += ["-e", f"FREQAI_META_DUMP={'1' if cfg['meta_dump'] else '0'}"]
        # EMA-200 primary-trend filter (2026-06-23): serve-time entry gate only — never long
        # below EMA-200, never short above. Does NOT change trained model → excluded from
        # _TRAIN_SHAPE_KEYS. A/B-able on cached predictions (same family as the base experiment).
        if cfg.get("trend_filter") is not None:
            env_args += ["-e", f"FREQAI_TREND_FILTER={'1' if cfg['trend_filter'] else '0'}"]
        # Lever 3 exit-side knobs (2026-07-08) — all serve-time (trading-only), so
        # NOT in _TRAIN_SHAPE_KEYS: A/B variants reuse the same cached family model.
        if cfg.get("threshold_floor") is not None:
            env_args += ["-e", f"FREQAI_THRESHOLD_FLOOR={'1' if cfg['threshold_floor'] else '0'}"]
        if cfg.get("progress_cut") is not None:
            env_args += ["-e", f"FREQAI_PROGRESS_CUT={'1' if cfg['progress_cut'] else '0'}"]
        if cfg.get("progress_cut_candles") is not None:
            env_args += ["-e", f"FREQAI_PROGRESS_CUT_CANDLES={cfg['progress_cut_candles']}"]
        if cfg.get("progress_cut_profit") is not None:
            env_args += ["-e", f"FREQAI_PROGRESS_CUT_PROFIT={cfg['progress_cut_profit']}"]
        if cfg.get("partial_tp") is not None:
            env_args += ["-e", f"FREQAI_PARTIAL_TP={'1' if cfg['partial_tp'] else '0'}"]
            # adjust_trade_position is only called when position adjustment is on.
            env_args += ["-e", "FREQTRADE__POSITION_ADJUSTMENT_ENABLE=true"]
        if cfg.get("partial_tp_trigger") is not None:
            env_args += ["-e", f"FREQAI_PARTIAL_TP_TRIGGER={cfg['partial_tp_trigger']}"]
        if cfg.get("partial_tp_fraction") is not None:
            env_args += ["-e", f"FREQAI_PARTIAL_TP_FRACTION={cfg['partial_tp_fraction']}"]
        # 2026-07-17: probe_scale was built 2026-06-23 alongside progress_cut/partial_tp but
        # its env forwarding was never added here — any past experiment with probe_scale set
        # silently ran with the live default (FREQAI_PROBE_SCALE=0), i.e. was a no-op duplicate
        # of the baseline. Fixing the same 3-layer gap partial_tp already had fixed on 07-08.
        if cfg.get("probe_scale") is not None:
            env_args += ["-e", f"FREQAI_PROBE_SCALE={'1' if cfg['probe_scale'] else '0'}"]
            # adjust_trade_position is only called when position adjustment is on.
            env_args += ["-e", "FREQTRADE__POSITION_ADJUSTMENT_ENABLE=true"]
        if cfg.get("probe_fraction") is not None:
            env_args += ["-e", f"FREQAI_PROBE_FRACTION={cfg['probe_fraction']}"]
        if cfg.get("probe_confirm_pct") is not None:
            env_args += ["-e", f"FREQAI_PROBE_CONFIRM_PCT={cfg['probe_confirm_pct']}"]
        if cfg.get("probe_window") is not None:
            env_args += ["-e", f"FREQAI_PROBE_WINDOW={cfg['probe_window']}"]
        # NEUTRAL-regime threshold multiplier override (2026-08-31) — serve-time gate,
        # same category as trend_filter/threshold_floor: NOT in _TRAIN_SHAPE_KEYS.
        if cfg.get("neutral_long_mult") is not None:
            env_args += ["-e", f"FREQAI_NEUTRAL_LONG_MULT={cfg['neutral_long_mult']}"]
        if cfg.get("neutral_short_mult") is not None:
            env_args += ["-e", f"FREQAI_NEUTRAL_SHORT_MULT={cfg['neutral_short_mult']}"]
        if cfg.get("neutral_exit_mult_long") is not None:
            env_args += ["-e", f"FREQAI_NEUTRAL_EXIT_MULT_LONG={cfg['neutral_exit_mult_long']}"]
        if cfg.get("neutral_exit_mult_short") is not None:
            env_args += ["-e", f"FREQAI_NEUTRAL_EXIT_MULT_SHORT={cfg['neutral_exit_mult_short']}"]
        # Exit-edge knobs (2026-08-31) — serve-time gates, NOT in _TRAIN_SHAPE_KEYS.
        if cfg.get("exit_hysteresis_frac") is not None:
            env_args += ["-e", f"FREQAI_EXIT_HYSTERESIS_FRAC={cfg['exit_hysteresis_frac']}"]
        if cfg.get("trail_leverage_fix") is not None:
            env_args += ["-e", f"FREQAI_TRAIL_LEVERAGE_FIX={'1' if cfg['trail_leverage_fix'] else '0'}"]
        # Persistence-exit / time-limit-grace knobs (2026-09-01) — serve-time gates,
        # NOT in _TRAIN_SHAPE_KEYS (same family as exit_hysteresis_frac/trail_leverage_fix).
        if cfg.get("pred_persist_exit") is not None:
            env_args += ["-e", f"FREQAI_PRED_PERSIST_EXIT={'1' if cfg['pred_persist_exit'] else '0'}"]
        if cfg.get("pred_persist_exit_n") is not None:
            env_args += ["-e", f"FREQAI_PRED_PERSIST_EXIT_N={cfg['pred_persist_exit_n']}"]
        if cfg.get("pred_persist_exit_level") is not None:
            env_args += ["-e", f"FREQAI_PRED_PERSIST_EXIT_LEVEL={cfg['pred_persist_exit_level']}"]
        if cfg.get("pred_persist_exit_min_loss") is not None:
            env_args += ["-e", f"FREQAI_PRED_PERSIST_EXIT_MIN_LOSS={cfg['pred_persist_exit_min_loss']}"]
        if cfg.get("time_limit_grace") is not None:
            env_args += ["-e", f"FREQAI_TIME_LIMIT_GRACE={'1' if cfg['time_limit_grace'] else '0'}"]
        if cfg.get("time_limit_grace_candles") is not None:
            env_args += ["-e", f"FREQAI_TIME_LIMIT_GRACE_CANDLES={cfg['time_limit_grace_candles']}"]
        if cfg.get("time_limit_grace_level") is not None:
            env_args += ["-e", f"FREQAI_TIME_LIMIT_GRACE_LEVEL={cfg['time_limit_grace_level']}"]
        if cfg.get("time_limit_grace_max_extensions") is not None:
            env_args += ["-e", f"FREQAI_TIME_LIMIT_GRACE_MAX_EXTENSIONS={cfg['time_limit_grace_max_extensions']}"]
    return env_args


# Model-cache family key (2026-06-12). Fields that change WHAT GETS TRAINED:
# feature pipeline (config_file carries include_timeframes/shifted_candles/
# periods/DI/SVM), feature gates, target horizon, model class + hyperparams.
# Deliberately EXCLUDED (trading-only, applied on top of identical predictions):
# long/short_threshold, k_tp, k_sl, stability_n, entry_mode, entry_quantile,
# bounce_guard. v23's set_freqai_targets uses ONLY label_period_candles
# (verified 2026-06-12) — if the target formula ever gains a new dependency,
# that field MUST be added here or cached models will be silently wrong.
_TRAIN_SHAPE_KEYS = (
    "arch", "strategy", "freqaimodel", "config_file", "timeframe",
    "feature_set", "label_period_candles", "filter_di", "filter_svm",
    "prune_indicators", "perpair_oi", "trend_horizon", "target_version",
    "meta_label",  # Phase 3: adds &-meta_long/short targets → different trained model
    # Corrected meta-label geometry (2026-06-20): these define WHAT the meta target IS, so a
    # change here = a different trained meta model. Must be here or the corrected label would
    # collide with the old broken-label cache (fam_6aeb1b16f6_*). meta_threshold/meta_dump are
    # serve-time only and stay EXCLUDED.
    "meta_tp_mult", "meta_sl_mult", "meta_horizon", "meta_fee_pct",
    "num_leaves", "learning_rate", "min_child_samples", "reg_alpha",
    "reg_lambda", "n_estimators",
)


def _family_identifier(cfg: dict, window: str) -> str:
    """Deterministic FreqAI identifier per (training-shape, window).

    Same family + same window → same identifier → FreqAI finds the trained
    sub-models on disk and skips straight to backtesting. Param-only
    experiments (most of the queue) stop paying the ~80% training tax.
    purge_old_models=false in the brain config keeps the cache; cleanup is
    handled by brain_cleanup.py (fam_* retention).
    """
    blob = json.dumps({k: cfg.get(k) for k in _TRAIN_SHAPE_KEYS}, sort_keys=True)
    fam = hashlib.sha256(blob.encode()).hexdigest()[:10]
    return f"fam_{fam}_{window}"


def _run_hypothesis_group(
    h: dict,
    pairs_subset: list[str],
    group_suffix: str,
    timeout_s: int | None = None,
) -> list[dict]:
    """Run one docker backtest for a pair subset. Returns raw trade list or []."""
    cfg         = h["config"]
    config_file = cfg.get("config_file", "v23_regression_15m_di_config.json")
    timerange   = h["timerange"]
    # Family-cached identifier (2026-06-12): scout and full run share the same
    # family dir — the scout trains its 6 pairs, the full run reuses those and
    # trains only the remaining 20. The next same-family experiment trains 0.
    identifier  = _family_identifier(cfg, h.get("window") or timerange)
    effective_timeout = timeout_s if timeout_s is not None else BACKTEST_TIMEOUT_S

    # Extract any LightGBM hyperparams from hypothesis config to patch into the JSON
    # n_estimators is stamped into hypothesis config by SEED_CONFIG_V23 (2026-05-27)
    # so it's tracked per-experiment in experiment logs for future A/B comparisons.
    lgbm_keys = ("num_leaves", "learning_rate", "min_child_samples", "reg_alpha", "reg_lambda",
                 "n_estimators")
    lgbm_overrides = {k: cfg[k] for k in lgbm_keys if k in cfg}
    tmp_config = _create_pair_group_config(config_file, pairs_subset, group_suffix, lgbm_overrides)
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
                timeout=effective_timeout,
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
        # 2026-06-08: surface WHY it failed. Previously this returned [] silently, so all
        # 167 fast-failing experiments logged only "returned None" with no diagnosable cause.
        # Capture the tail of the backtest log (contains the real traceback / freqtrade error)
        # so brain_run.log shows the actual reason. Pure observability — no behaviour change.
        try:
            tail = log_file.read_text(errors="replace").splitlines()[-15:]
            reason = " | ".join(t.strip() for t in tail if t.strip())[-500:]
        except Exception:
            reason = "(could not read log)"
        print(
            f"[brain] group {group_suffix} FAILED (exit={proc.returncode}) "
            f"for {h['hypothesis_id']}: {reason}",
            file=sys.stderr,
        )
        return []

    # Refresh the family dir's mtime on every use (load-only reuse doesn't
    # write into it) so brain_cleanup's fam_* retention sees it as active.
    fam_dir = USER_DATA / "models" / identifier
    if fam_dir.is_dir():
        subprocess.run(["sudo", "touch", "-c", str(fam_dir)],
                       capture_output=True, timeout=10)

    after    = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    new_zips = sorted(after - before, key=lambda p: p.stat().st_mtime)
    if not new_zips:
        return []
    return _parse_raw_trades_from_zip(new_zips[-1])


# ── Scout: cheap 6-pair pre-filter ────────────────────────────────────────

# Regime-calibrated scout pool (2026-05-27):
# In BEAR regime: include high-beta pairs that trend sharply bearish (FET, RENDER,
# LDO) so the scout doesn't miss bear-friendly configs that score poorly on BTC/ETH
# alone. These pairs have high short-WR in bear markets.
# In BULL regime: swap in momentum pairs (SOL, TAO, WIF) that amplify bull moves.
# BTC + ETH are always in — they're the regime anchors.
SCOUT_PAIRS_BEAR = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
    "XRP/USDT:USDT", "FET/USDT:USDT", "LDO/USDT:USDT",
]
SCOUT_PAIRS_BULL = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
    "TAO/USDT:USDT", "WIF/USDT:USDT", "XRP/USDT:USDT",
]
SCOUT_PAIRS_NEUTRAL = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
    "BNB/USDT:USDT", "XRP/USDT:USDT", "LINK/USDT:USDT",
]
SCOUT_TIMEOUT_S = 1800  # 30 min — 6 pairs should finish in ~15 min; generous buffer

# Honest-brain scout quality gates (2026-06-17). A 6-pair, 3-month scout that can't
# produce a meaningful sample with a positive profit factor is noise, not a candidate.
# Full 26-pair runs need ~150 trades for significance (promote.py MIN_TOTAL_TRADES);
# 6/26 of that ≈ 35, so 40 is the floor for the scout's own sample.
SCOUT_MIN_TRADES = 40
SCOUT_MIN_PF = 1.0


def _get_scout_pairs() -> list[str]:
    """Return the scout pair pool calibrated to the current live regime."""
    try:
        regime_file = ROOT / "finbuddy_memory" / "regimes" / "current.json"
        regime = json.load(regime_file.open()).get("regime", "NEUTRAL").upper()
    except Exception:
        regime = "NEUTRAL"
    if regime == "BEAR":
        return SCOUT_PAIRS_BEAR
    if regime == "BULL":
        return SCOUT_PAIRS_BULL
    return SCOUT_PAIRS_NEUTRAL


def _run_scout(h: dict) -> tuple[bool, dict]:
    """Run a cheap 6-pair backtest on the hypothesis's full timerange.

    Uses the same config and env vars as the full run — only the pair list shrinks.
    Returns (passed, scout_metrics).

    Pass gate: profit_pct > 0 AND sharpe > 0 AND trades >= 5.
    Fail means the hypothesis is very unlikely to pass the full 26-pair run.

    Note: train_period_days=90 requires the full 3-month timerange — we can't shorten
    it here. Runtime is ~6/26 × full_time ≈ 15 min (vs 74 min full).
    """
    cfg         = h["config"]
    config_file = cfg.get("config_file", "v23_regression_15m_di_config.json")
    all_pairs   = _load_brain_pairs(config_file)

    scout_pairs = _get_scout_pairs()
    # Intersect scout pairs with the pairs available for this window
    filtered_scout = _filter_pairs_for_window(scout_pairs, h.get("window", ""))
    if not filtered_scout:
        # All scout pairs filtered out (odd window) — pass through to full run
        return True, {}

    # Make a shallow copy with a distinct hypothesis_id so the scout identifier
    # never collides with the full-run identifier for the same hypothesis.
    scout_h = {**h, "hypothesis_id": f"scout_{h['hypothesis_id']}_{int(time.time())}"}

    trades = _run_hypothesis_group(scout_h, filtered_scout, "scout", timeout_s=SCOUT_TIMEOUT_S)

    if not trades:
        # 0-trade bypass for lt >= 2.5 REMOVED 2026-06-11: that threshold scale is
        # extinct (valid LT is now 0.1-0.8 after the _GLOBAL_STD=0.30 fix). The
        # bypass only let stale old-scale configs skip scouting into full 26-pair
        # runs that produced statistically meaningless few-trade "winners".
        return False, {"trades": 0, "profit_pct": 0.0, "sharpe": 0.0}

    m = _compute_metrics_from_raw_trades(trades)
    # 2026-06-17 HONEST-BRAIN fix: the old gate (profit>0 AND sharpe>0 AND trades>=5)
    # crowned statistical noise. Forensics: per-trade expectancy is negative; the only
    # configs that showed "profit" were the ones that barely traded (the 89 "winners"
    # averaged 45 trades, PF~1.1 — indistinguishable from luck). A 5-trade scout pass is
    # meaningless. New gate requires a meaningful sample on the 6-pair scout AND real
    # quality (positive profit factor), so noise no longer floods the full 26-pair runs.
    passed = (
        m.get("profit_pct", -1) > 0
        and m.get("sharpe", -1) > 0
        and m.get("pf", 0) > SCOUT_MIN_PF
        and m.get("trades", 0) >= SCOUT_MIN_TRADES
    )
    return passed, m


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

            # Strict bear/bull alternation: always pick the opposite window type of
            # the last completed experiment. This is the root-level fix for queue drift —
            # no matter how generate_and_queue() or queue_missing_windows() appends entries,
            # the runner enforces interleaving. Replaces the one-shot prioritize_regime_windows()
            # sort which only worked until the next batch was appended (2026-06-01 fix).
            queue = [e for e in queue if e.get("status") == "queued"]
            if not queue:
                print("[brain] queue empty — nothing to run")
                break
            last_type = last_completed_window_type()
            h = next_alternating(last_type)
            if h is None:
                print("[brain] queue empty — nothing to run")
                break
            if last_type:
                want_type = "bear" if last_type == "bull" else "bull"
                actual_type = "bear" if "bear" in h.get("window", "").lower() else "bull"
                if actual_type != want_type:
                    print(f"[brain] alternation: no {want_type} entries queued, falling back to {actual_type}")
            started = datetime.now(timezone.utc).isoformat()

            print(f"[brain] running {h['hypothesis_id']} ({h['band']}) on {h['window']}: {h['rationale']}")

            # Two-tier scout: cheap 6-pair pre-filter before the full 26-pair run.
            # Every 10th experiment bypasses the scout (sanity check we're not
            # over-filtering configs that only work on rare pairs).
            today_n = experiments_today_count()
            run_scout = today_n % 10 != 0  # bypass on the 10th, 20th, etc.
            # Benchmarks (e.g. BaselineEMACross) must always produce a FULL
            # 26-pair result — a losing benchmark is still the answer we want.
            if h.get("config", {}).get("skip_scout"):
                run_scout = False
            if run_scout:
                scout_pass, scout_m = _run_scout(h)
                if not scout_pass:
                    mark_scout_failed(h, scout_m)
                    print(
                        f"[brain] SCOUT_FAILED {h['hypothesis_id']} "
                        f"(profit={scout_m.get('profit_pct', 0):+.2f}% "
                        f"sharpe={scout_m.get('sharpe', 0):+.2f} "
                        f"trades={scout_m.get('trades', 0)})"
                    )
                    continue
                print(f"[brain] scout PASSED {h['hypothesis_id'][:8]} — proceeding to full run")

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

            # Cross-window validation: if this window passed (profit>0, sharpe>0),
            # 1. Move existing queued windows for this config to the queue front.
            # 2. Auto-add any windows not yet queued or tested — so a promising config
            #    gets tested on ALL 5 windows without waiting for random re-discovery.
            if metrics.get("profit_pct", -1) > 0 and metrics.get("sharpe", -1) > 0:
                from hypothesis_gen import WINDOWS, PAIRED_WINDOWS
                # Use PAIRED_WINDOWS order so cross-window queuing preserves
                # the bull→bear interleaving: bull_2024Q1 queued before bear_2025Q1, etc.
                paired_windows_dict = {w: WINDOWS[w] for w in PAIRED_WINDOWS if w in WINDOWS}
                # Attach metrics to h so queue_missing_windows can log them in rationale
                h_with_metrics = {**h, "metrics": metrics}
                promoted = prioritize_same_config(h)
                if promoted:
                    print(f"[brain] PRIORITY: moved {promoted} queued windows for {h['hypothesis_id'][:8]} to front")
                added = queue_missing_windows(h_with_metrics, paired_windows_dict)
                if added:
                    print(f"[brain] CROSS-WINDOW: queued {added} new windows for {h['hypothesis_id'][:8]} (not yet tested)")

            # NOTE: prioritize_regime_windows() intentionally NOT called here.
            # It moves ALL bear (or bull) entries to the front which destroys
            # the paired bull+bear ordering that enables fast promotion.
            # Queue order is maintained by PAIRED_WINDOWS in generate_and_queue()
            # and the initial reorder at queue-build time. Manual regime seeding
            # via `brain_cli.py seed-regime` can still be used for explicit
            # regime-targeting sessions.

            # Telegram via unified template ? silent for per-experiment results
            # (avoid spamming the user; only promotion candidates make a sound)
            arch = h.get("config", {}).get("arch", "?")
            status = Status.OK if metrics.get("profit_pct", -1) > 0 else Status.INFO
            elapsed_s = metrics.get("elapsed_s", 0)
            tg_send(
                subsystem=Subsystem.BRAIN_EXPERIMENT,
                status=status,
                title=f"#{h['hypothesis_id']} | {arch} | {h['band']}",
                fields={
                    "Window":   h["window"],
                    "Profit":   f"{metrics['profit_pct']:+.2f}%",
                    "Win Rate": f"{metrics['wr']*100:.1f}%",
                    "Sharpe":   f"{metrics['sharpe']:+.2f}",
                    "PF":       f"{metrics['pf']:.2f}",
                    "Trades":   f"{metrics['trades']} ({metrics['long_count']}L / {metrics['short_count']}S)",
                    "Duration": f"{elapsed_s//60}m {elapsed_s%60}s",
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
    p = argparse.ArgumentParser(description="Cortexa Brain — autonomous experiment runner")
    p.add_argument("--max",    type=int, default=1, help="max experiments to run this invocation")
    p.add_argument("--status", action="store_true", help="print status, do not run")
    args = p.parse_args()
    sys.exit(0 if run_next(max_runs=args.max, status_only=args.status) >= 0 else 1)
