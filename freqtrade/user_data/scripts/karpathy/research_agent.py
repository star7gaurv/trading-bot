#!/usr/bin/env python3
"""Simplified research agent — no Gemini API required."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT  = Path("/home/ubuntu/var/www/html/trade")
VAULT = ROOT / "finbuddy_memory"

def run_research():
    """Generate a simple research note from market data."""
    
    # Load context
    try:
        with open(ROOT / "freqtrade/user_data/data/external/combined_context.json") as f:
            ctx = json.load(f)
    except Exception:
        ctx = {}
    
    try:
        with open(VAULT / "regimes/current.json") as f:
            regime = json.load(f)
    except Exception:
        regime = {"regime": "NEUTRAL"}
    
    fg = ctx.get("fear_greed", 50)
    btc_dom = ctx.get("btc_dominance", 50)
    market_change = ctx.get("market_cap_change_24h_pct", 0)
    
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Simple rule-based analysis
    observations = []
    if fg < 35:
        observations.append("- Fear level extremely high (FG < 35) — potential capitulation")
    elif fg < 50:
        observations.append(f"- Fear & Greed at {fg} (FEAR zone)")
    elif fg > 70:
        observations.append(f"- Fear & Greed at {fg} (GREED zone)")
    else:
        observations.append(f"- Fear & Greed neutral at {fg}")
    
    if btc_dom > 55:
        observations.append(f"- BTC dominance high at {btc_dom}% — alts weakening")
    elif btc_dom < 45:
        observations.append(f"- BTC dominance low at {btc_dom}% — alt season")
    
    if market_change > 5:
        observations.append(f"- Market rallying hard ({market_change}% 24h)")
    elif market_change < -5:
        observations.append(f"- Market in free fall ({market_change}% 24h)")
    
    research_text = f"""# Nightly Research — {date_str}

## Market Observations
{chr(10).join(observations)}

## Current Regime: {regime.get('regime', 'NEUTRAL')}
Confidence: {round(regime.get('confidence', 0) * 100, 1)}%

## Hypotheses to Test
1. **Mean-reversion on FG divergence** — If FG < 30 and price holds above 20-EMA on daily, enter small longs on 15m oversold.
2. **BTC dominance momentum** — If BTC dom closes above 20-day SMA, reduce alts; increase BTC weight.
3. **Volatility regime filter** — Entry only when ATR(20) < 50th percentile to avoid breakeven traps in high-vol chop.

## Risk Notes
- Recent backtests (v10 OOS) failed due to path-blindness. Prioritize triple-barrier labeling over mean-reversion.
- Stop-hunting is heavy in tight ranges. Use 2×ATR minimum or pass.
"""
    
    out_file = VAULT / f"research/{date_str}-nightly.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(research_text)
    print(f"Research note written: {out_file}")
    return research_text

if __name__ == "__main__":
    run_research()
