#!/usr/bin/env python3
"""
Karpathy backtest runner — validates current strategy on a short OOS window.

Runs `freqtrade backtesting` inside the live container (docker exec) on a
3-pair, 3-month window.  Fast (~2 min), no extra container, uses cached data.

Updates the strategy registry:
  - Hypothesis ideas that require code changes → "needs_implementation"
  - Current strategy validation → stored under key "latest_backtest"
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT     = Path("/home/ubuntu/var/www/html/trade")
REGISTRY = ROOT / "strategies/registry.json"
LOG_DIR  = Path("/home/ubuntu/.finbuddy/logs")

# Short window to keep nightly run fast — 3 liquid pairs, last 3 months
PAIRS     = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
TIMERANGE = "20260301-20260515"
CONTAINER = "freqtrade"

# Acceptance thresholds (same as walk-forward)
MIN_WR     = 0.50
MAX_DD     = 0.20
MIN_PF     = 1.20
MIN_SHARPE = 0.50


def _load_registry() -> dict:
    try:
        with open(REGISTRY) as f:
            return json.load(f)
    except Exception:
        return {"strategies": []}


def _save_registry(reg: dict) -> None:
    with open(REGISTRY, "w") as f:
        json.dump(reg, f, indent=2)


def _run_backtest() -> dict | None:
    """Run freqtrade backtesting via docker exec, return parsed results or None."""
    pairs_flag = " ".join(f'"{p}"' for p in PAIRS)
    cmd = [
        "docker", "exec", CONTAINER,
        "freqtrade", "backtesting",
        "--strategy", "CortexaAI_v23",
        "--timerange", TIMERANGE,
        "--pairs", *PAIRS,
        "--export", "none",
        "--config", "/freqtrade/user_data/config.json",
        "--logfile", "/dev/null",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=900,  # 15-min ceiling
            cwd=str(ROOT),
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print("[backtest_runner] Timed out after 15 min — skipping this run")
        return None
    except Exception as e:
        print(f"[backtest_runner] docker exec failed: {e}")
        return None

    # Parse key metrics from freqtrade's summary table in stdout
    metrics = {}
    for line in output.splitlines():
        line = line.strip()
        if "Win/Loss/Draw" in line and "/" in line:
            # format: "| Win/Loss/Draw |      X/Y/Z |"
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                wld = parts[1].split("/")
                if len(wld) == 3:
                    try:
                        wins   = int(wld[0].strip())
                        losses = int(wld[1].strip())
                        total  = wins + losses + int(wld[2].strip())
                        metrics["win_rate"] = wins / total if total > 0 else 0
                        metrics["trades"]   = total
                    except (ValueError, ZeroDivisionError):
                        pass
        if "Profit factor" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                try:
                    metrics["profit_factor"] = float(parts[1].replace(",", "."))
                except ValueError:
                    pass
        if "Max/Avg. Drawdown" in line or "Max Drawdown" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                try:
                    dd_str = parts[1].replace("%", "").replace(",", ".").strip().split()[0]
                    metrics["max_drawdown"] = float(dd_str) / 100
                except ValueError:
                    pass
        if "Sharpe" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                try:
                    metrics["sharpe"] = float(parts[1].replace(",", "."))
                except ValueError:
                    pass

    if not metrics.get("trades"):
        print(f"[backtest_runner] Could not parse results. Output tail:\n{output[-500:]}")
        return None

    return metrics


def run_backtests(hypotheses=None) -> list:
    """
    Validate current strategy on a short OOS window.
    Mark parameter-only hypotheses as needing implementation (not auto-runnable).
    """
    registry = _load_registry()
    today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results  = []

    # Mark in_development hypotheses — they need manual strategy implementation
    pending = [s for s in registry.get("strategies", []) if s.get("status") == "in_development"]
    for s in pending:
        s["status"]       = "needs_implementation"
        s["reviewed_at"]  = today
        s["review_note"]  = (
            "Hypothesis queued for manual implementation. "
            "Auto-backtest validates current live config only."
        )
        print(f"PENDING IMPLEMENTATION: {s['strategy_id']}")
        results.append({"strategy_id": s["strategy_id"], "status": "needs_implementation"})

    # Run live backtest on current strategy
    print(f"[backtest_runner] Running backtest on {PAIRS} for {TIMERANGE}...")
    metrics = _run_backtest()

    if metrics:
        wr  = metrics.get("win_rate", 0)
        dd  = metrics.get("max_drawdown", 1)
        pf  = metrics.get("profit_factor", 0)
        shr = metrics.get("sharpe", -99)
        passed = wr >= MIN_WR and dd <= MAX_DD and pf >= MIN_PF and shr >= MIN_SHARPE

        verdict = {
            "run_date":      today,
            "timerange":     TIMERANGE,
            "pairs":         PAIRS,
            "trades":        metrics.get("trades"),
            "win_rate":      round(wr, 4),
            "max_drawdown":  round(dd, 4),
            "profit_factor": round(pf, 4),
            "sharpe":        round(shr, 4),
            "passed":        passed,
        }
        registry["latest_backtest"] = verdict

        status = "✅ PASS" if passed else "❌ FAIL"
        print(
            f"[backtest_runner] {status} — WR {wr*100:.1f}% | "
            f"DD {dd*100:.1f}% | PF {pf:.2f} | Sharpe {shr:.3f}"
        )
        results.append({"strategy_id": "current", "status": "pass" if passed else "fail", **verdict})
    else:
        print("[backtest_runner] Backtest did not produce parseable results — skipping registry update")

    _save_registry(registry)
    return results


if __name__ == "__main__":
    run_backtests()
