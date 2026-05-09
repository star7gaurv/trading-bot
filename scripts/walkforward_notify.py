#!/usr/bin/env python3
"""
FinBuddy Walk-Forward Notifier

Watches `walkforward_results/` for completed runs and fires a Telegram
message with PASS/FAIL verdict + key metrics. Runs every 30m via cron.

A run is "complete" when its directory contains a `summary.json` file
(written only at the very end of walk_forward.py main()).

Idempotent — tracks notified run IDs in a state file. Safe to re-run.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/home/ubuntu/var/www/html/trade")
RESULTS_BASE = REPO / "walkforward_results"
CONFIG_PATH = REPO / "freqtrade/user_data/config.json"
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


def telegram_send(msg: str) -> bool:
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        tg = cfg.get("telegram") or {}
        token, chat_id = tg.get("token"), tg.get("chat_id")
        if not (token and chat_id):
            print("WARN: telegram creds missing", file=sys.stderr)
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"ERR: telegram send failed: {e}", file=sys.stderr)
        return False


def format_message(run_id: str, summary: dict) -> str:
    agg = summary.get("aggregate", {})
    passed = summary.get("pass", False)
    verdict_lines = summary.get("verdict", [])
    icon = "✅ *PASS*" if passed else "❌ *FAIL*"
    next_step = (
        "🚀 Walk-forward GATE PASSED — Phase 10 (live migration) is now unblocked."
        if passed else
        "Strategy still in dry-run. Iterate on the failing metrics before next attempt."
    )
    return (
        f"🧪 *Walk-Forward Complete* {icon}\n\n"
        f"`{run_id}`\n\n"
        f"*Folds*: {agg.get('folds', '?')}\n"
        f"*Total trades*: {agg.get('total_trades', '?')}\n"
        f"*Total profit*: {agg.get('total_profit_abs', 0):.2f} USDT\n\n"
        f"*Verdict*\n" + "\n".join(verdict_lines) + "\n\n"
        f"_{next_step}_"
    )


def main() -> int:
    if not RESULTS_BASE.exists():
        print("OK: no walkforward_results dir yet")
        return 0

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

        msg = format_message(run_id, summary)
        if telegram_send(msg):
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


if __name__ == "__main__":
    sys.exit(main())
