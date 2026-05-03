#!/usr/bin/env python3
"""Simplified reasoning agent — no DeepSeek API required."""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
REGISTRY = ROOT / "strategies/registry.json"

def run_reasoning(research_text):
    """Generate strategy specs from research."""
    
    # Load or create registry
    try:
        with open(REGISTRY) as f:
            registry = json.load(f)
    except Exception:
        registry = {"strategies": []}
    
    # Simple rule-based strategy generation
    hypotheses = [
        {
            "strategy_id": "triple_barrier_mean_reversion_v1",
            "hypothesis": "Use López de Prado triple-barrier labels with asymmetric TP/SL to catch oversold bounces",
            "timeframe": "15m",
            "indicators": ["ATR_14", "RSI_14", "EMA_50"],
            "entry_long": "RSI < 40 AND close > EMA50 AND triple_barrier_label_proba > 0.55",
            "entry_short": "RSI > 60 AND close < EMA50 AND macro_regime != BULL",
            "exit_rule": "triple_barrier hit or time barrier (12 candles)",
            "regime_filter": ["BULL", "NEUTRAL"],
            "proposed_by": "reasoning_agent"
        },
        {
            "strategy_id": "btc_dominance_momentum_v1",
            "hypothesis": "When BTC dominance breaks 20d SMA upside, rotate from alts into BTC; hedge alts with tight stops",
            "timeframe": "15m",
            "indicators": ["BTC_DOM_20_SMA", "ATR_14"],
            "entry_long": "BTC_DOM > BTC_DOM_20_SMA AND market_cap_change_24h > 1%",
            "entry_short": "BTC_DOM break below 20d AND fear_greed < 40",
            "exit_rule": "opposite SMA break or 2×ATR stop",
            "regime_filter": ["NEUTRAL", "BULL"],
            "proposed_by": "reasoning_agent"
        }
    ]
    
    # Add to registry
    for h in hypotheses:
        h["status"] = "in_development"
        h["proposed_at"] = datetime.utcnow().strftime("%Y-%m-%d")
        registry["strategies"].append(h)
    
    with open(REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)
    
    print(f"Added {len(hypotheses)} hypotheses to registry")
    return hypotheses

if __name__ == "__main__":
    run_reasoning("")
