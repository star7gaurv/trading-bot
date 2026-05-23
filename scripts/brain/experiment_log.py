"""
experiment_log.py — Append-only JSONL store for every backtest the brain runs.

One record per (hypothesis, window) result. Queryable via Python or jq.

Schema (versioned; field names stable across versions):
  schema_version    int        — 1 (current)
  hypothesis_id     str        — uuid4
  parent_id         str|null   — id of hypothesis this was derived from
  band              str        — "safe" | "aggressive" | "seed"
  rationale         str        — one-line "why we tried this"
  window            str        — "bull" | "bear" | "full" | custom timerange
  timerange         str        — "YYYYMMDD-YYYYMMDD"
  config            dict       — every parameter (timeframe, K_SL, threshold, etc.)
  status            str        — "queued" | "running" | "completed" | "failed"
  created_at        iso8601    — when the hypothesis entered the queue
  started_at        iso8601|null
  completed_at      iso8601|null
  metrics           dict|null  — {trades, wr, sharpe, pf, profit_pct, long_count, short_count,
                                  exit_signal_count, exit_signal_wr, stop_loss_count, max_dd}
  error             str|null   — failure message if status=failed
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path("/home/ubuntu/var/www/html/trade")
EXP_DIR = ROOT / "finbuddy_memory" / "experiments"
LOG_FILE = EXP_DIR / "log.jsonl"
QUEUE_FILE = EXP_DIR / "queue.jsonl"  # pending hypotheses
SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_append(path: Path, record: dict) -> None:
    """JSONL append. Single-writer assumption (cron-driven so safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with path.open("a") as f:
        f.write(line)


# ── Hypothesis lifecycle ───────────────────────────────────────────────────

def queue_hypothesis(
    config: dict,
    band: str,
    rationale: str,
    window: str,
    timerange: str,
    parent_id: str | None = None,
) -> str:
    """Add a new hypothesis to the queue. Returns hypothesis_id."""
    assert band in ("safe", "aggressive", "seed"), f"unknown band: {band}"
    hid = uuid.uuid4().hex[:12]
    record = {
        "schema_version": SCHEMA_VERSION,
        "hypothesis_id":  hid,
        "parent_id":      parent_id,
        "band":           band,
        "rationale":      rationale,
        "window":         window,
        "timerange":      timerange,
        "config":         config,
        "status":         "queued",
        "created_at":     _now_iso(),
        "started_at":     None,
        "completed_at":   None,
        "metrics":        None,
        "error":          None,
    }
    _atomic_append(QUEUE_FILE, record)
    return hid


def read_queue() -> list[dict]:
    """Read all queued hypotheses."""
    if not QUEUE_FILE.exists():
        return []
    out = []
    with QUEUE_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_log() -> list[dict]:
    """Read all completed experiment results."""
    if not LOG_FILE.exists():
        return []
    out = []
    with LOG_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def mark_completed(hypothesis: dict, metrics: dict, started_at: str) -> None:
    """Move a hypothesis from queue → log with metrics attached."""
    record = dict(hypothesis)
    record["status"]       = "completed"
    record["started_at"]   = started_at
    record["completed_at"] = _now_iso()
    record["metrics"]      = metrics
    _atomic_append(LOG_FILE, record)
    _remove_from_queue(record["hypothesis_id"])


def mark_failed(hypothesis: dict, error: str, started_at: str | None = None) -> None:
    """Mark a hypothesis as failed and move to log."""
    record = dict(hypothesis)
    record["status"]       = "failed"
    record["started_at"]   = started_at
    record["completed_at"] = _now_iso()
    record["error"]        = error
    _atomic_append(LOG_FILE, record)
    _remove_from_queue(record["hypothesis_id"])


def _remove_from_queue(hypothesis_id: str) -> None:
    """Rewrite queue.jsonl without the given hypothesis. O(n) but n is small."""
    if not QUEUE_FILE.exists():
        return
    keep = [r for r in read_queue() if r.get("hypothesis_id") != hypothesis_id]
    tmp = QUEUE_FILE.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for r in keep:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    tmp.replace(QUEUE_FILE)


# ── Queries ────────────────────────────────────────────────────────────────

def best_by_metric(metric: str, window: str | None = None, min_trades: int = 10) -> dict | None:
    """Return the experiment with the highest value of `metric`.

    metric: 'profit_pct' | 'sharpe' | 'wr' | 'pf' (higher = better for all)
    window: filter to this window only, or None for any
    min_trades: ignore experiments below this trade count (noise filter)
    """
    log = read_log()
    candidates = [
        r for r in log
        if r.get("status") == "completed"
        and r.get("metrics")
        and r["metrics"].get("trades", 0) >= min_trades
        and (window is None or r.get("window") == window)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r["metrics"].get(metric, -1e9), reverse=True)
    return candidates[0]


def summary_stats() -> dict:
    """Quick brain status summary."""
    log = read_log()
    queue = read_queue()
    completed = [r for r in log if r.get("status") == "completed"]
    failed = [r for r in log if r.get("status") == "failed"]
    by_band = {}
    for r in completed:
        b = r.get("band", "?")
        by_band[b] = by_band.get(b, 0) + 1
    return {
        "queued": len(queue),
        "completed": len(completed),
        "failed": len(failed),
        "by_band": by_band,
        "last_completion": completed[-1]["completed_at"] if completed else None,
    }


if __name__ == "__main__":
    # Quick smoke check
    print(json.dumps(summary_stats(), indent=2))
