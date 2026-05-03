#!/usr/bin/env python3
"""Master Karpathy loop orchestrator — runs nightly at 02:00."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from research_agent import run_research
from reasoning_agent import run_reasoning
from backtest_runner import run_backtests
from promoter import run_promotion

if __name__ == "__main__":
    print("=== Karpathy Loop Start ===")
    research_text = run_research()
    hypotheses    = run_reasoning(research_text)
    results       = run_backtests(hypotheses)
    run_promotion(results)
    print("=== Karpathy Loop Complete ===")
