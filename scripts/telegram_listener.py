#!/usr/bin/env python3
"""
telegram_listener.py — Polls Telegram for button taps and executes actions.

Designed to run as a cron job every 2 minutes:
    */2 * * * *  cd /home/ubuntu/var/www/html/trade && python3 scripts/telegram_listener.py

Architecture:
1. Polls Telegram getUpdates with the offset tracked in state file.
2. Processes callback_query events from inline-keyboard button taps.
3. Dispatches actions by callback_data prefix:
       apply:<hash>   → run promote --apply
       skip:<hash>    → archive proposal without applying
       details:<hash> → show config JSON
       brain:pause    → disable brain cron
       brain:resume   → re-enable brain cron
       brain:status   → reply with brain status

Idempotent — tracks last_update_id in state to prevent re-processing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from telegram_template import (
    get_updates, answer_callback, edit_message, send, Subsystem, Status
)

STATE_FILE = Path("/home/ubuntu/.finbuddy/state/telegram_listener.json")
PROMOTIONS_DIR = ROOT / "finbuddy_memory" / "promotions"
LOCK_FILE = Path("/home/ubuntu/.finbuddy/state/telegram_listener.lock")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0, "processed": []}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Action handlers ──────────────────────────────────────────────────────

def handle_apply(config_hash: str) -> tuple[bool, str]:
    """Run the brain promote --apply command."""
    try:
        result = subprocess.run(
            ["python3", str(ROOT / "scripts" / "brain" / "promote.py"),
             "--apply", config_hash],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        ok = (result.returncode == 0)
        out = (result.stdout + result.stderr).strip()
        # Telegram callback alert is max 200 chars; keep it short
        return ok, (out[-200:] if out else "applied")
    except subprocess.TimeoutExpired:
        return False, "timeout running promote --apply"
    except Exception as e:
        return False, f"error: {e}"


def handle_skip(config_hash: str) -> tuple[bool, str]:
    """Archive the pending proposal without applying it."""
    pending = PROMOTIONS_DIR / "pending.json"
    if not pending.exists():
        return False, "no pending proposal"
    try:
        data = json.loads(pending.read_text())
        if data.get("config_hash") != config_hash:
            return False, "hash mismatch in pending.json"
        archive = PROMOTIONS_DIR / f"skipped_{config_hash}_{int(datetime.now(timezone.utc).timestamp())}.json"
        archive.write_text(json.dumps(data, indent=2))
        pending.unlink()
        return True, "skipped"
    except Exception as e:
        return False, f"error: {e}"


def handle_details(config_hash: str) -> str:
    """Return the full config JSON for the user (sent as new message)."""
    pending = PROMOTIONS_DIR / "pending.json"
    if not pending.exists():
        return "no pending proposal — already applied or skipped"
    try:
        data = json.loads(pending.read_text())
        if data.get("config_hash") != config_hash:
            archives = sorted(PROMOTIONS_DIR.glob(f"*_{config_hash}_*.json"))
            if archives:
                data = json.loads(archives[-1].read_text())
            else:
                return f"no record found for {config_hash}"
        cfg = data.get("config", {})
        metrics = data.get("metrics_summary", {})
        lines = [
            f"<b>Config</b> (<code>{config_hash}</code>):",
            f"<pre>{json.dumps(cfg, indent=2)}</pre>",
            f"<b>Metrics</b>: avg_profit={metrics.get('avg_profit')}% · sharpe={metrics.get('avg_sharpe')} · trades={metrics.get('total_trades')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"error reading proposal: {e}"


def handle_brain(action: str) -> tuple[bool, str]:
    """brain:pause / brain:resume / brain:status."""
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
        cron_path = Path("/tmp/.finbuddy_crontab_edit.tmp")
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
                    new_lines.append("# " + line.lstrip())   # comment out
                elif action == "resume" and line.lstrip().startswith("#"):
                    new_lines.append(stripped)                # uncomment
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        cron_path.write_text("\n".join(new_lines) + "\n")
        try:
            subprocess.check_call(["crontab", str(cron_path)])
            return True, f"brain {action}d"
        finally:
            cron_path.unlink(missing_ok=True)
    return False, f"unknown brain action: {action}"


# ── Dispatcher ───────────────────────────────────────────────────────────

def dispatch_callback(update: dict, state: dict) -> None:
    """Process a single callback_query event."""
    cq = update["callback_query"]
    cq_id = cq["id"]
    data = cq.get("data", "")
    msg = cq.get("message", {})
    message_id = msg.get("message_id")
    chat_id = msg.get("chat", {}).get("id")

    if not data or ":" not in data:
        answer_callback(cq_id, "unknown action")
        return

    verb, arg = data.split(":", 1)

    if verb == "apply":
        ok, info = handle_apply(arg)
        label = "✅ APPLIED" if ok else "❌ APPLY FAILED"
        # answer_callback clears the loading spinner — may fail if >30s since tap,
        # but the action already ran so we still send the confirmation below.
        answer_callback(cq_id, ("✅ Applied — check Telegram for confirmation" if ok else f"❌ {info[:150]}"), show_alert=True)
        if message_id and chat_id:
            edit_message(message_id, chat_id,
                         f"<b>{label}</b> · hash <code>{arg}</code>\n<i>{info[:300]}</i>")
        # Always send a fresh message — visible even if answer_callback expired.
        # Parse key fields from the apply output for a rich summary.
        identifier = next((l.split("→")[-1].strip() for l in info.split("\n") if "→" in l and "identifier" in l.lower()), "")
        new_thresh = next((l.split("updated:")[-1].strip() for l in info.split("\n") if ".env updated" in l), "")
        send(
            subsystem=Subsystem.BRAIN_PROMOTION,
            status=Status.OK if ok else Status.FAIL,
            title=f"🎉 PROMOTED TO LIVE" if ok else f"❌ Promotion failed",
            fields={
                "Status": "✅ Config live — bot restarted" if ok else f"❌ {info[:100]}",
                "Hash": f"<code>{arg}</code>",
                "Identifier": identifier or "see logs",
                "Updated": new_thresh or ".env written",
            },
            context="Pair-regime stats reset. New model training now." if ok else "",
        )

    elif verb == "skip":
        ok, info = handle_skip(arg)
        answer_callback(cq_id, ("⏭️ skipped" if ok else f"❌ {info}"))
        if message_id and chat_id:
            label = "⏭️ SKIPPED" if ok else "❌ SKIP FAILED"
            edit_message(message_id, chat_id,
                         f"<b>{label}</b> · hash <code>{arg}</code>\n<i>{info}</i>")

    elif verb == "details":
        details = handle_details(arg)
        answer_callback(cq_id, "details sent below")
        send(
            subsystem=Subsystem.BRAIN_PROMOTION,
            status=Status.INFO,
            title=f"config details · {arg}",
            fields=None,
            context=details[:3500],
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


def main() -> int:
    # Simple lock: skip if previous run still active
    if LOCK_FILE.exists():
        try:
            ts = float(LOCK_FILE.read_text())
            from time import time as _t
            if (_t() - ts) < 120:
                return 0
        except Exception:
            pass
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    from time import time as _t
    LOCK_FILE.write_text(str(_t()))

    try:
        state = _load_state()
        offset = int(state.get("last_update_id", 0)) + 1
        # Long-poll: hold connection open for 55s waiting for updates.
        # This means button taps are picked up within seconds rather than
        # up to 2 minutes (the cron interval). 55s < 60s cron so no overlap.
        updates = get_updates(offset=offset, timeout_s=55)

        for update in updates:
            uid = update.get("update_id", 0)
            try:
                if "callback_query" in update:
                    dispatch_callback(update, state)
            except Exception as e:
                print(f"ERR processing update {uid}: {e}", file=sys.stderr)
            state["last_update_id"] = max(state.get("last_update_id", 0), uid)

        _save_state(state)
        # Always print so log file mtime updates every cron tick.
        # Without this, the health dashboard shows STALE whenever no buttons are pressed.
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if updates:
            print(f"[{now}] Processed {len(updates)} updates")
        else:
            print(f"[{now}] checked — 0 updates")
        return 0
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
