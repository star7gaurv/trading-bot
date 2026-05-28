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
  status            str        — "queued" | "running" | "completed" | "failed" | "scout_failed"
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


def mark_scout_failed(hypothesis: dict, scout_metrics: dict) -> None:
    """Mark a hypothesis as rejected at the scout stage and move to log.

    scout_metrics contains the metrics from the cheap 6-pair scout run so we
    can review whether the scout gate is calibrated correctly.
    """
    record = dict(hypothesis)
    record["status"]       = "scout_failed"
    record["completed_at"] = _now_iso()
    record["metrics"]      = scout_metrics
    _atomic_append(LOG_FILE, record)
    _remove_from_queue(record["hypothesis_id"])


def experiments_today_count() -> int:
    """Count experiments logged today (any terminal status). Used for scout bypass cadence."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(
        1 for r in read_log()
        if (r.get("completed_at") or "").startswith(today)
    )


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


def _config_signature(config: dict) -> str:
    """Stable hash of a config dict ignoring window/identity fields.

    Two hypotheses share a config if all parameters except hypothesis_id,
    window, timerange, and created_at are identical.
    """
    skip = {"hypothesis_id", "parent_id", "window", "timerange", "created_at",
            "started_at", "completed_at", "status", "metrics", "error",
            "band", "rationale", "schema_version"}
    canonical = {k: v for k, v in config.items() if k not in skip}
    return json.dumps(canonical, sort_keys=True)


def prioritize_same_config(completed_hypothesis: dict) -> int:
    """Move all queued entries with the same config to the front of the queue.

    Called after a passing experiment (profit>0, sharpe>0) to fast-track
    cross-window validation. Returns number of entries promoted.

    The queue is rewritten so matching entries come first, preserving the
    relative order of non-matching entries. Safe to call concurrently — uses
    the same atomic tmp-replace pattern as _remove_from_queue.
    """
    if not QUEUE_FILE.exists():
        return 0
    target_sig = _config_signature(completed_hypothesis.get("config", {}))
    all_queued = read_queue()
    priority = [e for e in all_queued
                if e.get("status") == "queued"
                and _config_signature(e.get("config", {})) == target_sig]
    if not priority:
        return 0
    rest = [e for e in all_queued if e not in priority]
    tmp = QUEUE_FILE.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for e in priority + rest:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    tmp.replace(QUEUE_FILE)
    return len(priority)


def prioritize_regime_windows(regime: str) -> int:
    """Reorder the queue so experiments for the current regime run first.

    regime: "BEAR" moves bear_* windows to front; "BULL" moves bull_* to front.
    Entries not matching the regime are pushed to the back, preserving their
    relative order within each group. Returns number of entries moved to front.

    Called by `brain_cli.py seed-regime` and optionally after each experiment
    completion in runner.py to keep the queue aligned with the live market.
    """
    if not QUEUE_FILE.exists():
        return 0
    regime_key = regime.strip().lower()   # "bear" or "bull"
    all_queued = read_queue()
    front = [e for e in all_queued
             if e.get("status") == "queued"
             and regime_key in e.get("window", "").lower()]
    if not front:
        return 0
    back = [e for e in all_queued if e not in front]
    tmp = QUEUE_FILE.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for e in front + back:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    tmp.replace(QUEUE_FILE)
    return len(front)


def queue_missing_windows(completed_hypothesis: dict, windows: dict[str, str]) -> int:
    """After a passing run, auto-queue any windows not yet tested or queued for this config.

    This is the cross-window validation accelerator: when the brain finds a
    promising config on window A, it immediately queues it on windows B/C/D/E
    instead of waiting for the random exploration to rediscover it.

    Returns number of new entries added.
    """
    config = completed_hypothesis.get("config", {})
    this_sig = _config_signature(config)

    # Collect windows already covered: queued (pending) OR completed successfully.
    # IMPORTANT: "failed" experiments do NOT count as covered — failed = no data
    # collected, must retry. A timed-out bull experiment should be re-queued.
    covered: set[str] = set()
    for entry in read_queue():
        if _config_signature(entry.get("config", {})) == this_sig:
            covered.add(entry.get("window", ""))
    for entry in read_log():
        if (_config_signature(entry.get("config", {})) == this_sig
                and entry.get("status") == "completed"):
            covered.add(entry.get("window", ""))

    added = 0
    for win_name, timerange in windows.items():
        if win_name in covered:
            continue
        profit = completed_hypothesis.get("metrics", {}) or {}
        profit_pct = profit.get("profit_pct", 0)
        wr = profit.get("wr", 0)
        queue_hypothesis(
            config=config,
            band=completed_hypothesis.get("band", "aggressive"),
            rationale=(
                f"cross-window: derived from {completed_hypothesis['hypothesis_id'][:8]} "
                f"(profit={profit_pct:+.2f}% WR={wr*100:.1f}%) on "
                f"{completed_hypothesis.get('window', '?')}"
            ),
            window=win_name,
            timerange=timerange,
            parent_id=completed_hypothesis.get("hypothesis_id"),
        )
        added += 1
    return added


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
    completed    = [r for r in log if r.get("status") == "completed"]
    failed       = [r for r in log if r.get("status") == "failed"]
    scout_failed = [r for r in log if r.get("status") == "scout_failed"]
    by_band = {}
    for r in completed:
        b = r.get("band", "?")
        by_band[b] = by_band.get(b, 0) + 1
    return {
        "queued":       len(queue),
        "completed":    len(completed),
        "failed":       len(failed),
        "scout_failed": len(scout_failed),
        "by_band":      by_band,
        "last_completion": completed[-1]["completed_at"] if completed else None,
    }


if __name__ == "__main__":
    # Quick smoke check
    print(json.dumps(summary_stats(), indent=2))
