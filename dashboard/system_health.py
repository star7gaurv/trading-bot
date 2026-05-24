"""
System health metrics for the dashboard: load average, disk, memory, docker containers.

All commands run under a 5s timeout. Empty/partial data on failure — never raises.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional


def _safe_run(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def load_average() -> dict:
    try:
        l1, l5, l15 = os.getloadavg()
        cores = os.cpu_count() or 1
        return {
            "load_1m": round(l1, 2),
            "load_5m": round(l5, 2),
            "load_15m": round(l15, 2),
            "cores": cores,
            "utilization_pct": round((l1 / cores) * 100, 1),
        }
    except (OSError, AttributeError):
        return {"load_1m": None, "load_5m": None, "load_15m": None, "cores": None, "utilization_pct": None}


def disk_usage(path: str = "/home") -> dict:
    try:
        usage = shutil.disk_usage(path)
        used_pct = (usage.used / usage.total) * 100 if usage.total else 0
        return {
            "path": path,
            "total_gb": round(usage.total / 1024**3, 1),
            "used_gb": round(usage.used / 1024**3, 1),
            "free_gb": round(usage.free / 1024**3, 1),
            "used_pct": round(used_pct, 1),
            "status": "ok" if used_pct < 80 else ("warn" if used_pct < 90 else "critical"),
        }
    except OSError:
        return {"path": path, "error": "unavailable"}


def memory_usage() -> dict:
    """Parse /proc/meminfo (Linux only)."""
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                info[key] = int(val)  # value is in kB
    except (OSError, ValueError):
        return {"error": "unavailable"}

    total_kb = info.get("MemTotal", 0)
    available_kb = info.get("MemAvailable", 0)
    used_kb = total_kb - available_kb
    used_pct = (used_kb / total_kb) * 100 if total_kb else 0
    return {
        "total_gb": round(total_kb / 1024**2, 1),
        "used_gb": round(used_kb / 1024**2, 1),
        "available_gb": round(available_kb / 1024**2, 1),
        "used_pct": round(used_pct, 1),
        "status": "ok" if used_pct < 80 else ("warn" if used_pct < 90 else "critical"),
    }


def uptime_seconds() -> Optional[int]:
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError):
        return None


def docker_containers() -> list[dict]:
    """List running docker containers with name, status, uptime, image."""
    raw = _safe_run([
        "docker", "ps",
        "--format", "{{.Names}}|||{{.Status}}|||{{.Image}}|||{{.CreatedAt}}",
    ])
    if not raw:
        return []
    containers = []
    for line in raw.strip().splitlines():
        parts = line.split("|||")
        if len(parts) < 4:
            continue
        containers.append({
            "name": parts[0],
            "status": parts[1],
            "image": parts[2],
            "created_at": parts[3],
        })
    return containers


def freqtrade_status() -> dict:
    """Specifically check the live freqtrade container — most important process."""
    containers = docker_containers()
    ft = next((c for c in containers if c["name"] == "freqtrade"), None)
    if not ft:
        return {"running": False, "status": "container not found"}
    return {
        "running": True,
        "status": ft["status"],
        "image": ft["image"],
    }


def streamer_self() -> dict:
    """This process — uptime + PID."""
    try:
        with open("/proc/self/stat") as f:
            stat = f.read().split()
        # field 22 is starttime in clock ticks since boot
        starttime_ticks = int(stat[21])
        clock_ticks = os.sysconf("SC_CLK_TCK")
        system_uptime = uptime_seconds() or 0
        process_age_s = system_uptime - (starttime_ticks // clock_ticks)
        return {
            "pid": os.getpid(),
            "uptime_s": process_age_s,
        }
    except (OSError, IndexError, ValueError):
        return {"pid": os.getpid(), "uptime_s": None}


def full_snapshot() -> dict:
    """Combined snapshot used by /api/system/health."""
    return {
        "ts": int(time.time()),
        "load": load_average(),
        "disk": disk_usage("/home"),
        "memory": memory_usage(),
        "uptime_s": uptime_seconds(),
        "freqtrade": freqtrade_status(),
        "containers": docker_containers(),
        "streamer": streamer_self(),
    }


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(full_snapshot(), indent=2))
