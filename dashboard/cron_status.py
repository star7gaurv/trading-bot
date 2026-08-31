"""
Parse the current crontab and report health per job.

For each cron entry we figure out:
- name (last script in the command)
- schedule (cron expression)
- log path (everything after the last `>>` or `>`)
- last run timestamp (mtime of log file)
- staleness (last_run age vs 2x expected interval)
- tail of log (last 5 non-empty lines)

This is read-only and safe to expose to the dashboard.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional


def _run_crontab() -> str:
    try:
        out = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        )
        return out.stdout if out.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _expected_interval_seconds(schedule: str) -> Optional[int]:
    """Approximate the expected gap between runs for the given cron schedule.

    Returns None if the schedule is too irregular to estimate.
    """
    parts = schedule.split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts[0], parts[1], parts[2], parts[3], parts[4]

    # Every N minutes: */N
    m = re.match(r"\*/(\d+)", minute)
    if m and hour == "*":
        return int(m.group(1)) * 60

    # Specific minute, every N hours: M */N
    m_min = re.match(r"^\d+$", minute)
    m_hr = re.match(r"\*/(\d+)", hour)
    if m_min and m_hr:
        return int(m_hr.group(1)) * 3600

    # Daily (specific time, every day)
    if m_min and re.match(r"^\d+$", hour) and dom == "*" and month == "*" and dow == "*":
        return 24 * 3600

    # Every N days
    m_dom = re.match(r"\*/(\d+)", dom)
    if m_min and re.match(r"^\d+$", hour) and m_dom:
        return int(m_dom.group(1)) * 24 * 3600

    # Hourly (specific minute, every hour)
    if m_min and hour == "*":
        return 3600

    return None


def _extract_log_path(command: str) -> Optional[str]:
    # >> /path  or  > /path  (with optional 2>&1 trailing)
    m = re.search(r">>?\s*(\S+)", command)
    if not m:
        return None
    return m.group(1)


def _extract_name(command: str) -> str:
    # Find the last .py / .sh in the command — that's usually the script
    matches = re.findall(r"(\S+\.(?:py|sh))", command)
    if matches:
        return Path(matches[-1]).name
    # Fall back to first token after any cd...&&
    if "&&" in command:
        command = command.split("&&")[-1]
    tokens = command.strip().split()
    return tokens[0] if tokens else "unknown"


def _tail_log(path: str, n: int = 5) -> list[str]:
    try:
        out = subprocess.run(
            ["tail", "-n", str(n * 4), path], capture_output=True, text=True, timeout=3
        )
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        return lines[-n:]
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        return []


_BRAIN_LOCK = "/tmp/finbuddy_brain_run.lock"
_WF_LOCK    = "/tmp/walkforward_deep.lock"

# The crontab is shared with other, unrelated projects on this server
# (e.g. siteserve, siteserve-filament5). Only surface jobs that belong to
# this project — recognized by their log path living under one of these.
# (Commands aren't reliable to filter on: several jobs use a bare relative
# script path with no `cd`/absolute prefix, so the log path is the one
# thing every job here consistently roots in this project.)
_PROJECT_LOG_PREFIXES = (
    "/home/ubuntu/var/www/html/trade",
    "/home/ubuntu/.finbuddy",
)
_PROJECT_LOG_EXACT = {
    "/home/ubuntu/finbuddy_memory_cron.log",  # auto_commit.sh (vault git commit)
}


def _belongs_to_project(log_path: Optional[str]) -> bool:
    if not log_path:
        return True
    return log_path.startswith(_PROJECT_LOG_PREFIXES) or log_path in _PROJECT_LOG_EXACT


def _lock_is_held(lock_path: str) -> bool:
    """Return True if a flock lock file is currently held by another process."""
    try:
        r = subprocess.run(
            ["flock", "-n", lock_path, "true"],
            capture_output=True, timeout=2,
        )
        return r.returncode != 0
    except Exception:
        return False


def _classify_status(last_run_age_s: Optional[int], expected_interval_s: Optional[int]) -> str:
    if last_run_age_s is None:
        return "unknown"
    if expected_interval_s is None:
        # Couldn't estimate cadence — call it ok if log exists and was touched in last 7 days
        return "ok" if last_run_age_s < 7 * 24 * 3600 else "stale"
    if last_run_age_s > 2 * expected_interval_s:
        return "stale"
    return "ok"


def parse_crontab() -> list[dict]:
    """Return a list of dicts, one per cron job."""
    raw = _run_crontab()
    if not raw:
        return []

    now = int(time.time())
    jobs = []
    seen_names: dict[str, int] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Skip env-var lines like PATH=...
        if "=" in line and " " not in line.split("=", 1)[0]:
            # crontab var, not a job
            if not re.match(r"^[\*\d/,\-]", line):
                continue

        # Cron line: <m> <h> <dom> <mon> <dow> <command>
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue

        schedule = " ".join(parts[:5])
        command = parts[5]

        log_path = _extract_log_path(command)
        if not _belongs_to_project(log_path):
            continue

        name = _extract_name(command)
        # Disambiguate duplicates (e.g. memory_writer.py appears twice)
        if name in seen_names:
            seen_names[name] += 1
            display_name = f"{name} (#{seen_names[name]})"
        else:
            seen_names[name] = 1
            display_name = name

        last_run_ts = None
        last_run_age = None
        tail = []

        if log_path and os.path.exists(log_path):
            try:
                last_run_ts = int(os.path.getmtime(log_path))
                last_run_age = now - last_run_ts
            except OSError:
                pass
            tail = _tail_log(log_path, n=5)

        expected = _expected_interval_seconds(schedule)
        status = _classify_status(last_run_age, expected)

        # Long-running jobs: if the experiment lock is held the job IS running —
        # the log goes quiet during the run so mtime-based staleness is a false
        # positive. Override to "running" so the dashboard shows the correct state.
        if status == "stale":
            if "brain_cli" in name and " run" in command:
                if _lock_is_held(_BRAIN_LOCK):
                    status = "running"
            elif "walkforward" in name or "walk_forward" in name:
                if _lock_is_held(_WF_LOCK) or _lock_is_held("/tmp/walkforward_daily.lock"):
                    status = "running"

        jobs.append({
            "name": display_name,
            "schedule": schedule,
            "command": command,
            "log_path": log_path,
            "last_run_ts": last_run_ts,
            "last_run_age_s": last_run_age,
            "expected_interval_s": expected,
            "status": status,  # "ok" | "stale" | "unknown"
            "tail": tail,
        })

    return jobs


def summarize(jobs: list[dict]) -> dict:
    total = len(jobs)
    ok      = sum(1 for j in jobs if j["status"] == "ok")
    running = sum(1 for j in jobs if j["status"] == "running")
    stale   = sum(1 for j in jobs if j["status"] == "stale")
    unknown = sum(1 for j in jobs if j["status"] == "unknown")
    return {
        "total": total,
        "ok": ok,
        "running": running,
        "stale": stale,
        "unknown": unknown,
        "overall": "ok" if stale == 0 else ("warn" if stale <= 2 else "critical"),
    }


if __name__ == "__main__":
    import json as _json

    jobs = parse_crontab()
    print(_json.dumps({"summary": summarize(jobs), "jobs": jobs}, indent=2))
