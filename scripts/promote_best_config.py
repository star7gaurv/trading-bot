#!/usr/bin/env python3
"""
promote_best_config.py — pick best bull-grid config, walk-forward, promote.

Pipeline:
  1. Read _autobacktest_results.csv, filter for healthy configs.
  2. Run a single walk-forward backtest on the OOS window for the chosen config.
  3. Write JSON + markdown report; if walk-forward passes, promote params as
     BEST_BULL_2024 preset on FinBuddyFreqAI.

Exits 0 if results not yet ready (cron-safe).
"""
import csv
import json
import re
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/home/ubuntu/var/www/html/trade")
CSV_PATH     = PROJECT_ROOT / "_autobacktest_results.csv"
RESEARCH_DIR = PROJECT_ROOT / "finbuddy_memory" / "research"
BEST_JSON    = RESEARCH_DIR / "best_bull_2024_config.json"
WF_JSON      = RESEARCH_DIR / "best_bull_2024_walkforward.json"
WF_MD        = RESEARCH_DIR / "best_bull_2024_walkforward.md"
STRAT_PATH   = PROJECT_ROOT / "freqtrade/user_data/strategies/FinBuddyFreqAI.py"

WF_TIMERANGE = os.environ.get("WALKFORWARD_TIMERANGE", "20250101-20260401")

# Same thresholds applied to in-sample selection AND walk-forward verdict
THRESHOLDS = {
    "trades":        40,
    "sharpe":        0.0,
    "max_drawdown":  0.25,
    "profit_factor": 1.1,
}
PROMOTE_THRESHOLDS = {
    "trades":        30,
    "sharpe":        0.5,
    "max_drawdown":  0.20,
    "profit_factor": 1.2,
}

PARAM_KEYS = ["ml_threshold", "stoploss", "trailing_offset",
              "ml_exit_threshold", "atr_threshold"]


def _f(v):
    try: return float(v) if v not in ("", None) else None
    except ValueError: return None


def grid_finished() -> bool:
    """True iff CSV has data rows AND the autobacktest process is no longer running."""
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size < 200:
        return False
    proc = subprocess.run(["pgrep", "-f", "scripts/autobacktest.py"],
                          capture_output=True, text=True)
    return proc.returncode != 0


def load_rows():
    with CSV_PATH.open() as f:
        return [r for r in csv.DictReader(f) if _f(r.get("sharpe")) is not None]


def select_best(rows):
    """Filter healthy configs; fallback to highest Sharpe with trades >= 30."""
    healthy = []
    for r in rows:
        t  = _f(r["trades"]) or 0
        sh = _f(r["sharpe"]) or -1
        dd = _f(r["max_drawdown"])
        pf = _f(r["profit_factor"]) or 0
        dd_abs = abs(dd) if dd is not None else 1
        if (t >= THRESHOLDS["trades"] and sh > THRESHOLDS["sharpe"]
                and dd_abs < THRESHOLDS["max_drawdown"]
                and pf > THRESHOLDS["profit_factor"]):
            healthy.append(r)
    if healthy:
        healthy.sort(key=lambda r: _f(r["sharpe"]), reverse=True)
        return healthy[0], "primary"
    fallback = [r for r in rows if (_f(r["trades"]) or 0) >= 30 and (_f(r["sharpe"]) or -1) > 0]
    if not fallback:
        print("NO PROMOTABLE CONFIG — all combos negative Sharpe")
        return None, "none"
    fallback.sort(key=lambda r: _f(r["sharpe"]) or -1e9, reverse=True)
    return fallback[0], "fallback"


def run_walkforward(params: dict) -> dict:
    """Reuse autobacktest helpers to run one backtest on WF_TIMERANGE."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    os.environ["BACKTEST_TIMERANGE"] = WF_TIMERANGE
    import importlib
    autobacktest = importlib.import_module("autobacktest")
    importlib.reload(autobacktest)
    autobacktest.write_patched_config(params)
    temp_path = autobacktest.write_patched_strategy(STRAT_PATH, params)
    return autobacktest.run_backtest(
        {
            "parse_script": "scripts/parse_backtest.py",
            "backtest_results_path": "freqtrade/user_data/backtest_results",
        },
        temp_path,
    )


def passes(metrics: dict) -> bool:
    t  = metrics.get("trades") or 0
    sh = metrics.get("sharpe") or -1
    dd = metrics.get("max_drawdown")
    pf = metrics.get("profit_factor") or 0
    dd_abs = abs(dd) if dd is not None else 1
    return (t >= PROMOTE_THRESHOLDS["trades"]
            and sh > PROMOTE_THRESHOLDS["sharpe"]
            and dd_abs < PROMOTE_THRESHOLDS["max_drawdown"]
            and pf > PROMOTE_THRESHOLDS["profit_factor"])


def promote_preset(params: dict) -> bool:
    """Inject/replace BEST_BULL_2024 preset block at top of class body."""
    text = STRAT_PATH.read_text()
    block = (
        "    # BEST_BULL_2024 — auto-promoted from bull walk-forward\n"
        "    BEST_BULL_2024 = " + json.dumps(params, sort_keys=True) + "\n"
    )
    pattern = r"    # BEST_BULL_2024 — auto-promoted.*?\n    BEST_BULL_2024 = \{[^}]*\}\n"
    if re.search(pattern, text, re.DOTALL):
        new = re.sub(pattern, block, text, count=1, flags=re.DOTALL)
    else:
        new = re.sub(
            r"(class FinBuddyFreqAI\(IStrategy\):\n(?:    \"\"\".*?\"\"\"\n)?)",
            r"\1" + block,
            text, count=1, flags=re.DOTALL,
        )
    if new == text:
        return False
    STRAT_PATH.write_text(new)
    return True


def write_report(chosen, mode, wf, verdict):
    params = {k: chosen.get(k) for k in PARAM_KEYS}
    md = [
        "# Best Bull 2024 — Walk-Forward Report",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        f"**Selection mode:** {mode}",
        "",
        "## Chosen params",
        "```json",
        json.dumps(params, indent=2),
        "```",
        "",
        "## In-sample (bull 2024 grid row)",
        f"- trades: {chosen.get('trades')}",
        f"- win_rate: {chosen.get('win_rate')}",
        f"- sharpe: {chosen.get('sharpe')}",
        f"- max_drawdown: {chosen.get('max_drawdown')}",
        f"- profit_factor: {chosen.get('profit_factor')}",
        f"- total_profit: {chosen.get('total_profit')}",
        "",
        f"## Out-of-sample walk-forward ({WF_TIMERANGE})",
        f"- trades: {wf.get('trades')}",
        f"- win_rate: {wf.get('win_rate')}",
        f"- sharpe: {wf.get('sharpe')}",
        f"- max_drawdown: {wf.get('max_drawdown')}",
        f"- profit_factor: {wf.get('profit_factor')}",
        f"- total_profit: {wf.get('total_profit')}",
        f"- error: {wf.get('error')}",
        "",
        f"## Verdict: **{verdict}**",
    ]
    WF_MD.write_text("\n".join(md) + "\n")


def main():
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    if not grid_finished():
        print("[promote] grid not ready or still running; exit 0")
        return 0

    rows = load_rows()
    if not rows:
        print("[promote] no parseable rows in CSV; exit 0")
        return 0

    chosen, mode = select_best(rows)
    if chosen is None:
        print("[promote] no eligible configs even in fallback; exit 0")
        return 0

    params = {k: _f(chosen.get(k)) for k in PARAM_KEYS}
    BEST_JSON.write_text(json.dumps(
        {"mode": mode, "row": chosen, "params": params}, indent=2))
    print(f"[promote] chosen ({mode}): {params}")

    wf = run_walkforward(params)
    WF_JSON.write_text(json.dumps(wf, default=str, indent=2))

    verdict = "PROMOTE" if passes(wf) else "DO NOT PROMOTE"
    write_report(chosen, mode, wf, verdict)
    print(f"[promote] verdict: {verdict}")

    if verdict == "PROMOTE":
        if promote_preset(params):
            print("[promote] BEST_BULL_2024 preset written into strategy")
        else:
            print("[promote] preset injection no-op (already current)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
