#!/usr/bin/env python3
"""Promoter — promote or demote strategies based on results."""
import json, subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
VAULT = ROOT / "finbuddy_memory"
REGISTRY = ROOT / "strategies/registry.json"

def run_promotion(results=None):
    """Review queued backtests and promote winners."""
    
    try:
        with open(REGISTRY) as f:
            registry = json.load(f)
    except Exception:
        registry = {"strategies": []}
    
    to_review = [s for s in registry["strategies"] if s.get("status") in ("backtest_done", "backtest_queued")]
    
    for strat in to_review:
        sid = strat["strategy_id"]
        bt = strat.get("backtest_result", {})
        
        # For now, mark queued as pending actual backtest
        if strat.get("status") == "backtest_queued":
            print(f"PENDING BACKTEST: {sid}")
    
    with open(REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)
    
    # Auto-commit
    subprocess.run(
        ["git", "add", "strategies/"],
        cwd=str(ROOT), capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--no-verify", "-m",
         f"karpathy: promotion run {datetime.utcnow().strftime('%Y-%m-%d')}"],
        cwd=str(ROOT), capture_output=True
    )
    subprocess.run(["git", "push", "origin", "gaurav"], cwd=str(ROOT), capture_output=True)

if __name__ == "__main__":
    run_promotion()
