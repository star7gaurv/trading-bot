#!/usr/bin/env python3
"""Simplified backtest runner — queues backtests without running."""
import json
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
REGISTRY = ROOT / "strategies/registry.json"

def run_backtests(hypotheses=None):
    """Queue backtests (simplified — doesn't actually run)."""
    
    try:
        with open(REGISTRY) as f:
            registry = json.load(f)
    except Exception:
        registry = {"strategies": []}
    
    if hypotheses is None:
        hypotheses = [s for s in registry.get("strategies", []) if s.get("status") == "in_development"]
    
    results = []
    for spec in hypotheses:
        # Mark as queued instead of actually backtesting
        for s in registry["strategies"]:
            if s.get("strategy_id") == spec.get("strategy_id"):
                s["status"] = "backtest_queued"
                s["queued_at"] = "2026-05-03"
        
        result = {
            "strategy_id": spec["strategy_id"],
            "status": "queued",
            "note": "Actual backtest to be run on server"
        }
        results.append(result)
    
    with open(REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)
    
    print(f"Queued {len(results)} backtests")
    return results

if __name__ == "__main__":
    run_backtests()
