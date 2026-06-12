#!/usr/bin/env python3
"""
data_sentinel.py — silent-failure detector (added 2026-06-12).

Born from one audit pattern repeated four times: the per-pair funding cron dead
for a week, the analyst crashing for 4 days, the IC monitor reading a frozen
orphan file, the emergency shield inert since shipping. Nothing crashed loudly;
components just quietly stopped mattering.

Every 6h, for each feed/component, asks three questions:
  1. FRESH?        (file mtime / last data timestamp within budget)
  2. NON-CONSTANT? (recent values actually vary — not all-zero/frozen)
  3. ALIVE?        (cron logs advancing; queue schema intact; no fresh tracebacks)

Telegram WARN only on violations (silent OK otherwise). Exit 0 = all green.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
LOGS = Path("/home/ubuntu/.finbuddy/logs")
sys.path.insert(0, str(ROOT / "scripts"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402

NOW = time.time()
problems: list[str] = []


def _age_h(path: Path) -> float | None:
    try:
        return (NOW - path.stat().st_mtime) / 3600
    except FileNotFoundError:
        return None


def check_fresh(label: str, path: Path, max_age_h: float) -> None:
    age = _age_h(path)
    if age is None:
        problems.append(f"{label}: MISSING ({path.name})")
    elif age > max_age_h:
        problems.append(f"{label}: stale {age:.1f}h (budget {max_age_h:.0f}h)")


def check_parquet_data_fresh(label: str, path: Path, date_col: str, max_age_h: float) -> None:
    """Freshness by the DATA's last timestamp, not file mtime (a cron can
    rewrite a file daily while appending nothing — the funding bug pattern)."""
    try:
        import pandas as pd
        if path.suffix == ".feather":
            df = pd.read_feather(path, columns=[date_col])
        else:
            df = pd.read_parquet(path, columns=[date_col])
        last = pd.to_datetime(df[date_col], utc=True).max()
        age = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if age > max_age_h:
            problems.append(f"{label}: last data point {age:.0f}h old (budget {max_age_h:.0f}h)")
    except FileNotFoundError:
        problems.append(f"{label}: MISSING ({path.name})")
    except Exception as e:
        problems.append(f"{label}: unreadable ({e})")


def check_predictions() -> None:
    """Live predictions: in the IDENTIFIER subdir, fresh, and non-constant."""
    env = ROOT / "freqtrade/.env"
    ident = None
    for line in env.read_text().splitlines():
        if line.startswith("FREQTRADE__FREQAI__IDENTIFIER="):
            ident = line.split("=", 1)[1].strip()
    if not ident:
        problems.append("predictions: no identifier in .env")
        return
    pkl = ROOT / f"freqtrade/user_data/models/{ident}/historic_predictions.pkl"
    age = _age_h(pkl)
    if age is None:
        problems.append(f"predictions: pkl missing for identifier {ident}")
        return
    if age > 12:
        problems.append(f"predictions: pkl {age:.1f}h old (live bot saves on retrain; budget 12h)")
        return
    try:
        import pickle
        import pandas as pd
        hp = pickle.load(open(pkl, "rb"))
        df = next(iter(hp.values())).sort_values("date_pred").tail(96)
        pred = pd.to_numeric(df["&-future_return"], errors="coerce")
        if pred.std() is not None and pred.std() < 0.01:
            problems.append(f"predictions: last-24h std={pred.std():.4f} — near-constant (model degenerate?)")
        dp = pd.to_numeric(df["do_predict"], errors="coerce")
        if dp.eq(1).mean() < 0.2:
            problems.append(f"predictions: do_predict=1 on only {dp.eq(1).mean():.0%} of last 24h")
    except Exception as e:
        problems.append(f"predictions: pkl unreadable ({e})")


def check_cron_logs() -> None:
    budgets = {  # log name -> max hours since last write
        "data_fetcher.log": 1, "trade_postmortem.log": 1, "watchdog.log": 1.5,
        "brain_run.log": 3, "hmm_regime.log": 5, "memory_writer.log": 1,
        "pair_regime.log": 1.5, "funding_farm.log": 2,
        "daily_summary.log": 26, "download_data_daily.log": 26,
        "historical_funding.log": 30, "historical_funding_perpair.log": 30,
        "historical_oi.log": 30, "historical_macro.log": 30,
        "historical_regime.log": 30, "brain_gen.log": 8, "brain_analyst.log": 8,
        "llm_hypothesis.log": 26,
    }
    for name, budget in budgets.items():
        age = _age_h(LOGS / name)
        if age is None:
            problems.append(f"cron {name}: log MISSING")
        elif age > budget:
            problems.append(f"cron {name}: silent for {age:.1f}h (budget {budget}h)")


def check_tracebacks() -> None:
    """Fresh tracebacks in brain logs = a component is crash-looping."""
    for name in ("brain_analyst.log", "brain_gen.log", "brain_scan.log", "llm_hypothesis.log"):
        p = LOGS / name
        if not p.exists() or _age_h(p) > 8:
            continue
        tail = "\n".join(p.read_text(errors="replace").splitlines()[-30:])
        if "Traceback (most recent call last)" in tail:
            err = re.findall(r"\n(\w+Error.*)", tail)
            problems.append(f"{name}: crash in last run — {err[-1][:90] if err else 'see log'}")


def check_queue_schema() -> None:
    qf = ROOT / "finbuddy_memory/experiments/queue.jsonl"
    bad = 0
    total = 0
    for line in qf.read_text().splitlines():
        if not line.strip():
            continue
        total += 1
        e = json.loads(line)
        if not e.get("hypothesis_id") or e.get("status") != "queued":
            bad += 1
    if bad:
        problems.append(f"queue: {bad}/{total} entries schema-broken (picker-invisible / analyst-crashing)")
    if total == 0:
        problems.append("queue: EMPTY — brain has nothing to do")


def check_container() -> None:
    try:
        r = subprocess.run(["docker", "inspect", "freqtrade", "--format", "{{.State.Status}}"],
                           capture_output=True, text=True, timeout=15)
        if r.stdout.strip() != "running":
            problems.append(f"freqtrade container: {r.stdout.strip() or r.stderr[:80]}")
    except Exception as e:
        problems.append(f"freqtrade container: docker inspect failed ({e})")


def main() -> int:
    H = ROOT / "finbuddy_memory/historical"
    check_fresh("combined_context", ROOT / "freqtrade/user_data/data/external/combined_context.json", 1)
    check_fresh("regime current.json", ROOT / "finbuddy_memory/regimes/current.json", 5)
    check_fresh("recent_wr.json", Path("/home/ubuntu/.finbuddy/state/recent_wr.json"), 1)
    check_parquet_data_fresh("funding_rate(BTC)", H / "funding_rate.parquet", "date", 36)
    check_parquet_data_fresh("funding_perpair", H / "funding_perpair.parquet", "date", 36)
    # OI sources come from Binance Data Vision daily ZIPs which publish with a
    # 1-2 day lag — 60h budget, not 36h.
    check_parquet_data_fresh("open_interest(BTC)", H / "open_interest.parquet", "date", 60)
    check_parquet_data_fresh("oi_perpair", H / "oi_perpair.parquet", "date", 60)
    check_parquet_data_fresh("macro_features", H / "macro_features.parquet", "date", 36)
    check_parquet_data_fresh("historical_regime", ROOT / "finbuddy_memory/regimes/historical_regime.parquet", "date", 36)
    check_parquet_data_fresh("BTC 15m feather", ROOT / "freqtrade/user_data/data/binance/futures/BTC_USDT_USDT-15m-futures.feather", "date", 30)
    check_predictions()
    check_cron_logs()
    check_tracebacks()
    check_queue_schema()
    check_container()

    if problems:
        body = "\n".join(f"• {p}" for p in problems[:12])
        send(Subsystem.WATCHDOG, Status.WARN,
             f"Data sentinel: {len(problems)} silent failure(s)",
             html_context=body,
             context="A component is stale, constant, or crash-looping — "
                     "the brain may be learning from dead data.",
             silent=False)
        print(f"[sentinel] {len(problems)} problems:")
        for p in problems:
            print("  -", p)
        return 1
    print("[sentinel] all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
