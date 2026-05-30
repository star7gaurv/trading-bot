#!/usr/bin/env python3
"""
FinBuddy Watchdog — alerts when the live FreqTrade/FreqAI bot goes silent.

Designed after the 7-day no-trade crisis (2026-05-08). The classic failure
mode is "container Up, heartbeat ticking, but training never re-fires and
predictions stale" — the bot looks alive but is silently broken.

Checks (run every 30m via cron):
  1. Container `freqtrade` is running (docker inspect)
  2. At least one `Done training` event in the last 14h
     (live_retrain_hours=12 + 2h buffer; update this comment if retrain hours change)
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

TRAINING_MAX_AGE_MIN = 14 * 60  # 14h (live_retrain_hours=12 + 2h buffer; was 8h when retrain=4h)
HEARTBEAT_MAX_AGE_MIN = 5       # 5m
ALERT_COOLDOWN_MIN = 60         # don't repeat same alert within 1h
DISK_USAGE_WARN_PCT = 80        # warn when filesystem usage exceeds this %
DISK_USAGE_CRITICAL_PCT = 90    # critical alert at this %
CPU_CORES = 4                   # Oracle Free Tier ARM64
CPU_LOAD_WARN = CPU_CORES       # 4.0 — all cores busy, bot may slow
CPU_LOAD_CRITICAL = CPU_CORES * 1.5  # 6.0 — server saturated, brain + WF fighting bot

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


def telegram_send(msg: str, *, is_recovery: bool = False) -> bool:
    """Watchdog telegram sender → routes through unified template.

    `msg` is parsed for the check-key from the existing call-site convention
    (e.g. "❌ container down", "✅ container up"). We extract the check name and
    re-format as a proper template message.
    """
    try:
        # Import template lazily to avoid circular issues if template lib changes
        sys.path.insert(0, "/home/ubuntu/var/www/html/trade/scripts/lib")
        from telegram_template import send as _tg_send, Subsystem, Status as _Status

        status = _Status.OK if is_recovery else _Status.FAIL
        # Strip leading emoji + bold markers if present (legacy markdown)
        title = msg.replace("*", "").strip()
        if title.startswith(("❌ ", "✅ ", "🚨 ", "⚠️ ", "🟢 ", "🔴 ")):
            title = title.split(" ", 1)[1] if " " in title else title
        return _tg_send(
            subsystem=Subsystem.WATCHDOG,
            status=status,
            title=title[:140],
            fields=None,
            context=("Auto-recovered" if is_recovery else "Health check failed"),
            action=(None if is_recovery else "Check container/logs immediately"),
        )
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


def latest_log_match(
    pattern: str,
    since_min: int,
    use_file_fallback: bool = False,
    docker_since_min: int | None = None,
) -> datetime | None:
    """Return timestamp of most recent log line matching pattern, or None.

    Primary source: docker logs (current container buffer).
    Fallback (use_file_fallback=True): if docker logs yields no match OR times out,
    scan the on-disk log file. Handles two known failure modes:
    1. Docker buffer evicted by error-message spam (training check).
    2. Docker daemon slow during docker-compose run (heartbeat check, 2026-05-09).

    docker_since_min: cap the docker logs query window to avoid timeouts on long
    windows (e.g. training check asks for 8h+30m = 510m which reliably times out).
    File fallback always covers the full since_min window.
    """
    cutoff = now_utc() - timedelta(minutes=since_min)
    query_min = docker_since_min if docker_since_min is not None else since_min
    docker_result = None
    try:
        out = subprocess.run(
            ["docker", "logs", CONTAINER, "--since", f"{query_min}m"],
            capture_output=True, text=True, timeout=30,
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
        telegram_send(msg, is_recovery=True)
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

    # 1b. container uptime — alert if bot restarted unexpectedly in last 30 min
    # Bug 8 fix (2026-05-30): after a container restart FreqAI takes ~30 min to
    # stabilise predictions. Undetected restarts look like "no trades" or bad WR.
    try:
        _inspect = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.StartedAt}}", CONTAINER],
            capture_output=True, text=True, timeout=10,
        )
        if _inspect.returncode == 0:
            _started_str = _inspect.stdout.strip()
            from datetime import datetime as _dt
            # Docker returns RFC3339 like "2026-05-30T10:57:27.123456789Z"
            _started = _dt.fromisoformat(_started_str.replace("Z", "+00:00")).replace(tzinfo=None)
            _uptime_min = (now_utc() - _started).total_seconds() / 60
            if _uptime_min < 30:
                maybe_alert(
                    state, "container_restart",
                    f"⚠️ *FreqTrade restarted* — container has only been up {_uptime_min:.0f}m. "
                    f"FreqAI predictions are unstable for ~30min after restart. "
                    f"No trades during warmup is expected.",
                )
            else:
                maybe_recover(state, "container_restart",
                              f"✅ FreqTrade uptime stable ({_uptime_min:.0f}m since last start).")
    except Exception:
        pass  # non-critical

    # 2. recent training event
    # use_file_fallback=True: if Docker's buffer is evicted by error spam,
    # fall back to the on-disk freqtrade.log so we don't false-alert.
    # docker_since_min=90 prevents 510-min docker log queries timing out.
    # File fallback covers the full 8h+ window via freqtrade.log.
    last_train = latest_log_match(
        "Done training",
        since_min=TRAINING_MAX_AGE_MIN + 30,
        use_file_fallback=True,
        docker_since_min=90,
    )
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

    # 2b. FreqAI NaN training failure — 100% of training rows dropped
    # This is the catastrophic feature-pipeline failure pattern seen on 2026-05-19
    # when historical macro/regime parquets went stale → all features NaN →
    # n_samples=0 → bot trains nothing → "No model ready" for every pair.
    nan_train = latest_log_match(
        "100 percent of training data dropped",
        since_min=60,
        use_file_fallback=True,
        docker_since_min=90,
    )
    if nan_train is not None:
        age = now_utc() - nan_train
        if age < timedelta(minutes=60):
            maybe_alert(state, "training_nan",
                        f"🚨 *CRITICAL* — FreqAI dropping 100% of training rows (NaN feature pipeline). "
                        f"Last occurrence {int(age.total_seconds()/60)}m ago. "
                        f"Check `_get_macro_series` / `_get_regime_series` and historical parquet freshness "
                        f"(`python3 scripts/build_historical_macro.py && python3 scripts/build_historical_regime.py`).")
            issues.append("training_nan")
        else:
            maybe_recover(state, "training_nan", "✅ FreqAI training-NaN cleared (no occurrence in last hour).")
    else:
        maybe_recover(state, "training_nan", "✅ FreqAI feature pipeline healthy.")

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

    # 5. CPU load — alert when server is saturated (brain + WF + bot fighting for cores)
    load1, load5, _ = os.getloadavg()
    wf_active = False
    try:
        out = subprocess.run(["pgrep", "-f", "walk_forward.py"], capture_output=True, text=True)
        wf_active = out.returncode == 0
    except Exception:
        pass

    if load1 >= CPU_LOAD_CRITICAL:
        maybe_alert(state, "cpu_load",
                    f"🚨 *FinBuddy CPU CRITICAL* — load {load1:.1f} on {CPU_CORES} cores "
                    f"({load1/CPU_CORES*100:.0f}% saturation). "
                    f"{'WF is active (low-priority) but server load is critical.' if wf_active else 'WF fold + brain + live bot may be fighting.'} "
                    f"Check: `docker stats --no-stream`")
        issues.append("cpu_load")
    elif load1 >= CPU_LOAD_WARN:
        if wf_active:
            # Suppress normal warning since WF is designed to run low-priority on idle cores
            maybe_recover(state, "cpu_load",
                          f"✅ FinBuddy CPU normal (WF active and running low-priority at load {load1:.1f}).")
        else:
            maybe_alert(state, "cpu_load",
                        f"⚠️ *FinBuddy CPU high* — load {load1:.1f} on {CPU_CORES} cores. "
                        f"All cores busy — bot responses may be slow.")
            issues.append("cpu_load")
    else:
        maybe_recover(state, "cpu_load",
                      f"✅ FinBuddy CPU normal — load {load1:.1f} on {CPU_CORES} cores.")

    save_state(state)
    if issues:
        print(f"FAIL: {','.join(issues)}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
