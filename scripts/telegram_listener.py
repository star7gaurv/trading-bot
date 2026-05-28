#!/usr/bin/env python3
"""
telegram_listener.py — Daemon that polls Telegram for button taps and executes actions.

Run as a long-lived process (started by cron if not already running):
    */2 * * * *  cd /home/ubuntu/var/www/html/trade && flock -n /tmp/finbuddy_telegram_listener.lock python3 scripts/telegram_listener.py

Architecture:
1. Runs as an infinite loop using Telegram long-polling (60s timeout per request).
2. Processes callback_query events from inline-keyboard button taps.
3. Dispatches actions by callback_data prefix:
       apply:<hash>   → run promote --apply
       skip:<hash>    → archive proposal without applying
       details:<hash> → show config JSON
       brain:pause    → disable brain cron
       brain:resume   → re-enable brain cron
       brain:status   → reply with brain status

Idempotent — tracks last_update_id in state to prevent re-processing.
Response latency: < 2s (long-poll + immediate dispatch).
"""
from __future__ import annotations

import json
import subprocess
import sys
import signal
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from telegram_template import (
    get_updates, answer_callback, edit_message, send, Subsystem, Status
)

STATE_FILE = Path("/home/ubuntu/.finbuddy/state/telegram_listener.json")
PROMOTIONS_DIR = ROOT / "finbuddy_memory" / "promotions"
LOCK_FILE = Path("/tmp/finbuddy_telegram_listener.lock")
PID_FILE  = Path("/home/ubuntu/.finbuddy/state/telegram_listener.pid")

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

    else:
        answer_callback(cq_id, f"unknown verb: {verb}")


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
