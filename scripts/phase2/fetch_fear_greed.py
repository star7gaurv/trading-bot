#!/usr/bin/env python3
"""
FinBuddy Phase 2 — Fear & Greed Index Fetcher
Source: Alternative.me (free, no API key needed)
Output: dict with value (0-100), classification, and 7-day trend

Fear & Greed values:
  0-25   = Extreme Fear  (historically good BUY zone)
  25-45  = Fear
  45-55  = Neutral
  55-75  = Greed
  75-100 = Extreme Greed (historically good SELL/CAUTION zone)
"""

import requests
from datetime import datetime

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=7&format=json"
TIMEOUT = 8


def fetch_fear_greed() -> dict:
    """
    Fetch current + 7-day Fear & Greed data.
    Returns normalized dict ready to inject into FreqAI features.
    """
    try:
        resp = requests.get(FEAR_GREED_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()["data"]

        current = data[0]
        value = int(current["value"])
        classification = current["value_classification"]

        # 7-day trend: positive = greed growing, negative = fear growing
        values_7d = [int(d["value"]) for d in data]
        trend_7d = values_7d[0] - values_7d[-1]  # today minus 7 days ago

        # Normalize 0-100 to 0.0-1.0 for ML features
        normalized = value / 100.0

        # Regime signal: -1 (extreme fear) to +1 (extreme greed)
        if value <= 25:
            regime_signal = -1.0
        elif value <= 45:
            regime_signal = -0.5
        elif value <= 55:
            regime_signal = 0.0
        elif value <= 75:
            regime_signal = 0.5
        else:
            regime_signal = 1.0

        return {
            "source": "fear_greed",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": True,
            "value": value,
            "classification": classification,
            "normalized": normalized,
            "regime_signal": regime_signal,
            "trend_7d": trend_7d,
            "history_7d": values_7d,
            # Ready-to-use feature columns for FreqAI
            "features": {
                "ext_fear_greed": normalized,
                "ext_fear_greed_regime": regime_signal,
                "ext_fear_greed_trend_7d": trend_7d / 100.0,
            }
        }

    except Exception as e:
        return {
            "source": "fear_greed",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": False,
            "error": str(e),
            "features": {
                "ext_fear_greed": 0.5,          # neutral fallback
                "ext_fear_greed_regime": 0.0,
                "ext_fear_greed_trend_7d": 0.0,
            }
        }


if __name__ == "__main__":
    import json
    result = fetch_fear_greed()
    print(json.dumps(result, indent=2))
    if result["ok"]:
        print(f"\nCurrent: {result['value']} — {result['classification']}")
        print(f"7-day trend: {'+' if result['trend_7d'] >= 0 else ''}{result['trend_7d']} points")
