#!/usr/bin/env python3
"""Research agent — generates nightly market analysis note.
Uses the central llm_client for AI analysis (task="research").
Falls back to rule-based analysis when no LLM providers are available.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT  = Path("/home/ubuntu/var/www/html/trade")
VAULT = ROOT / "finbuddy_memory"

# Import central LLM client (one directory up from karpathy/)
sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import call_llm, available_providers


def _rule_based_analysis(ctx: dict, regime: dict) -> str:
    """Context-driven analysis without an LLM — meaningful even without AI credits."""
    fg         = ctx.get("fear_greed", 50)
    btc_dom    = ctx.get("btc_dominance", 50)
    mkt_change = ctx.get("market_cap_change_24h_pct", 0)
    current    = regime.get("regime", "NEUTRAL")
    conf       = round(regime.get("confidence", 0.5) * 100, 1)

    lines = []
    if current == "CRASH":
        lines.append("🔴 CRASH regime — avoid longs, prefer shorts or cash.")
    elif current == "BEAR":
        lines.append("🟠 BEAR regime — short bias. ML model should prefer S labels.")
    elif current == "BULL":
        lines.append("🟢 BULL regime — long bias. Regime multiplier increases stake.")
    elif current == "EUPHORIA":
        lines.append("🚀 EUPHORIA — shorts blocked by kill-switch. Watch for reversal signals.")
    else:
        lines.append(f"⚪ NEUTRAL regime (confidence {conf}%) — symmetric L/S expected.")

    if fg < 25:
        lines.append(f"Extreme Fear (FG={fg}) — historically a contrarian long signal.")
    elif fg < 40:
        lines.append(f"Fear zone (FG={fg}) — exit signals may trigger early.")
    elif fg > 75:
        lines.append(f"Greed zone (FG={fg}) — potential short-entry area for mean-reversion.")
    else:
        lines.append(f"Fear & Greed neutral at {fg} — no contrarian bias.")

    if btc_dom > 58:
        lines.append(f"BTC dominance elevated ({btc_dom}%) — alt-pair win rates may dip.")
    elif btc_dom < 48:
        lines.append(f"BTC dominance low ({btc_dom}%) — alt-season conditions, alt signals improve.")

    if abs(mkt_change) > 3:
        direction = "rallying" if mkt_change > 0 else "selling off"
        lines.append(f"Market {direction} hard ({mkt_change:+.1f}% 24h) — ATR-based stops may widen.")

    hypotheses = []
    if fg < 35 and current in ("BEAR", "NEUTRAL"):
        hypotheses.append("**Capitulation bounce** — extreme fear + BEAR/NEUTRAL → test small longs on 15m RSI<25 with 1×ATR stop.")
    if btc_dom > 57:
        hypotheses.append("**Alt threshold raise** — high BTC dom → raise ml_threshold to 0.65 on alt pairs to filter noise.")
    if abs(mkt_change) < 1 and current == "NEUTRAL":
        hypotheses.append("**Low-vol time limit** — flat market + NEUTRAL → tighter time_limit (4 candles) to capture chop profit.")
    if not hypotheses:
        hypotheses.append("**Threshold sensitivity** — OOS backtest comparing ml_threshold 0.55 vs 0.65 on current regime window.")

    obs = "\n".join(f"- {l}" for l in lines)
    hyp = "\n".join(f"{i+1}. {h}" for i, h in enumerate(hypotheses))
    return f"## Observations\n{obs}\n\n## Hypotheses to Test\n{hyp}"


def run_research() -> str:
    try:
        with open(ROOT / "freqtrade/user_data/data/external/combined_context.json") as f:
            ctx = json.load(f)
    except Exception:
        ctx = {}

    try:
        with open(VAULT / "regimes/current.json") as f:
            regime = json.load(f)
    except Exception:
        regime = {"regime": "NEUTRAL", "confidence": 0.5}

    fg         = ctx.get("fear_greed", 50)
    btc_dom    = ctx.get("btc_dominance", 50)
    mkt_change = ctx.get("market_cap_change_24h_pct", 0)
    tvl        = ctx.get("defi_tvl_usd", 0)
    news_bull  = ctx.get("news_bullish", 0)
    news_bear  = ctx.get("news_bearish", 0)
    gtrends    = ctx.get("google_trends_bitcoin", 50)
    current_regime = regime.get("regime", "NEUTRAL")
    regime_conf    = round(regime.get("confidence", 0.5) * 100, 1)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    snapshot = (
        f"Date: {date_str}\n"
        f"Fear & Greed: {fg}\n"
        f"BTC Dominance: {btc_dom}%\n"
        f"Market 24h: {mkt_change:+.2f}%\n"
        f"DeFi TVL: ${tvl:,.0f}\n"
        f"News: {news_bull} bullish / {news_bear} bearish\n"
        f"Google Trends: {gtrends}\n"
        f"Regime: {current_regime} ({regime_conf}%)"
    )

    system_prompt = (
        "You are FinBuddy's research analyst for a 25-pair crypto futures bot "
        "(FreqAI LightGBM, 1h TF, long+short). "
        "Analyse the market snapshot and produce a nightly research note: "
        "key observations, regime interpretation, 2-3 concrete testable hypotheses, risk notes. "
        "Max 350 words."
    )

    providers = available_providers()
    analysis = call_llm(snapshot, system=system_prompt, task="research", max_tokens=600)
    if analysis:
        provider_list = ", ".join(providers) if providers else "unknown"
        source = f"AI ({provider_list})"
    else:
        analysis = _rule_based_analysis(ctx, regime)
        source = "rule-based fallback (configure GEMINI_API_KEY / DEEPSEEK_API_KEY for AI analysis)"

    research_text = f"""# Nightly Research — {date_str}

## Market Snapshot
{snapshot}

## Analysis ({source})
{analysis}

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[research/README]]*
"""

    out_file = VAULT / f"research/{date_str}-nightly.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(research_text)
    print(f"Research note written: {out_file} [source: {source}]")
    return research_text


if __name__ == "__main__":
    run_research()
