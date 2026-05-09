#!/usr/bin/env python3
"""
FinBuddy Watchdog — alerts when the live FreqTrade/FreqAI bot goes silent.

Designed after the 7-day no-trade crisis (2026-05-08). The classic failure
mode is "container Up, heartbeat ticking, but training never re-fires and
predictions stale" — the bot looks alive but is silently broken.

Checks (run every 30m via cron):
  1. Container `freqtrade` is running (docker inspect)
  2. At least one `Done training` event in the last 8h
     (live_retrain_hours=4, so an 8h gap = two missed cycles = broken)
  3. At least one `Bot heartbeat` line in the last 5m
     (heartbeat is per-minute; 5m gap = bot loop dead)

Alerts go to Telegram via the credentials already in config.json. A per-check
cooldown prevents spam (default 1h between repeat alerts of the same issue),
and recovery messages fire once when an issue clears.

State file: /home/ubuntu/.finbuddy/state/watchdog_alerts.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------- config ----------
CONFIG_PATH = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json")
STATE_DIR = Path("/home/ubuntu/.finbuddy/state")
STATE_FILE = STATE_DIR / "watchdog_alerts.json"
CONTAINER = "freqtrade"

TRAINING_MAX_AGE_MIN = 8 * 60   # 8h
HEARTBEAT_MAX_AGE_MIN = 5       # 5m
ALERT_COOLDOWN_MIN = 60         # don't repeat same alert within 1h

LOG_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


# ---------- helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # docker logs are naive UTC


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(s: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str))


def telegram_send(msg: str) -> bool:
    try:
        with CONFIG_PATH.open() as f:
            cfg = json.load(f)
        tg = cfg.get("telegram") or {}
        token = tg.get("token")
        chat_id = tg.get("chat_id")
        if not (token and chat_id):
            print("WARN: telegram token/chat_id missing in config.json", file=sys.stderr)
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"ERR: telegram send failed: {e}", file=sys.stderr)
        return False


def container_running(name: str) -> bool:
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=5,
        )
        return out.returncode == 0 and out.stdout.strip() == "true"
    except Exception:
        return False


def latest_log_match(pattern: str, since_min: int) -> datetime | None:
    """Return timestamp of most recent log line matching pattern, or None."""
    try:
        out = subprocess.run(
            ["docker", "logs", CONTAINER, "--since", f"{since_min}m"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return None
        # docker logs writes to stderr by default for freqtrade
        haystack = out.stdout + "\n" + out.stderr
        last_ts = None
        for line in haystack.splitlines():
            if pattern in line:
                m = LOG_LINE_RE.match(line)
                if m:
                    try:
                        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except ValueError:
                        pass
        return last_ts
    except Exception as e:
        print(f"ERR: docker logs failed: {e}", file=sys.stderr)
        return None


# ---------- alert plumbing ----------
def maybe_alert(state: dict, key: str, msg: str) -> None:
    """Send alert with per-key cooldown. Mutates state in place."""
    last = state.get(key, {}).get("last_alert")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if now_utc() - last_dt < timedelta(minutes=ALERT_COOLDOWN_MIN):
                return  # cooldown
        except Exception:
            pass
    if telegram_send(msg):
        print(f"ALERT [{key}]: {msg}")
    state[key] = {"status": "fail", "last_alert": now_utc().isoformat()}


def maybe_recover(state: dict, key: str, msg: str) -> None:
    """Send recovery msg once when previous status was fail."""
    prev = state.get(key, {}).get("status")
    if prev == "fail":
        telegram_send(msg)
        print(f"RECOVERED [{key}]")
    state[key] = {"status": "ok", "last_alert": None}


# ---------- checks ----------
def main() -> int:
    state = load_state()
    issues = []

    # 1. container up
    if not container_running(CONTAINER):
        maybe_alert(state, "container",
                    f"🚨 *FinBuddy DOWN* — container `{CONTAINER}` is not running.")
        issues.append("container")
        save_state(state)
        return 1
    maybe_recover(state, "container",
                  f"✅ FinBuddy recovered — container `{CONTAINER}` is running again.")

    # 2. recent training event
    last_train = latest_log_match("Done training", since_min=TRAINING_MAX_AGE_MIN + 30)
    if last_train is None:
        maybe_alert(state, "training",
                    f"⚠️ *FinBuddy stuck* — no `Done training` event in last {TRAINING_MAX_AGE_MIN//60}h. "
                    f"FreqAI may be silently broken (see Pitfall 1: identifier collision).")
        issues.append("training")
    else:
        age = now_utc() - last_train
        if age > timedelta(minutes=TRAINING_MAX_AGE_MIN):
            maybe_alert(state, "training",
                        f"⚠️ *FinBuddy stale models* — last `Done training` was "
                        f"{age.total_seconds()/3600:.1f}h ago (> {TRAINING_MAX_AGE_MIN//60}h threshold).")
            issues.append("training")
        else:
            maybe_recover(state, "training",
                          f"✅ FinBuddy training resumed — last event {int(age.total_seconds()/60)}m ago.")

    # 3. recent heartbeat
    last_hb = latest_log_match("Bot heartbeat", since_min=HEARTBEAT_MAX_AGE_MIN + 2)
    if last_hb is None:
        maybe_alert(state, "heartbeat",
                    f"🚨 *FinBuddy heartbeat lost* — no `Bot heartbeat` line in last {HEARTBEAT_MAX_AGE_MIN}m. "
                    f"Worker loop may be dead.")
        issues.append("heartbeat")
    else:
        age = now_utc() - last_hb
        if age > timedelta(minutes=HEARTBEAT_MAX_AGE_MIN):
            maybe_alert(state, "heartbeat",
                        f"🚨 *FinBuddy heartbeat stale* — last beat {int(age.total_seconds()/60)}m ago.")
            issues.append("heartbeat")
        else:
            maybe_recover(state, "heartbeat", "✅ FinBuddy heartbeat resumed.")

    save_state(state)
    if issues:
        print(f"FAIL: {','.join(issues)}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
