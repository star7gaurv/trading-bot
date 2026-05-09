#!/usr/bin/env python3
"""
FinBuddy Trade Post-Mortem Writer

For every closed trade not yet recorded, append a one-line memorandum to
`finbuddy_memory/trades/closed.md`. This is the closed-loop feedback the
brain has been missing — without it, FreqAI trains on price labels but
never sees its own real-world outcomes.

Each entry captures:
  date, pair, side, hold time, P&L %, P&L $, exit_reason, regime at close,
  enter_tag (strategy slot fired)

Idempotent: tracks last-processed trade id in state file. Safe to re-run.
Designed to run every 15m via cron.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/tradesv3.sqlite")
TRADES_LOG = Path("/home/ubuntu/var/www/html/trade/finbuddy_memory/trades/closed.md")
REGIME_FILE = Path("/home/ubuntu/var/www/html/trade/finbuddy_memory/regimes/current.json")
STATE_FILE = Path("/home/ubuntu/.finbuddy/state/postmortem_state.json")
CONFIG_PATH = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json")

# Bias-detector config: alert if last N trades (closed + open) are ≥THRESHOLD% one-sided.
BIAS_WINDOW = 10            # last N trades to inspect
BIAS_THRESHOLD = 0.85       # 85% or more on one side fires alert
BIAS_COOLDOWN_HOURS = 6     # don't repeat the same direction alert within this window

HEADER = """# FinBuddy — Closed Trade Ledger

> Auto-written by `scripts/trade_postmortem.py` every 15 minutes.
> One row per closed trade. The brain reads this back via Karpathy loop
> and external research scripts to find which slots/regimes pay off.

| Closed (UTC) | Pair | Side | Hold | P&L % | P&L $ | Exit | Regime | Tag |
|---|---|---|---|---|---|---|---|---|
"""


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"last_id": 0}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_id": 0}


def save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def current_regime() -> str:
    try:
        return json.loads(REGIME_FILE.read_text()).get("regime", "?")
    except Exception:
        return "?"


def humanize_hold(open_date: str, close_date: str) -> str:
    try:
        o = datetime.fromisoformat(open_date.split(".")[0])
        c = datetime.fromisoformat(close_date.split(".")[0])
        delta = c - o
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        if h >= 24:
            d, h = divmod(h, 24)
            return f"{d}d{h}h"
        return f"{h}h{m:02d}m"
    except Exception:
        return "?"


def fetch_new_closed(since_id: int) -> list[tuple]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        c = conn.cursor()
        return c.execute(
            """
            SELECT id, pair, is_short, open_date, close_date,
                   close_profit, close_profit_abs, exit_reason, enter_tag, strategy
            FROM trades
            WHERE is_open = 0 AND id > ?
            ORDER BY id ASC
            """,
            (since_id,),
        ).fetchall()
    finally:
        conn.close()


def ensure_log() -> None:
    TRADES_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not TRADES_LOG.exists():
        TRADES_LOG.write_text(HEADER)


def telegram_send(msg: str) -> bool:
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        tg = cfg.get("telegram") or {}
        token, chat_id = tg.get("token"), tg.get("chat_id")
        if not (token and chat_id):
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id, "text": msg,
            "parse_mode": "Markdown", "disable_web_page_preview": "true",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"WARN: telegram failed: {e}", file=sys.stderr)
        return False


def fetch_recent_sides(limit: int) -> list[bool]:
    """Return is_short flags for last N trades (open + closed). Most recent first."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            """SELECT is_short FROM trades
               ORDER BY id DESC LIMIT ?""", (limit,),
        ).fetchall()
        return [bool(r[0]) for r in rows]
    finally:
        conn.close()


def check_trade_bias(state: dict) -> None:
    """If last BIAS_WINDOW trades are ≥BIAS_THRESHOLD one-sided, send Telegram alert.
    Tracks last alert direction + timestamp in state to avoid spam."""
    sides = fetch_recent_sides(BIAS_WINDOW)
    if len(sides) < BIAS_WINDOW:
        return  # not enough trades yet
    short_count = sum(1 for s in sides if s)
    long_count = len(sides) - short_count
    short_ratio = short_count / len(sides)
    long_ratio = long_count / len(sides)

    direction = None
    if short_ratio >= BIAS_THRESHOLD:
        direction = "SHORT"
        ratio = short_ratio
    elif long_ratio >= BIAS_THRESHOLD:
        direction = "LONG"
        ratio = long_ratio
    if direction is None:
        return

    # cooldown check
    bias_state = state.get("bias_alert", {})
    last_dir = bias_state.get("direction")
    last_ts_str = bias_state.get("ts")
    if last_dir == direction and last_ts_str:
        try:
            last_ts = datetime.fromisoformat(last_ts_str)
            if datetime.now(timezone.utc).replace(tzinfo=None) - last_ts < timedelta(hours=BIAS_COOLDOWN_HOURS):
                return  # still cooling down
        except Exception:
            pass

    msg = (
        f"⚠️ *FinBuddy Trade Bias Detected*\n\n"
        f"Last {BIAS_WINDOW} trades: *{ratio:.0%} {direction}*\n"
        f"({short_count} SHORT / {long_count} LONG)\n\n"
        f"_Possible causes:_\n"
        f"• Model genuinely sees one-sided opportunity (regime-driven)\n"
        f"• Model bias (training data skew, label imbalance)\n"
        f"• Macro filter is gating one side\n\n"
        f"Check FreqAI predictions and regime, ensure both sides can fire."
    )
    if telegram_send(msg):
        state["bias_alert"] = {
            "direction": direction,
            "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        print(f"BIAS ALERT: {ratio:.0%} {direction}")


def format_row(row: tuple, regime: str) -> str:
    tid, pair, is_short, open_d, close_d, profit_pct, profit_abs, exit_reason, enter_tag, strategy = row
    side = "SHORT" if is_short else "LONG"
    hold = humanize_hold(open_d, close_d)
    pct = (profit_pct or 0) * 100
    abs_p = profit_abs or 0
    closed_short = (close_d or "?").split(".")[0]
    et = (enter_tag or "-")[:24]
    er = (exit_reason or "-")[:18]
    return f"| {closed_short} | {pair} | {side} | {hold} | {pct:+.2f}% | {abs_p:+.2f} | {er} | {regime} | {et} |\n"


def main() -> int:
    state = load_state()
    last_id = int(state.get("last_id", 0))
    new_rows = fetch_new_closed(last_id)

    if new_rows:
        ensure_log()
        regime = current_regime()
        with TRADES_LOG.open("a") as f:
            for row in new_rows:
                f.write(format_row(row, regime))
        new_last = max(r[0] for r in new_rows)
        state["last_id"] = new_last
        print(f"OK: appended {len(new_rows)} trades (last_id={new_last})")
    else:
        print("OK: no new closed trades")

    # Bias check runs every cycle — uses live trades + recent closed
    check_trade_bias(state)

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
