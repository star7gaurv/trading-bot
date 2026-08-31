#!/usr/bin/env python3
"""
Cortexa Walk-Forward Notifier

Watches `walkforward_results/` for completed runs and fires a Telegram
message with PASS/FAIL verdict + key metrics. Runs every 30m via cron.

A run is "complete" when its directory contains a `summary.json` file
(written only at the very end of walk_forward.py main()).

Idempotent — tracks notified run IDs in a state file. Safe to re-run.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/home/ubuntu/var/www/html/trade")
RESULTS_BASE = REPO / "walkforward_results"
STATE_FILE = Path("/home/ubuntu/.finbuddy/state/walkforward_notify.json")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"notified": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"notified": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def send_wf_message(run_id: str, summary: dict) -> bool:
    """Send WF result via the unified template module."""
    sys.path.insert(0, str(REPO / "scripts" / "lib"))
    from telegram_template import send as _tg_send, Subsystem, Status

    agg    = summary.get("aggregate", {}) or {}
    passed = summary.get("pass", False)
    # Verdicts from walk_forward.py (e.g. "❌ no trades across all folds")
    verdict_lines = summary.get("verdict", [])
    verdict_str   = " · ".join(verdict_lines) if verdict_lines else ""

    # Shorten the run_id for display: strip the strategy prefix, keep date+timestamp.
    # e.g. "FinBuddyFreqAI_v23_2025-08-01_2026-05-01_20260522T220002"
    #   → "2025-08-01 → 2026-05-01 (20260522T220002)"
    try:
        parts = run_id.split("_")
        # find first date part (YYYY-MM-DD format)
        date_parts = [p for p in parts if len(p) == 10 and p[4] == "-"]
        ts_parts   = [p for p in parts if len(p) == 15 and "T" in p]
        if len(date_parts) >= 2:
            display_id = f"{date_parts[0]} → {date_parts[1]}"
            if ts_parts:
                display_id += f" ({ts_parts[0]})"
        else:
            display_id = run_id
    except Exception:
        display_id = run_id

    no_data = not agg  # aggregate is empty — all folds timed out / no trades

    if no_data:
        # Bug 5 fix (2026-05-30): show the ACTUAL effective LT so the reason is
        # immediately actionable instead of the stale canned message.
        try:
            import os as _os
            from pathlib import Path as _Path
            _env_path = _Path("/home/ubuntu/var/www/html/trade/freqtrade/.env")
            _lt = 1.5
            for _line in _env_path.read_text().splitlines():
                if _line.startswith("FREQAI_LONG_THRESHOLD="):
                    _lt = float(_line.split("=", 1)[1].strip())
            # WF forces RECENT_WR=0.55 (neutral) so wr_adj=1.0
            _eff_lt = _lt * 1.0
            # Read current regime for context
            try:
                import json as _json
                _regime_file = _Path("/home/ubuntu/var/www/html/trade/finbuddy_memory/regimes/current.json")
                _regime = _json.loads(_regime_file.read_text()).get("regime", "UNKNOWN")
            except Exception:
                _regime = "UNKNOWN"
            _bear_hint = (
                " BEAR regime active: regime multiplier pushes effective threshold higher "
                "— even LT=1.5 can become ~2.0σ in BEAR+bad_WR. Deep WF (7 folds) "
                "covers Q4-2025 bull period and WILL show trade activity there."
                if "BEAR" in _regime else ""
            )
            _no_trade_reason = (
                f"No trades in any fold — LT={_lt:.2f}, regime={_regime}, "
                f"eff_LT≈{_eff_lt:.2f}σ (WR neutral in WF)."
                f"{'⚠️ LT high for current market.' if _eff_lt > 2.0 else '✅ LT OK — signal drought.'}"
                f"{_bear_hint}"
            )
            _ctx = (
                f"Daily WF test window (Apr+May 2026) is BEAR market — low signal density expected. "
                f"Check deep WF folds for Q4-2025 bull performance. "
                f"Effective threshold in WF: {_eff_lt:.2f}σ."
            )
        except Exception:
            _no_trade_reason = verdict_str or "all folds produced no trades"
            _ctx = "All folds produced no trades — check FREQAI_LONG_THRESHOLD in .env"
        fields = {
            "Verdict":  "FAIL — keep iterating",
            "Run":      display_id,
            "Reason":   _no_trade_reason,
            "Folds":    "0 with data",
        }
        ctx = _ctx
    else:
        n_folds  = agg.get("folds", "?")
        n_trades = agg.get("total_trades", "?")
        profit   = agg.get("total_profit_abs", 0)
        wr_raw   = agg.get("weighted_win_rate")
        sharpe   = agg.get("weighted_sharpe", "?")
        pf       = agg.get("weighted_profit_factor", "?")
        worst_dd = agg.get("worst_drawdown", 0) or 0
        fields = {
            "Verdict":      "PASS ✅ — Phase 10 unblocked" if passed else "FAIL — keep iterating",
            "Run":          display_id,
            "Folds":        f"{n_folds}",
            "Total Trades": f"{n_trades}",
            "Total Profit": f"{profit:+.2f} USDT",
            "Win Rate":     f"{wr_raw*100:.1f}%" if isinstance(wr_raw, (int, float)) else "—",
            "Sharpe":       f"{sharpe}",
            "PF":           f"{pf}",
            "Worst DD":     f"{worst_dd*100:.1f}%",
        }
        ctx = "Out-of-sample validator · gates live deployment"
        if verdict_str:
            ctx += f"\n{verdict_str}"

    return _tg_send(
        subsystem=Subsystem.WALK_FORWARD,
        status=Status.OK if passed else Status.FAIL,
        title=f"{'daily' if 'T220' in run_id or 'T21' in run_id else 'deep'} walk-forward result",
        fields=fields,
        context=ctx,
        action=("Review walkforward_results/ and discuss deployment" if passed else None),
    )


def main() -> int:
    if not RESULTS_BASE.exists():
        print("OK: no walkforward_results dir yet")
        return 0

    # Fix 15 (2026-05-22): use flock to prevent race condition when two cron instances
    # start simultaneously (every 30m). Without locking, both read the same notified set
    # and each sends duplicate Telegram for the same WF run.
    import fcntl
    LOCK_FILE = Path("/tmp/finbuddy_walkforward_notify.lock")
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("OK: another instance is running, skipping")
        lock_fd.close()
        return 0

    try:
        state = load_state()
        notified: set[str] = set(state.get("notified", []))

        new = 0
        for run_dir in sorted(RESULTS_BASE.iterdir()):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            if run_id in notified:
                continue
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                continue  # run still in progress

            try:
                summary = json.loads(summary_path.read_text())
            except Exception as e:
                print(f"ERR: parsing {summary_path}: {e}", file=sys.stderr)
                continue

            if send_wf_message(run_id, summary):
                print(f"NOTIFIED: {run_id} (pass={summary.get('pass')})")
                notified.add(run_id)
                new += 1
            else:
                print(f"WARN: telegram failed for {run_id} — will retry next run")

        state["notified"] = sorted(notified)
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        print(f"OK: {new} new notifications sent")
        return 0
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    sys.exit(main())
