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

# E3 (2026-06-11): the live detector previously classified on SENTIMENT
# (fear/greed + market-cap change) while the backtest parquet classified on
# BTC PRICE ACTION — they routinely disagreed (2026-06-08: parquet CRASH vs
# live NEUTRAL → entry deadlock). Both now share scripts/regime_core.py.
sys.path.insert(0, str(ROOT / "scripts"))
from regime_core import classify_latest  # noqa: E402

BTC_4H_FEATHER = ROOT / "freqtrade/user_data/data/binance/futures/BTC_USDT_USDT-4h-futures.feather"


def classify_from_price_action():
    """Classify the current regime from local BTC 4h candles (same data and
    rules the historical parquet uses — live == backtest by construction).

    Candle freshness: download_data_daily.sh refreshes at 04:30 UTC, so the
    last candle can lag up to ~24h. The 30d/90d horizons these rules use make
    that lag immaterial (vs. the old sentiment rules' 24h horizon).
    """
    import pandas as pd
    df = pd.read_feather(BTC_4H_FEATHER)
    return classify_latest(df)


def run():
    regime, confidence = classify_from_price_action()

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

---
*← [[FINBUDDY_PROJECT_MEMORY]]*
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
