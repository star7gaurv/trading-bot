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
DISK_USAGE_WARN_PCT = 80        # warn when filesystem usage exceeds this %
DISK_USAGE_CRITICAL_PCT = 90    # critical alert at this %

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


def check_disk_usage() -> tuple[int, int, str]:
    """Returns (used_pct, available_gb, mount_point) for / filesystem.
    Returns (-1, -1, '?') on failure."""
    try:
        import shutil
        usage = shutil.disk_usage("/")
        used_pct = int((usage.used / usage.total) * 100)
        available_gb = int(usage.free / (1024**3))
        return used_pct, available_gb, "/"
    except Exception as e:
        print(f"WARN: disk check failed: {e}", file=sys.stderr)
        return -1, -1, "?"


def container_running(name: str) -> bool:
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=5,
        )
        return out.returncode == 0 and out.stdout.strip() == "true"
    except Exception:
        return False


FILE_LOG = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/logs/freqtrade.log")
FILE_LOG_ROTATED = [
    Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/logs/freqtrade.log.1"),
    Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/logs/freqtrade.log.2"),
]


def _scan_lines_for_pattern(lines: list[str], pattern: str, cutoff: datetime) -> datetime | None:
    """Scan log lines for pattern, return newest timestamp >= cutoff or None."""
    last_ts = None
    for line in lines:
        if pattern not in line:
            continue
        m = LOG_LINE_RE.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        if last_ts is None or ts > last_ts:
            last_ts = ts
    return last_ts


def latest_log_match(pattern: str, since_min: int, use_file_fallback: bool = False) -> datetime | None:
    """Return timestamp of most recent log line matching pattern, or None.

    Primary source: docker logs (current container buffer).
    Fallback (use_file_fallback=True): if docker logs yields no match OR times out,
    scan the on-disk log file. Handles two known failure modes:
    1. Docker buffer evicted by error-message spam (training check).
    2. Docker daemon slow during docker-compose run (heartbeat check, 2026-05-09).
    """
    cutoff = now_utc() - timedelta(minutes=since_min)
    docker_result = None
    try:
        out = subprocess.run(
            ["docker", "logs", CONTAINER, "--since", f"{since_min}m"],
            capture_output=True, text=True, timeout=30,  # raised from 15s — docker slow during compose run
        )
        if out.returncode == 0:
            haystack = (out.stdout + "\n" + out.stderr).splitlines()
            docker_result = _scan_lines_for_pattern(haystack, pattern, cutoff)
    except Exception as e:
        print(f"ERR: docker logs failed: {e}", file=sys.stderr)

    if docker_result is not None:
        return docker_result

    if not use_file_fallback:
        return None

    # Fallback: scan on-disk log files (handles Docker buffer eviction by error spam)
    file_result = None
    for log_path in [FILE_LOG] + FILE_LOG_ROTATED:
        if not log_path.exists():
            continue
        try:
            lines = log_path.read_text(errors="replace").splitlines()
            ts = _scan_lines_for_pattern(lines, pattern, cutoff)
            if ts and (file_result is None or ts > file_result):
                file_result = ts
        except Exception as e:
            print(f"ERR: reading {log_path}: {e}", file=sys.stderr)

    if file_result:
        print(f"INFO: docker logs had no match; file log found pattern at {file_result}")
    return file_result


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
    # use_file_fallback=True: if Docker's buffer is evicted by error spam,
    # fall back to the on-disk freqtrade.log so we don't false-alert.
    last_train = latest_log_match("Done training", since_min=TRAINING_MAX_AGE_MIN + 30, use_file_fallback=True)
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
    # use_file_fallback=True: docker daemon can be slow when docker-compose run
    # spawns a new container (walk-forward folds), causing docker logs to time out
    # and generate a false "heartbeat lost" alert (seen 2026-05-09).
    last_hb = latest_log_match("Bot heartbeat", since_min=HEARTBEAT_MAX_AGE_MIN + 2, use_file_fallback=True)
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

    # 4. disk usage — Oracle free tier ~50GB, FreqAI models accumulate silently
    used_pct, avail_gb, mount = check_disk_usage()
    if used_pct >= DISK_USAGE_CRITICAL_PCT:
        maybe_alert(state, "disk",
                    f"🚨 *FinBuddy disk CRITICAL* — `{mount}` at {used_pct}% used "
                    f"({avail_gb}GB free). Bot will fail when disk fills. "
                    f"Clean old FreqAI models or rotated logs NOW.")
        issues.append("disk")
    elif used_pct >= DISK_USAGE_WARN_PCT:
        maybe_alert(state, "disk",
                    f"⚠️ *FinBuddy disk warning* — `{mount}` at {used_pct}% used "
                    f"({avail_gb}GB free). Consider cleaning old model dirs.")
        issues.append("disk")
    elif used_pct >= 0:
        maybe_recover(state, "disk",
                      f"✅ FinBuddy disk pressure cleared — {mount} at {used_pct}% ({avail_gb}GB free).")

    save_state(state)
    if issues:
        print(f"FAIL: {','.join(issues)}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
