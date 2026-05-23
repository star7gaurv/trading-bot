"""
digest.py — Daily brain progress digest to Telegram.

Reads experiment log and queue, computes:
  - experiments completed today
  - best 3 results all-time + today
  - trend in best-of-day across last 7 days
  - queue health (size, oldest pending)

Runs daily at 08:00 via cron. Sends via telegram_template (BRAIN bot).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "brain"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from experiment_log import read_log, read_queue
from telegram_template import send, Subsystem, Status


def _today_utc_bounds():
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _within(iso_str: str, start: datetime, end: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(iso_str)
        return start <= ts <= end
    except Exception:
        return False


def _best_n(records: list[dict], n: int = 3) -> list[dict]:
    records = [r for r in records
               if r.get("status") == "completed"
               and r.get("metrics", {}).get("trades", 0) >= 20]
    records.sort(key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    return records[:n]


def _fmt_result(r: dict) -> str:
    m = r["metrics"]
    cfg = r.get("config", {})
    arch = cfg.get("arch") or ("v22" if cfg.get("strategy") == "FinBuddyFreqAI" else "v23")
    return (
        f"<code>{r['hypothesis_id'][:6]}</code> [{arch}] "
        f"P&L {m.get('profit_pct'):+.2f}% · WR {m.get('wr', 0)*100:.1f}% · "
        f"PF {m.get('pf') or m.get('profit_factor', 0):.2f} · "
        f"L/S {m.get('long_count', '?')}/{m.get('short_count', '?')}"
    )


def _best_of_day_trend(log: list[dict], days: int = 7) -> list[tuple[str, float]]:
    """For each of last N days, return (date_str, best_profit_pct or NaN)."""
    out = []
    now = datetime.now(timezone.utc)
    for d in range(days, -1, -1):
        day_start = (now - timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_runs = [r for r in log
                    if r.get("status") == "completed"
                    and r.get("metrics", {}).get("trades", 0) >= 20
                    and _within(r.get("completed_at", ""), day_start, day_end)]
        if not day_runs:
            out.append((day_start.strftime("%m-%d"), None))
            continue
        best = max(day_runs, key=lambda r: r["metrics"].get("profit_pct", -1e9))
        out.append((day_start.strftime("%m-%d"), best["metrics"]["profit_pct"]))
    return out


def build_digest() -> dict:
    log = read_log()
    queue = read_queue()
    today_start, now = _today_utc_bounds()

    completed = [r for r in log if r.get("status") == "completed"]
    failed = [r for r in log if r.get("status") == "failed"]
    today_runs = [r for r in completed if _within(r.get("completed_at", ""), today_start, now)]
    today_failed = [r for r in failed if _within(r.get("completed_at", ""), today_start, now)]

    best_alltime = _best_n(completed, 3)
    best_today = _best_n(today_runs, 3)
    trend = _best_of_day_trend(completed, days=7)

    # Queue oldest
    queue_oldest = None
    if queue:
        try:
            sorted_q = sorted(queue, key=lambda r: r.get("created_at", ""))
            oldest_iso = sorted_q[0].get("created_at", "")
            oldest_ts = datetime.fromisoformat(oldest_iso)
            queue_oldest = f"{(now - oldest_ts).total_seconds() / 3600:.1f}h ago"
        except Exception:
            pass

    return {
        "today_count": len(today_runs),
        "today_failed": len(today_failed),
        "total_completed": len(completed),
        "queue_size": len(queue),
        "queue_oldest": queue_oldest,
        "best_alltime": best_alltime,
        "best_today": best_today,
        "trend": trend,
    }


def send_digest() -> bool:
    d = build_digest()

    fields = {
        "Today":           f"{d['today_count']} completed · {d['today_failed']} failed",
        "All-time":        f"{d['total_completed']} completed",
        "Queue":           f"{d['queue_size']} pending"
                           + (f" (oldest {d['queue_oldest']})" if d['queue_oldest'] else ""),
    }

    # Best-of-day trend line (last 7 days)
    trend_str = " · ".join(
        f"{day}: {p:+.2f}%" if p is not None else f"{day}: —"
        for day, p in d["trend"]
    )

    # Top results blocks
    lines = []
    if d["best_today"]:
        lines.append("🏆 <b>Best today:</b>")
        for r in d["best_today"]:
            lines.append("  " + _fmt_result(r))
    else:
        lines.append("🏆 <b>Best today:</b> — no results yet")

    lines.append("")
    lines.append("📊 <b>Best all-time:</b>")
    for r in d["best_alltime"]:
        lines.append("  " + _fmt_result(r))

    lines.append("")
    lines.append("📈 <b>Best-of-day trend (last 7d):</b>")
    lines.append("  " + trend_str)

    context = "\n".join(lines)

    return send(
        subsystem=Subsystem.BRAIN_CYCLE,
        status=Status.INFO,
        title=f"daily digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        fields=fields,
        html_context=context,   # context contains <b> and <code> HTML — must not be escaped
    )


if __name__ == "__main__":
    ok = send_digest()
    if ok:
        print("Digest sent.")
    else:
        print("Digest send failed (telegram).")
        sys.exit(1)
