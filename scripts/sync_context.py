#!/usr/bin/env python3
"""
FinBuddy Context Auto-Sync

Runs every 4h (alongside HMM cron) and keeps FINBUDDY_PROJECT_MEMORY.md
permanently in sync with the live system state. Also appends a one-liner to
finbuddy_memory/session_events.md whenever a meaningful state change is
detected — giving Claude a machine-maintained event log to pull from when
writing session history.

What it auto-reads:
  - Strategy version (from FinBuddyFreqAI.py comments)
  - FreqAI identifier + pair count (from config.json)
  - Current regime (from regimes/current.json)
  - Walk-forward status (from walkforward_results/ dir)
  - FreqTrade API: open trades, trade count, last heartbeat age
  - Live crontab

What it writes:
  - Replaces the <!-- AUTO-SYNC-START --> ... <!-- AUTO-SYNC-END --> block in
    FINBUDDY_PROJECT_MEMORY.md with a freshly generated live-state table.
  - Appends to finbuddy_memory/session_events.md on state change.
  - Git commits the changes (gaurav branch).

Usage:
  python3 scripts/sync_context.py [--dry-run]

Cron (add alongside HMM cron):
  0 */4 * * * python3 /home/ubuntu/var/www/html/trade/scripts/sync_context.py >> /home/ubuntu/.finbuddy/logs/sync_context.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------- paths ----------
REPO = Path("/home/ubuntu/var/www/html/trade")
STRATEGY_FILE = REPO / "freqtrade/user_data/strategies/FinBuddyFreqAI.py"
CONFIG_FILE = REPO / "freqtrade/user_data/config.json"
REGIME_JSON = REPO / "finbuddy_memory/regimes/current.json"
MEMORY_FILE = REPO / "finbuddy_memory" / "FINBUDDY_PROJECT_MEMORY.md"
EVENTS_FILE = REPO / "finbuddy_memory/session_events.md"
WF_RESULTS_DIR = REPO / "walkforward_results"
LOG_FILE = REPO / "freqtrade/user_data/logs/freqtrade.log"
STATE_FILE = Path("/home/ubuntu/.finbuddy/state/sync_context_prev.json")

FREQTRADE_API = "http://localhost:8080/api/v1"
FREQTRADE_AUTH = ("bot", "REDACTED-FREQTRADE__API_SERVER__PASSWORD")

SYNC_START = "<!-- AUTO-SYNC-START -->"
SYNC_END = "<!-- AUTO-SYNC-END -->"

REGIME_EMOJI = {
    "CRASH": "💀", "BEAR": "🐻", "NEUTRAL": "⚖️",
    "BULL": "🐂", "EUPHORIA": "🚀",
}


# ---------- readers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def read_strategy_version() -> str:
    """Extract the highest vNN.N version mentioned in strategy comments."""
    if not STRATEGY_FILE.exists():
        return "unknown"
    text = STRATEGY_FILE.read_text(errors="replace")
    versions = re.findall(r"v(\d+\.\d+)", text)
    if not versions:
        return "unknown"
    # sort by major.minor numerically
    def ver_key(v):
        parts = v.split(".")
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    return "v" + max(versions, key=ver_key)


def read_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def read_regime() -> tuple[str, str]:
    """Returns (regime_name, emoji)."""
    if not REGIME_JSON.exists():
        return "UNKNOWN", "❓"
    try:
        data = json.loads(REGIME_JSON.read_text())
        regime = data.get("regime", "UNKNOWN").upper()
        return regime, REGIME_EMOJI.get(regime, "❓")
    except Exception:
        return "UNKNOWN", "❓"


def read_walkforward_status() -> str:
    """Returns human-readable walk-forward status."""
    if not WF_RESULTS_DIR.exists():
        return "⬜ Not started"
    runs = sorted(WF_RESULTS_DIR.glob("FinBuddyFreqAI_*"))
    if not runs:
        return "⬜ No results yet"
    latest = runs[-1]
    # check for summary file
    summary = latest / "summary.json"
    if summary.exists():
        try:
            data = json.loads(summary.read_text())
            passed = data.get("pass", False)
            agg = data.get("aggregate", {})
            icon = "✅ PASS" if passed else "❌ FAIL"
            wr = agg.get("weighted_win_rate", 0)
            sharpe = agg.get("weighted_sharpe", 0)
            dd = agg.get("worst_drawdown", 0)
            pf = agg.get("weighted_profit_factor", 0)
            n_trades = agg.get("total_trades", 0)
            return (
                f"{icon} — WR {wr:.1%}, Sharpe {sharpe:.2f}, DD {dd:.1%}, "
                f"PF {pf:.2f} ({n_trades} trades, run `{latest.name}`)"
            )
        except Exception:
            pass
    # running: count fold result files
    fold_files = list(latest.glob("fold_*.json"))
    if fold_files:
        return f"⏳ Running — {len(fold_files)}/21 folds done ({latest.name})"
    return f"⏳ Running — 0/21 folds ({latest.name})"


def call_api(endpoint: str, timeout: int = 5):
    """Call FreqTrade REST API. Returns parsed JSON or None."""
    try:
        import base64
        token = base64.b64encode(
            f"{FREQTRADE_AUTH[0]}:{FREQTRADE_AUTH[1]}".encode()
        ).decode()
        req = urllib.request.Request(
            f"{FREQTRADE_API}/{endpoint}",
            headers={"Authorization": f"Basic {token}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"WARN: API call {endpoint} failed: {e}", file=sys.stderr)
        return None


def read_trade_stats() -> dict:
    """Returns open_count, long_count, short_count, total_closed, all_time_profit."""
    result = {
        "open": 0, "longs": 0, "shorts": 0,
        "closed": 0, "all_time_profit": 0.0,
    }
    status = call_api("status")
    if status:
        result["open"] = len(status)
        result["longs"] = sum(1 for t in status if t.get("is_open") and not t.get("is_short"))
        result["shorts"] = sum(1 for t in status if t.get("is_open") and t.get("is_short"))
    profit = call_api("profit")
    if profit:
        result["closed"] = profit.get("trade_count", 0)
        result["all_time_profit"] = profit.get("profit_all_coin", 0.0)
    return result


def read_last_training_age_min() -> int | None:
    """Scan freqtrade.log for newest 'Done training' line. Returns age in minutes or None."""
    if not LOG_FILE.exists():
        return None
    try:
        # read last 50k chars for efficiency
        text = LOG_FILE.read_text(errors="replace")[-50000:]
        matches = list(re.finditer(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Done training",
            text, re.MULTILINE
        ))
        if not matches:
            return None
        last_ts_str = matches[-1].group(1)
        last_ts = datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
        age = now_utc() - last_ts
        return int(age.total_seconds() / 60)
    except Exception:
        return None


# ---------- state diff & event log ----------
def load_prev_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def append_event(msg: str) -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    line = f"- **{ts}** — {msg}\n"
    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("# FinBuddy Session Events (auto-generated)\n\n*← [[FINBUDDY_PROJECT_MEMORY]]*\n\n")
    with EVENTS_FILE.open("a") as f:
        f.write(line)
    print(f"EVENT: {msg}")


def detect_and_log_changes(curr: dict, prev: dict) -> None:
    """Compare current vs previous state; append events for meaningful changes."""
    checks = [
        ("strategy_version", "Strategy version changed: {prev} → {curr}"),
        ("freqai_identifier", "FreqAI identifier changed: {prev} → {curr}"),
        ("pair_count", "Pair whitelist changed: {prev} → {curr} pairs"),
        ("regime", "Regime changed: {prev} → {curr}"),
        ("wf_status", "Walk-forward status: {curr}"),
    ]
    for key, tmpl in checks:
        c, p = curr.get(key), prev.get(key)
        if c and c != p:
            append_event(tmpl.format(curr=c, prev=p or "N/A"))

    # trade milestones
    curr_closed = curr.get("closed_trades", 0)
    prev_closed = prev.get("closed_trades", 0)
    for milestone in [10, 25, 50, 100, 200, 500]:
        if prev_closed < milestone <= curr_closed:
            append_event(f"🎯 Trade milestone reached: {milestone} closed trades")


# ---------- markdown writer ----------
def build_sync_block(
    strategy_ver: str,
    identifier: str,
    pair_count: int,
    dry_run: bool,
    regime: str,
    regime_emoji: str,
    wf_status: str,
    trades: dict,
    training_age_min: int | None,
) -> str:
    ts = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    training_str = (
        f"{training_age_min}m ago" if training_age_min is not None
        else "unknown"
    )
    dr_label = "dry-run" if dry_run else "⚠️ LIVE"
    rows = [
        ("FreqTrade", "✅ Running, " + dr_label, f"Strategy {strategy_ver}, Binance USDT-M, isolated margin, port 8080"),
        ("FreqAI identifier", f"`{identifier}`", "Active model key"),
        ("Whitelist", f"{pair_count} pairs", "Binance USDT-M perpetuals"),
        ("Regime", f"{regime_emoji} {regime}", "From HMM (updates every 4h)"),
        ("Open trades", f"{trades['open']} ({trades['longs']}L / {trades['shorts']}S)", "Live positions"),
        ("Closed trades", str(trades["closed"]), f"All-time P&L: {trades['all_time_profit']:.2f} USDT"),
        ("Last training", training_str, "Age of most recent 'Done training' log event"),
        ("Walk-forward", wf_status, "OOS validator — gates Phase 10"),
    ]
    lines = [
        SYNC_START,
        f"> 🤖 *Auto-synced by `scripts/sync_context.py` at {ts}*",
        "",
        "## 🚀 Live System State (Auto-Synced)",
        "",
        "| Component | Status | Notes |",
        "|---|---|---|",
    ]
    for name, status, notes in rows:
        lines.append(f"| **{name}** | {status} | {notes} |")
    lines.append("")
    lines.append(SYNC_END)
    return "\n".join(lines)


def update_memory_file(block: str, dry_run_mode: bool) -> bool:
    """Replace the AUTO-SYNC block in FINBUDDY_PROJECT_MEMORY.md. Returns True if changed."""
    if not MEMORY_FILE.exists():
        print(f"WARN: {MEMORY_FILE} does not exist", file=sys.stderr)
        return False
    text = MEMORY_FILE.read_text()
    start_idx = text.find(SYNC_START)
    end_idx = text.find(SYNC_END)
    if start_idx == -1 or end_idx == -1:
        # markers not present — append block before the 🔗 Related Files section
        insert_before = "## 🔗 Related Files"
        idx = text.find(insert_before)
        if idx == -1:
            # just append
            new_text = text.rstrip() + "\n\n" + block + "\n"
        else:
            new_text = text[:idx] + block + "\n\n---\n\n" + text[idx:]
    else:
        new_text = text[:start_idx] + block + text[end_idx + len(SYNC_END):]

    if new_text == text:
        print("INFO: FINBUDDY_PROJECT_MEMORY.md already up to date (no change)")
        return False
    if not dry_run_mode:
        MEMORY_FILE.write_text(new_text)
        print(f"INFO: Updated {MEMORY_FILE}")
    else:
        print("[dry-run] Would update FINBUDDY_PROJECT_MEMORY.md")
    return True


def git_commit(dry_run_mode: bool) -> None:
    if dry_run_mode:
        print("[dry-run] Would git commit")
        return
    ts = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    try:
        subprocess.run(
            ["git", "add",
             "finbuddy_memory/FINBUDDY_PROJECT_MEMORY.md",
             "finbuddy_memory/session_events.md"],
            cwd=REPO, check=False
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=REPO
        )
        if result.returncode == 0:
            print("INFO: nothing to commit")
            return
        subprocess.run(
            ["git", "commit", "-m",
             f"chore: auto-sync project state [{ts}]\n\nCo-Authored-By: sync_context.py <noreply@anthropic.com>"],
            cwd=REPO, check=True
        )
        print("INFO: committed")
    except Exception as e:
        print(f"WARN: git commit failed: {e}", file=sys.stderr)


# ---------- main ----------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change without writing files")
    args = parser.parse_args()

    print(f"=== sync_context.py {now_utc().isoformat()} ===")

    # Read all live state
    strategy_ver = read_strategy_version()
    cfg = read_config()
    identifier = cfg.get("freqai", {}).get("identifier", "unknown")
    pair_count = len(cfg.get("exchange", {}).get("pair_whitelist", []))
    dry_run = cfg.get("dry_run", True)
    regime, regime_emoji = read_regime()
    wf_status = read_walkforward_status()
    trades = read_trade_stats()
    training_age = read_last_training_age_min()

    curr_state = {
        "strategy_version": strategy_ver,
        "freqai_identifier": identifier,
        "pair_count": pair_count,
        "regime": regime,
        "wf_status": wf_status,
        "closed_trades": trades["closed"],
        "last_sync": now_utc().isoformat(),
    }

    print(f"  strategy: {strategy_ver}")
    print(f"  identifier: {identifier}")
    print(f"  pairs: {pair_count}, dry_run: {dry_run}")
    print(f"  regime: {regime_emoji} {regime}")
    print(f"  walk-forward: {wf_status}")
    print(f"  trades open={trades['open']} ({trades['longs']}L/{trades['shorts']}S) closed={trades['closed']}")
    print(f"  last training: {training_age}m ago" if training_age else "  last training: unknown")

    # Detect changes and log events
    prev_state = load_prev_state()
    detect_and_log_changes(curr_state, prev_state)

    # Build and write the auto-sync block
    block = build_sync_block(
        strategy_ver, identifier, pair_count, dry_run,
        regime, regime_emoji, wf_status, trades, training_age
    )
    changed = update_memory_file(block, args.dry_run)

    if not args.dry_run:
        save_state(curr_state)
        if changed:
            git_commit(args.dry_run)

    print("=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
