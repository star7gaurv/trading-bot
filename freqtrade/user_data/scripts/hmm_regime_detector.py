#!/usr/bin/env python3
"""
Simplified Regime Detector — classifies current BTC market regime using statistical rules.
Writes to: finbuddy_memory/regimes/current.json + current.md
"""
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
EXTERNAL = ROOT / "freqtrade/user_data/data/external"
REGIMES_DIR = ROOT / "finbuddy_memory/regimes"
REGIMES_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_JSON = REGIMES_DIR / "current.json"
CURRENT_MD   = REGIMES_DIR / "current.md"
HISTORY_MD   = REGIMES_DIR / "history.md"

def fetch_btc_price():
    """Fetch current BTC price from Binance."""
    import urllib.request
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return float(data.get("price", 0))
    except Exception as e:
        print(f"Warning: Could not fetch BTC price: {e}")
        return None

def load_combined_context():
    """Load the combined external context."""
    try:
        with open(EXTERNAL / "combined_context.json") as f:
            return json.load(f)
    except Exception:
        return {}

def classify_regime(ctx):
    """
    Classify regime based on simple statistical rules:
    - CRASH: FG < 25 AND BTC dominance drop > 5% OR market cap change < -5%
    - BEAR: FG < 45 AND market cap change < -1%
    - NEUTRAL: FG 45-55 OR market cap change between -1% and +1%
    - BULL: FG > 55 AND market cap change > +1%
    - EUPHORIA: FG > 70 AND market cap change > +3%
    """
    fg = ctx.get("fear_greed", 50)
    market_change = ctx.get("market_cap_change_24h_pct", 0)
    btc_dom = ctx.get("btc_dominance", 50)

    if fg < 25 and market_change < -5:
        return "CRASH", 0.95
    elif fg < 45 and market_change < -1:
        return "BEAR", 0.80
    elif 45 <= fg <= 55 or (-1 <= market_change <= 1):
        return "NEUTRAL", 0.70
    elif fg > 55 and market_change > 1:
        return "BULL", 0.85
    elif fg > 70 and market_change > 3:
        return "EUPHORIA", 0.90
    else:
        return "NEUTRAL", 0.50

def run():
    ctx = load_combined_context()
    regime, confidence = classify_regime(ctx)

    # Load previous regime from JSON if exists
    prev_regime = "UNKNOWN"
    try:
        with open(CURRENT_JSON) as f:
            prev_data = json.load(f)
            prev_regime = prev_data.get("regime", "UNKNOWN")
    except Exception:
        pass

    # Find "since" date (when current regime streak started)
    # For now, use current date
    since_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()

    result = {
        "regime": regime,
        "confidence": round(confidence, 4),
        "since": since_date,
        "updated": now,
        "previous_regime": prev_regime,
    }

    # Write JSON
    with open(CURRENT_JSON, "w") as f:
        json.dump(result, f, indent=2)

    # Write Markdown
    md = f"""---
regime: {regime}
confidence: {round(confidence, 4)}
since: {since_date}
updated: {now}
---
# Current Market Regime: {regime}

**Confidence:** {round(confidence * 100, 1)}%
**Active since:** {since_date}
**Previous regime:** {prev_regime}
**Last updated:** {now}

## Regime Reference
| Regime | Brain Behavior |
|---|---|
| CRASH | No new entries. Defensive only. |
| BEAR | Reduced position sizes. Higher confidence threshold. |
| NEUTRAL | Normal trading. Default sizing. |
| BULL | Normal trading. |
| EUPHORIA | Reduced entries. Take profits faster. |
"""
    with open(CURRENT_MD, "w") as f:
        f.write(md)

    # Append to history if regime changed
    if regime != prev_regime and prev_regime != "UNKNOWN":
        history_line = f"| {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | {prev_regime} → {regime} | Confidence: {round(confidence * 100, 1)}% |\n"
        if not HISTORY_MD.exists():
            HISTORY_MD.write_text("# Regime Change History\n| Date | Change | Note |\n|---|---|---|\n")
        with open(HISTORY_MD, "a") as f:
            f.write(history_line)
        print(f"REGIME CHANGE: {prev_regime} → {regime}")

    print(f"Regime: {regime} (confidence: {round(confidence * 100, 1)}%) since {since_date}")
    return result

if __name__ == "__main__":
    run()
