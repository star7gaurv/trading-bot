#!/usr/bin/env python3
"""
auto_promote.py — FinBuddy Self-Evolution: Walk-Forward Promotion Engine
=========================================================================
Compares the most recently completed walk-forward run against the current
live model's recorded Sharpe. If the new run is meaningfully better, sends
a Telegram notification with the proposed config change.

SAFETY: This script is NOTIFY-ONLY. It never modifies config.json or
restarts the bot automatically. Gaurav reviews the Telegram alert and
manually applies the promoted config. Fully autonomous promotion is a
future Phase 2 unlock.

Designed to run 5 minutes after the monthly walk-forward cron (03:00 UTC):
  Cron:  5 3 1 * *  python /path/to/auto_promote.py

State file: ~/.finbuddy/state/promotion_state.json
  - records the Sharpe of the currently deployed config
  - records the last run we already evaluated (idempotent)
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT      = Path("/home/ubuntu/var/www/html/trade")
WF_RESULTS_DIR = REPO_ROOT / "walkforward_results"
CONFIG_PATH    = REPO_ROOT / "freqtrade" / "user_data" / "config.json"
STATE_FILE     = Path("/home/ubuntu/.finbuddy/state/promotion_state.json")
TELEGRAM_TOKEN = "REDACTED-FREQTRADE__TELEGRAM__TOKEN"
TELEGRAM_CHAT  = "5622292536"

# Minimum Sharpe improvement to trigger a promotion notification
PROMOTION_DELTA = 0.10


def _tg(msg: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception as e:
        print(f"WARN: Telegram failed: {e}", file=sys.stderr)


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
    """Return (run_name, summary_dict) for the most recently completed WF run."""
    summaries = list(WF_RESULTS_DIR.glob("*/summary.json"))
    if not summaries:
        return None, None
    latest = max(summaries, key=lambda p: p.stat().st_mtime)
    try:
        summary = json.loads(latest.read_text())
        return latest.parent.name, summary
    except Exception as e:
        print(f"WARN: Could not read {latest}: {e}", file=sys.stderr)
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

    new_sharpe  = summary.get("weighted_sharpe", summary.get("sharpe", None))
    new_wr      = summary.get("weighted_win_rate", summary.get("win_rate", None))
    new_pf      = summary.get("weighted_profit_factor", summary.get("profit_factor", None))
    new_dd      = summary.get("worst_drawdown", summary.get("max_drawdown", None))
    new_verdict = summary.get("pass", False)

    current_sharpe    = state.get("current_sharpe")
    live_identifier   = get_live_identifier()

    print(f"Run: {run_name}")
    print(f"  New Sharpe:  {new_sharpe}  WR: {new_wr}  PF: {new_pf}  DD: {new_dd}")
    print(f"  Pass: {new_verdict}")
    print(f"  Live ID:     {live_identifier}")
    print(f"  Live Sharpe: {current_sharpe}")

    state["last_evaluated_run"] = run_name

    if not new_verdict:
        _tg(
            f"📊 <b>Walk-Forward Result</b> (monthly)\n"
            f"Run: <code>{run_name}</code>\n\n"
            f"❌ FAIL — no promotion\n"
            f"  Sharpe: {new_sharpe}  WR: {new_wr}%  PF: {new_pf}  DD: {new_dd}%\n\n"
            f"Current: <code>{live_identifier}</code> (Sharpe {current_sharpe})\n"
            f"No action taken — keeping current config."
        )
        save_state(state)
        return 0

    if current_sharpe is not None and new_sharpe is not None:
        improvement = float(new_sharpe) - float(current_sharpe)
        if improvement < PROMOTION_DELTA:
            _tg(
                f"📊 <b>Walk-Forward Result</b> (monthly)\n"
                f"Run: <code>{run_name}</code>\n\n"
                f"✅ PASS but improvement too small (+{improvement:.3f} < {PROMOTION_DELTA} threshold)\n"
                f"  New Sharpe: {new_sharpe}  WR: {new_wr}%  PF: {new_pf}  DD: {new_dd}%\n"
                f"  Current: {current_sharpe}\n\n"
                f"No promotion — keeping current config."
            )
            save_state(state)
            return 0

    # New run passes AND is meaningfully better — send promotion notification
    _tg(
        f"🚀 <b>FinBuddy Promotion Candidate!</b>\n\n"
        f"Walk-Forward: <code>{run_name}</code>\n"
        f"  ✅ Sharpe: {new_sharpe}  WR: {new_wr}%  PF: {new_pf}  DD: {new_dd}%\n\n"
        f"Current: <code>{live_identifier}</code> (Sharpe {current_sharpe})\n"
        f"Improvement: +{(float(new_sharpe or 0) - float(current_sharpe or 0)):.3f}\n\n"
        f"<b>ACTION REQUIRED:</b>\n"
        f"1. Review the walk-forward folds in <code>walkforward_results/{run_name}/</code>\n"
        f"2. If satisfied, update <code>config.json</code> identifier and restart bot\n"
        f"3. Run <code>python scripts/auto_promote.py --confirm</code> to record new Sharpe\n\n"
        f"This is notify-only — no automatic config change was made."
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
    _tg(
        f"✅ <b>Promotion Recorded</b>\n"
        f"New baseline Sharpe: {new_sharpe} (was {old})\n"
        f"Live config: <code>{live_id}</code>"
    )
    print(f"Promotion recorded: Sharpe {old} → {new_sharpe}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        sharpe = float(sys.argv[2]) if len(sys.argv) > 2 else float(input("Enter new Sharpe: "))
        record_promotion(sharpe)
    else:
        sys.exit(main())
