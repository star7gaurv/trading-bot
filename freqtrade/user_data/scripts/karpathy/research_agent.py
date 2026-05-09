#!/usr/bin/env python3
"""Research agent — calls Grok-3-Mini (XAI) to analyse market context.
Falls back to rule-based analysis when XAI has no credits or is unavailable.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT  = Path("/home/ubuntu/var/www/html/trade")
VAULT = ROOT / "finbuddy_memory"
XAI_API_URL = "https://api.x.ai/v1/chat/completions"


def _load_xai_key() -> str:
    key = os.environ.get("XAI_API_KEY", "")
    if key:
        return key
    try:
        for line in (ROOT / "freqtrade/.env").read_text().splitlines():
            if line.startswith("XAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def _call_grok(prompt: str, system: str = "", max_tokens: int = 800) -> str | None:
    """Returns LLM response text, or None on any failure (incl. no credits)."""
    key = _load_xai_key()
    if not key:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": "grok-3-mini",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        XAI_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"[research] XAI 403 — no credits on account. Using rule-based fallback. "
                  f"Add credits at https://console.x.ai to enable AI analysis.")
        else:
            print(f"[research] XAI HTTP {e.code}: {e}")
        return None
    except Exception as e:
        print(f"[research] XAI error: {e}")
        return None


def _rule_based_analysis(ctx: dict, regime: dict) -> str:
    """Generate varied, context-driven analysis without an LLM."""
    fg         = ctx.get("fear_greed", 50)
    btc_dom    = ctx.get("btc_dominance", 50)
    mkt_change = ctx.get("market_cap_change_24h_pct", 0)
    tvl        = ctx.get("defi_tvl_usd", 0)
    current    = regime.get("regime", "NEUTRAL")
    conf       = round(regime.get("confidence", 0.5) * 100, 1)

    lines = []

    # Regime interpretation
    if current == "CRASH":
        lines.append("🔴 CRASH regime — avoid longs, prefer shorts or cash. High false-positive rate on longs expected.")
    elif current == "BEAR":
        lines.append("🟠 BEAR regime — short bias. ML model should prefer S labels.")
    elif current == "BULL":
        lines.append("🟢 BULL regime — long bias. Regime multiplier increases stake.")
    elif current == "EUPHORIA":
        lines.append("🚀 EUPHORIA — shorts blocked by kill-switch. Watch for reversal signals.")
    else:
        lines.append(f"⚪ NEUTRAL regime (confidence {conf}%) — symmetric L/S expected.")

    # Fear & Greed signals
    if fg < 25:
        lines.append(f"Extreme Fear (FG={fg}) — historically a contrarian long signal. Confirm with price action before entering.")
    elif fg < 40:
        lines.append(f"Fear zone (FG={fg}) — market cautious. Exit signals may trigger early; watch for false exits.")
    elif fg > 75:
        lines.append(f"Greed zone (FG={fg}) — potential short-entry area for mean-reversion. Euphoria kill-switch active if FG>80.")
    else:
        lines.append(f"Fear & Greed neutral at {fg} — no contrarian bias.")

    # BTC dominance
    if btc_dom > 58:
        lines.append(f"BTC dominance elevated ({btc_dom}%) — altcoins underperforming. Expect lower win rates on alt-heavy pairs.")
    elif btc_dom < 48:
        lines.append(f"BTC dominance low ({btc_dom}%) — alt-season conditions. ML signal quality on alts may improve.")

    # Market cap movement
    if abs(mkt_change) > 3:
        direction = "rallying" if mkt_change > 0 else "selling off"
        lines.append(f"Market {direction} hard ({mkt_change:+.1f}% 24h) — increased volatility expected. ATR-based stops may widen.")

    # Hypothesis ideas based on context
    hypotheses = []
    if fg < 35 and current in ("BEAR", "NEUTRAL"):
        hypotheses.append("**Capitulation bounce** — FG extreme fear + BEAR/NEUTRAL regime → test small long entries on 15m RSI<25 with 1×ATR stop.")
    if btc_dom > 57:
        hypotheses.append("**Alt-pair threshold raise** — during high BTC dom, raise ml_threshold to 0.65 on alt pairs to filter noise.")
    if abs(mkt_change) < 1 and current == "NEUTRAL":
        hypotheses.append("**Low-vol range trade** — flat market + NEUTRAL → test tighter time_limit (4 candles) to capture chop profit.")
    if not hypotheses:
        hypotheses.append("**Threshold sensitivity test** — run OOS backtest comparing ml_threshold 0.55 vs 0.65 on current regime window.")

    obs_text = "\n".join(f"- {l}" for l in lines)
    hyp_text = "\n".join(f"{i+1}. {h}" for i, h in enumerate(hypotheses))

    return f"""## Observations
{obs_text}

## Hypotheses to Test
{hyp_text}

## Risk Notes
- Walk-forward OOS WR currently 30% (v11/v16 mixed run, under investigation). Do not migrate to live until WR>50% confirmed.
- Stop-loss exits are the primary P&L drain — do not raise position sizes until stop architecture improves.
- DeFi TVL data unavailable (API issue) — regime confidence may be lower than displayed."""


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

    fg          = ctx.get("fear_greed", 50)
    btc_dom     = ctx.get("btc_dominance", 50)
    mkt_change  = ctx.get("market_cap_change_24h_pct", 0)
    tvl         = ctx.get("defi_tvl_usd", 0)
    news_bull   = ctx.get("news_bullish", 0)
    news_bear   = ctx.get("news_bearish", 0)
    gtrends     = ctx.get("google_trends_bitcoin", 50)
    current_regime = regime.get("regime", "NEUTRAL")
    regime_conf    = round(regime.get("confidence", 0.5) * 100, 1)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    snapshot = (f"Date: {date_str}\nFear & Greed: {fg}\nBTC Dominance: {btc_dom}%\n"
                f"Market 24h: {mkt_change:+.2f}%\nDeFi TVL: ${tvl:,.0f}\n"
                f"News: {news_bull} bullish / {news_bear} bearish\n"
                f"Google Trends: {gtrends}\nRegime: {current_regime} ({regime_conf}%)")

    # Try LLM first; fall back to rules
    system_prompt = (
        "You are FinBuddy's research analyst for a 25-pair futures bot (FreqAI LightGBM, 1h TF). "
        "Analyse the market snapshot and produce a nightly research note: key observations, "
        "regime interpretation, 2-3 concrete testable hypotheses, risk notes. Max 350 words."
    )
    analysis = _call_grok(snapshot, system=system_prompt, max_tokens=600)
    source = "Grok-3-Mini"
    if analysis is None:
        analysis = _rule_based_analysis(ctx, regime)
        source = "rule-based fallback (add XAI credits for AI analysis)"

    research_text = f"""# Nightly Research — {date_str}

## Market Snapshot
{snapshot}

## Analysis ({source})
{analysis}
"""

    out_file = VAULT / f"research/{date_str}-nightly.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(research_text)
    print(f"Research note written: {out_file} [source: {source}]")
    return research_text


if __name__ == "__main__":
    run_research()
