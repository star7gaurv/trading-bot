#!/usr/bin/env python3
"""
auto_promote.py — Cortexa Self-Evolution: Walk-Forward Promotion Engine
=========================================================================
Compares the most recently completed walk-forward run against the current
live model's recorded Sharpe. If the new run is meaningfully better, sends
a Telegram notification with the proposed config change.

SAFETY: This script is NOTIFY-ONLY. It never modifies config.json or
restarts the bot automatically. Gaurav reviews the Telegram alert and
manually applies the promoted config. Fully autonomous promotion is a
future Phase 2 unlock.

Designed to run daily after the walk-forward results window (04:00 UTC):
  Cron:  0 4 * * *  python /path/to/auto_promote.py

State file: ~/.finbuddy/state/promotion_state.json
  - records the Sharpe of the currently deployed config
  - records the last run we already evaluated (idempotent)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT      = Path("/home/ubuntu/var/www/html/trade")
WF_RESULTS_DIR = REPO_ROOT / "walkforward_results"
CONFIG_PATH    = REPO_ROOT / "freqtrade" / "user_data" / "config.json"
STATE_FILE     = Path("/home/ubuntu/.finbuddy/state/promotion_state.json")

# Minimum Sharpe improvement to trigger a promotion notification
PROMOTION_DELTA = 0.10


# Use the unified telegram template (scripts/lib/telegram_template.py)
sys.path.insert(0, str(Path(__file__).parent / "lib"))
from telegram_template import send as _tg_send, Subsystem, Status


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"current_sharpe": None, "last_evaluated_run": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"current_sharpe": None, "last_evaluated_run": None}


def save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def find_latest_wf_run() -> tuple[str, dict] | tuple[None, None]:
    """Return (run_name, summary_dict) for the most recently completed WF run.

    Skips summaries with total_trades == 0 (failed/incomplete WF runs that wrote
    an empty aggregate). Those runs are touched to disk after completion but carry
    no useful metrics — picking them would render Sharpe/WR/PF as None every day.
    Uses file mtime as the sort key; most-recent non-empty run wins.
    """
    summaries = list(WF_RESULTS_DIR.glob("*/summary.json"))
    if not summaries:
        return None, None
    summaries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # Count how many consecutive 0-trade summaries we skip (Bug 10 fix, 2026-05-30)
    skipped_empty = 0
    for path in summaries:
        try:
            summary = json.loads(path.read_text())
            total = summary.get("aggregate", {}).get("total_trades", 0) or 0
            if total == 0:
                print(f"SKIP empty summary (0 trades): {path.parent.name}", file=sys.stderr)
                skipped_empty += 1
                continue
            # Bug 10 fix: if we skipped ≥3 empty summaries before finding a valid one,
            # the valid one is stale (≥3 days of WF failures). Alert once, then return
            # None so this run becomes a no-op rather than silently using stale data.
            if skipped_empty >= 3:
                run_time = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                age_days = (datetime.now(timezone.utc) - run_time).total_seconds() / 86400
                print(f"WARN: {skipped_empty} consecutive 0-trade WF runs — "
                      f"most recent valid run is {age_days:.1f}d old ({path.parent.name})",
                      file=sys.stderr)
                try:
                    _tg_send(
                        subsystem=Subsystem.WALK_FORWARD,
                        status=Status.WARN,
                        title=f"Walk-forward has produced NO valid results for {skipped_empty} consecutive runs",
                        fields={
                            "Last valid run": f"{path.parent.name} ({age_days:.0f}d ago)",
                            "Action": "Check FREQAI_LONG_THRESHOLD — may be too high for current market",
                        },
                        context=f"All recent WF folds returned 0 trades. "
                                f"LT may still be above model prediction range.",
                    )
                except Exception:
                    pass
                return None, None
            return path.parent.name, summary
        except Exception as e:
            print(f"WARN: Could not read {path}: {e}", file=sys.stderr)
    return None, None


def get_live_identifier() -> str:
    """Read the current FreqAI identifier from config.json."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        return cfg.get("freqai", {}).get("identifier", "unknown")
    except Exception:
        return "unknown"


def main() -> int:
    state    = load_state()
    run_name, summary = find_latest_wf_run()

    if run_name is None:
        print("No walk-forward runs found — nothing to evaluate")
        return 0

    if run_name == state.get("last_evaluated_run"):
        print(f"Already evaluated run '{run_name}' — skipping (idempotent)")
        return 0

    # 2026-05-20: metrics actually live under summary["aggregate"], not at root.
    # Before this fix the Telegram message rendered "Sharpe: None / WR: None%" on
    # every failing run because every .get() missed and returned literal None.
    agg = summary.get("aggregate", {}) or {}
    new_sharpe  = agg.get("weighted_sharpe", agg.get("sharpe"))
    new_wr      = agg.get("weighted_win_rate", agg.get("win_rate"))
    new_pf      = agg.get("weighted_profit_factor", agg.get("profit_factor"))
    new_dd      = agg.get("worst_drawdown", agg.get("max_drawdown"))
    new_verdict = summary.get("pass", False)

    current_sharpe    = state.get("current_sharpe")
    live_identifier   = get_live_identifier()

    print(f"Run: {run_name}")
    print(f"  New Sharpe:  {new_sharpe}  WR: {new_wr}  PF: {new_pf}  DD: {new_dd}")
    print(f"  Pass: {new_verdict}")
    print(f"  Live ID:     {live_identifier}")
    print(f"  Live Sharpe: {current_sharpe}")

    state["last_evaluated_run"] = run_name

    # Format helpers — keep "—" placeholder instead of literal "None" when a
    # field is missing (typical for 0-trade WF runs where aggregate is empty).
    def _fmt(v, suffix="", fmt=""):
        if v is None:
            return "—"
        try:
            return (f"{float(v):{fmt}}" if fmt else f"{v}") + suffix
        except (TypeError, ValueError):
            return f"{v}{suffix}"

    metrics_fields = {
        "Run":      f"<code>{run_name}</code>",
        "Sharpe":   _fmt(new_sharpe, fmt=".3f"),
        "Win Rate": _fmt((new_wr * 100) if isinstance(new_wr, (int, float)) else new_wr, suffix="%", fmt=".1f"),
        "PF":       _fmt(new_pf, fmt=".3f"),
        "Drawdown": _fmt((new_dd * 100) if isinstance(new_dd, (int, float)) and abs(new_dd) < 1 else new_dd, suffix="%", fmt=".2f"),
        "Trades":   _fmt(agg.get("total_trades")),
        "Baseline": f"Sharpe {_fmt(current_sharpe, fmt='.3f')} · id={live_identifier}",
    }

    if not new_verdict:
        _tg_send(
            subsystem=Subsystem.WALK_FORWARD,
            status=Status.FAIL,
            title=f"daily walk-forward run failed — no promotion",
            fields=metrics_fields,
            context="Keeping current config — iterate on failing metrics first.",
        )
        save_state(state)
        return 0

    if current_sharpe is not None and new_sharpe is not None:
        improvement = float(new_sharpe) - float(current_sharpe)
        if improvement < PROMOTION_DELTA:
            _tg_send(
                subsystem=Subsystem.WALK_FORWARD,
                status=Status.WARN,
                title=f"passed but improvement too small (+{improvement:.3f} < {PROMOTION_DELTA})",
                fields=metrics_fields,
                context="Keeping current config — improvement below promotion threshold.",
            )
            save_state(state)
            return 0

    # New run passes AND is meaningfully better — send promotion notification
    improvement = float(new_sharpe or 0) - float(current_sharpe or 0)
    _tg_send(
        subsystem=Subsystem.BRAIN_PROMOTION,
        status=Status.ACTION,
        title=f"daily walk-forward winner found",
        fields={
            "Run":         f"<code>{run_name}</code>",
            "New Sharpe":  f"{new_sharpe} (+{improvement:.3f} vs baseline)",
            "Win Rate":    f"{new_wr}%",
            "PF":          f"{new_pf}",
            "Drawdown":    f"{new_dd}%",
            "Live ID":     f"<code>{live_identifier}</code>",
        },
        context="Daily auto-promote · notify-only (no auto config change)",
        action=(
            f"1. Review: <code>walkforward_results/{run_name}/</code> · "
            f"2. Update config.json + restart · "
            f"3. <code>python scripts/auto_promote.py --confirm {new_sharpe}</code>"
        ),
    )

    print(f"PROMOTION CANDIDATE: {run_name} (Sharpe {new_sharpe} vs current {current_sharpe})")
    save_state(state)
    return 0


def record_promotion(new_sharpe: float) -> None:
    """Call this after manually applying a promoted config to update baseline Sharpe."""
    state = load_state()
    old   = state.get("current_sharpe")
    state["current_sharpe"] = new_sharpe
    state["promotion_applied_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    live_id = get_live_identifier()
    _tg_send(
        subsystem=Subsystem.BRAIN_PROMOTION,
        status=Status.OK,
        title="promotion recorded — baseline updated",
        fields={
            "New Baseline Sharpe": f"{new_sharpe}",
            "Previous Sharpe":     f"{old}",
            "Live Config":         f"<code>{live_id}</code>",
        },
        context="Brain will now compare future candidates against this baseline.",
    )
    print(f"Promotion recorded: Sharpe {old} → {new_sharpe}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        sharpe = float(sys.argv[2]) if len(sys.argv) > 2 else float(input("Enter new Sharpe: "))
        record_promotion(sharpe)
    else:
        sys.exit(main())
