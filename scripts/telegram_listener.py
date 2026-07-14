#!/usr/bin/env python3
"""
telegram_listener.py — Daemon that polls Telegram for button taps and executes actions.

Run as a long-lived process (started by cron if not already running):
    */2 * * * *  cd /home/ubuntu/var/www/html/trade && flock -n /tmp/finbuddy_telegram_listener.lock python3 scripts/telegram_listener.py

Architecture:
1. Runs as an infinite loop using Telegram long-polling (60s timeout per request).
2. Processes callback_query events from inline-keyboard button taps.
3. Dispatches actions by callback_data prefix:
       apply:<hash>       → run promote --apply
       skip:<hash>        → archive proposal without applying
       details:<hash>     → show config JSON
       brain:pause        → disable brain cron
       brain:resume       → re-enable brain cron
       brain:status       → reply with brain status
       forceexit:<tid>    → close one open trade via FreqTrade's real /forceexit
       trading:pause      → stop new entries (existing trades still managed)
       trading:resume     → resume new entries
4. Also handles plain text commands from the configured chat: /pause, /resume,
   /trades (lists open trades, each with an inline "Close this trade" button).

Idempotent — tracks last_update_id in state to prevent re-processing.
Response latency: < 2s (long-poll + immediate dispatch).
"""
from __future__ import annotations

import json
import subprocess
import sys
import signal
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from telegram_template import (
    get_updates, answer_callback, edit_message, send, Subsystem, Status, TELEGRAM_CHAT
)
from ft_creds import get_ft_auth

STATE_FILE = Path("/home/ubuntu/.finbuddy/state/telegram_listener.json")
PROMOTIONS_DIR = ROOT / "finbuddy_memory" / "promotions"
LOCK_FILE = Path("/tmp/finbuddy_telegram_listener.lock")
PID_FILE  = Path("/home/ubuntu/.finbuddy/state/telegram_listener.pid")
MANUAL_OVERRIDE_LOG = ROOT / "finbuddy_memory" / "trades" / "manual_overrides.jsonl"
FT_BASE = "http://127.0.0.1:8080/api/v1"

_running = True


def _sig_handler(sig, frame):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _sig_handler)
signal.signal(signal.SIGINT, _sig_handler)


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Action handlers ──────────────────────────────────────────────────────

def handle_apply(config_hash: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["python3", str(ROOT / "scripts" / "brain" / "promote.py"),
             "--apply", config_hash],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        ok = (result.returncode == 0)
        out = (result.stdout + result.stderr).strip()
        return ok, (out[-400:] if out else "applied")
    except subprocess.TimeoutExpired:
        return False, "timeout running promote --apply"
    except Exception as e:
        return False, f"error: {e}"


def handle_skip(config_hash: str) -> tuple[bool, str]:
    pending = PROMOTIONS_DIR / "pending.json"
    if not pending.exists():
        return False, "no pending proposal"
    try:
        data = json.loads(pending.read_text())
        if data.get("config_hash") != config_hash:
            return False, "hash mismatch in pending.json"
        archive = PROMOTIONS_DIR / f"skipped_{config_hash}_{int(time.time())}.json"
        archive.write_text(json.dumps(data, indent=2))
        pending.unlink()
        return True, "skipped"
    except Exception as e:
        return False, f"error: {e}"


def handle_details(config_hash: str) -> str:
    """Return the full config as clean HTML (no escaped tags) for html_context."""
    pending = PROMOTIONS_DIR / "pending.json"
    if not pending.exists():
        archives = sorted(PROMOTIONS_DIR.glob(f"*_{config_hash}_*.json"))
        if archives:
            data = json.loads(archives[-1].read_text())
        else:
            return f"No record found for <code>{config_hash}</code>"
    else:
        data = json.loads(pending.read_text())
        if data.get("config_hash") != config_hash:
            return f"Hash mismatch — pending is <code>{data.get('config_hash')}</code>"

    cfg     = data.get("config", {})
    metrics = data.get("metrics_summary", {})
    cfg_json = json.dumps(cfg, indent=2)
    lines = [
        f"<b>Config</b> <code>{config_hash}</code>",
        f"<pre>{cfg_json}</pre>",
        f"<b>Avg Profit:</b> {metrics.get('avg_profit')}%  "
        f"<b>Sharpe:</b> {metrics.get('avg_sharpe')}  "
        f"<b>Trades:</b> {metrics.get('total_trades')}",
    ]
    return "\n".join(lines)


def handle_brain(action: str) -> tuple[bool, str]:
    if action == "status":
        try:
            r = subprocess.run(
                ["python3", str(ROOT / "scripts" / "brain" / "brain_cli.py"), "status"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=30,
            )
            return True, r.stdout.strip()[-1000:]
        except Exception as e:
            return False, f"error: {e}"

    if action in ("pause", "resume"):
        try:
            current = subprocess.check_output(["crontab", "-l"], text=True)
        except Exception:
            return False, "could not read crontab"
        marker = "brain_cli.py run"
        new_lines = []
        for line in current.splitlines():
            if marker in line:
                stripped = line.lstrip("#").strip()
                if action == "pause" and not line.lstrip().startswith("#"):
                    new_lines.append("# " + line.lstrip())
                elif action == "resume" and line.lstrip().startswith("#"):
                    new_lines.append(stripped)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        cron_path = Path("/tmp/.finbuddy_crontab_edit.tmp")
        cron_path.write_text("\n".join(new_lines) + "\n")
        try:
            subprocess.check_call(["crontab", str(cron_path)])
            return True, f"brain {action}d"
        finally:
            cron_path.unlink(missing_ok=True)
    return False, f"unknown brain action: {action}"


def _append_override_log(entry: dict) -> None:
    """Same schema/file as dashboard/streamer.py's _append_override_log, just
    channel="telegram" instead of "dashboard" — the audit trail is unified
    regardless of which surface the operator used."""
    MANUAL_OVERRIDE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    with open(MANUAL_OVERRIDE_LOG, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")


def handle_forceexit(trade_id: str) -> tuple[bool, str]:
    """Manually close one open trade via FreqTrade's real /forceexit (places a
    genuine market exit order) — mirrors dashboard/streamer.py's
    force_exit_trade() endpoint so a Telegram tap and a dashboard tap do the
    exact same thing."""
    auth = get_ft_auth()
    try:
        status = requests.get(f"{FT_BASE}/status", auth=auth, timeout=10).json()
        snapshot = next((t for t in status if t.get("trade_id") == int(trade_id)), None)
    except Exception:
        snapshot = None

    try:
        r = requests.post(
            f"{FT_BASE}/forceexit", auth=auth, timeout=15,
            json={"tradeid": str(trade_id), "ordertype": "market"},
        )
    except Exception as e:
        _append_override_log({"action": "force_exit", "channel": "telegram",
                               "trade_id": trade_id, "result": "error", "ft_response": str(e)})
        return False, f"error: {e}"

    if r.status_code != 200:
        detail = r.text[:300]
        already_closed = "invalid argument" in detail.lower()
        _append_override_log({
            "action": "force_exit", "channel": "telegram", "trade_id": trade_id,
            "pair": snapshot.get("pair") if snapshot else None,
            "result": "already_closed" if already_closed else "error",
            "ft_response": detail, "snapshot": snapshot,
        })
        if already_closed:
            return True, "Trade was already closed."
        return False, detail

    body = r.json()
    _append_override_log({
        "action": "force_exit", "channel": "telegram", "trade_id": trade_id,
        "pair": snapshot.get("pair") if snapshot else None,
        "result": "closed", "ft_response": body, "snapshot": snapshot,
    })
    return True, body.get("result", "Exit order submitted.")


def handle_trading_toggle(action: str) -> tuple[bool, str]:
    """arg is 'pause' or 'resume' — pause stops new entries only, existing
    open trades keep being managed normally (SL/TP/exit_signal still fire)."""
    if action not in ("pause", "resume"):
        return False, f"unknown trading action: {action}"
    auth = get_ft_auth()
    path = "/pause" if action == "pause" else "/start"
    try:
        r = requests.post(f"{FT_BASE}{path}", auth=auth, timeout=15, json={})
    except Exception as e:
        _append_override_log({"action": f"{action}_entries", "channel": "telegram",
                               "result": "error", "ft_response": str(e)})
        return False, f"error: {e}"

    ok = r.status_code == 200
    body = r.json() if ok else {}
    _append_override_log({"action": f"{action}_entries", "channel": "telegram",
                           "result": "ok" if ok else "error",
                           "ft_response": body or r.text[:300]})
    if not ok:
        return False, r.text[:300]
    return True, body.get("status", action)


# ── Dispatcher ───────────────────────────────────────────────────────────

def dispatch_callback(update: dict) -> None:
    cq       = update["callback_query"]
    cq_id    = cq["id"]
    data     = cq.get("data", "")
    msg      = cq.get("message", {})
    message_id = msg.get("message_id")
    chat_id    = msg.get("chat", {}).get("id")

    if not data or ":" not in data:
        answer_callback(cq_id, "unknown action")
        return

    verb, arg = data.split(":", 1)

    if verb == "apply":
        ok, info = handle_apply(arg)
        label = "✅ APPLIED" if ok else "❌ APPLY FAILED"
        # answer_callback clears the spinner. show_alert=True pops up on screen.
        answer_callback(cq_id, "✅ Applied — see Telegram confirmation" if ok else f"❌ {info[:100]}", show_alert=True)
        if message_id and chat_id:
            edit_message(message_id, chat_id,
                         f"<b>{label}</b> · <code>{arg}</code>\n<i>{info[-200:]}</i>")
        # Parse key fields from output for a clean summary
        identifier = next((l.split("→")[-1].strip() for l in info.split("\n") if "→" in l and "identifier" in l.lower()), "see logs")
        send(
            subsystem=Subsystem.BRAIN_PROMOTION,
            status=Status.OK if ok else Status.FAIL,
            title="🎉 PROMOTED TO LIVE" if ok else "❌ Promotion failed",
            fields={
                "Status":     "✅ Bot restarted — retraining" if ok else f"❌ {info[:80]}",
                "Hash":       f"<code>{arg}</code>",
                "Identifier": identifier,
            },
            context="Pair-regime stats reset. New model training started." if ok else "",
        )

    elif verb == "skip":
        ok, info = handle_skip(arg)
        answer_callback(cq_id, "⏭️ Skipped" if ok else f"❌ {info}")
        if message_id and chat_id:
            label = "⏭️ SKIPPED" if ok else "❌ SKIP FAILED"
            edit_message(message_id, chat_id,
                         f"<b>{label}</b> · <code>{arg}</code>")

    elif verb == "details":
        # answer immediately so the spinner clears while we fetch the data
        answer_callback(cq_id, "Sending details...")
        details_html = handle_details(arg)
        send(
            subsystem=Subsystem.BRAIN_PROMOTION,
            status=Status.INFO,
            title=f"Config · {arg}",
            fields=None,
            html_context=details_html,   # html_context bypasses escaping
        )

    elif verb == "brain":
        ok, info = handle_brain(arg)
        answer_callback(cq_id, info[:200], show_alert=True)
        send(
            subsystem=Subsystem.BRAIN_CYCLE,
            status=Status.OK if ok else Status.FAIL,
            title=f"brain {arg}",
            fields={"Result": info[:500]},
        )

    elif verb == "forceexit":
        ok, info = handle_forceexit(arg)
        answer_callback(cq_id, "✅ Closing…" if ok else f"❌ {info[:100]}", show_alert=True)
        if message_id and chat_id:
            label = "✅ CLOSED" if ok else "❌ CLOSE FAILED"
            edit_message(message_id, chat_id,
                         f"<b>{label}</b> · trade <code>{arg}</code>\n<i>{info[-200:]}</i>")

    elif verb == "trading":
        ok, info = handle_trading_toggle(arg)
        label = "⏸️ PAUSED" if (ok and arg == "pause") else "▶️ RESUMED" if ok else "❌ FAILED"
        answer_callback(cq_id, info[:200], show_alert=True)
        if message_id and chat_id:
            edit_message(message_id, chat_id, f"<b>{label}</b>\n<i>{info[-200:]}</i>")

    else:
        answer_callback(cq_id, f"unknown verb: {verb}")


def dispatch_message(update: dict) -> None:
    """Plain text commands — /pause, /resume, /trades. Only these three; button
    taps (dispatch_callback) remain the primary interaction for everything
    else. Restricted to the configured chat — this is a single-operator bot,
    not a public one."""
    msg = update.get("message", {})
    text = (msg.get("text") or "").strip().lower()
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if chat_id != str(TELEGRAM_CHAT) or not text.startswith("/"):
        return

    cmd = text.split()[0]

    if cmd in ("/pause", "/resume"):
        action = "pause" if cmd == "/pause" else "resume"
        ok, info = handle_trading_toggle(action)
        label = ("⏸️ PAUSED" if action == "pause" else "▶️ RESUMED") if ok else "❌ FAILED"
        send(Subsystem.BRAIN_CYCLE, Status.OK if ok else Status.FAIL,
             label, fields={"Result": info[:400]}, silent=False)

    elif cmd == "/trades":
        try:
            status = requests.get(f"{FT_BASE}/status", auth=get_ft_auth(), timeout=10).json()
        except Exception as e:
            send(Subsystem.BRAIN_CYCLE, Status.FAIL, "Could not fetch open trades",
                 fields={"Error": str(e)[:300]})
            return
        if not status:
            send(Subsystem.BRAIN_CYCLE, Status.INFO, "No open trades", fields=None)
            return
        for t in status:
            side = "SHORT" if t.get("is_short") else "LONG"
            pnl = t.get("profit_abs")
            send(
                Subsystem.BRAIN_CYCLE, Status.INFO,
                f"{t.get('pair')} · {side}",
                fields={
                    "Entry": t.get("open_rate"),
                    "Current": t.get("current_rate"),
                    "P&L": f"{pnl:+.2f} USDT" if pnl is not None else "—",
                },
                buttons=[[{"text": "❌ Close this trade", "callback_data": f"forceexit:{t['trade_id']}"}]],
                silent=True,
            )


# ── Daemon loop ───────────────────────────────────────────────────────────

def run_daemon() -> None:
    """Infinite long-poll loop. Exits on SIGTERM/SIGINT or after 90min (cron restarts)."""
    import os
    my_pid = os.getpid()

    # PID-file guard: exit if another instance is already running.
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if old_pid != my_pid:
                try:
                    os.kill(old_pid, 0)   # signal 0 = check if process exists
                    print(f"[{_now()}] already running (pid {old_pid}), exiting")
                    return
                except OSError:
                    pass   # old PID is dead — stale file, overwrite
        except Exception:
            pass
    PID_FILE.write_text(str(my_pid))

    state    = _load_state()
    started  = time.time()
    # Restart every 90 min so cron can pick up code changes and avoid memory drift.
    max_age  = 90 * 60

    while _running and (time.time() - started) < max_age:
        offset = int(state.get("last_update_id", 0)) + 1
        try:
            # 55-second long-poll: Telegram holds the connection open and returns
            # immediately when an update arrives, or after 55s if nothing happened.
            updates = get_updates(offset=offset, timeout_s=55)
        except Exception as e:
            print(f"[{_now()}] getUpdates error: {e}", file=sys.stderr)
            time.sleep(10)   # back off on error — prevents spin loop
            continue

        if updates is None:
            time.sleep(10)
            continue

        for update in updates:
            uid = update.get("update_id", 0)
            try:
                if "callback_query" in update:
                    dispatch_callback(update)
                elif "message" in update:
                    dispatch_message(update)
            except Exception as e:
                print(f"[{_now()}] ERR update {uid}: {e}", file=sys.stderr)
            state["last_update_id"] = max(state.get("last_update_id", 0), uid)

        if updates:
            _save_state(state)
            print(f"[{_now()}] Processed {len(updates)} updates", flush=True)
        else:
            # Heartbeat each poll cycle (55s) so log file mtime updates
            print(f"[{_now()}] poll — 0 updates", flush=True)

    _save_state(state)
    PID_FILE.unlink(missing_ok=True)
    print(f"[{_now()}] daemon exit (uptime {int(time.time()-started)}s)")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> int:
    # flock -n in the cron prevents two daemons running at once.
    # If already running (lock held) the cron silently skips — that's correct.
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    run_daemon()
    return 0


if __name__ == "__main__":
    sys.exit(main())
