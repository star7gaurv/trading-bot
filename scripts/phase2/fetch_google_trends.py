#!/usr/bin/env python3
"""
FinBuddy Phase 2 — Google Trends Fetcher
Source: Google Trends via pytrends (unofficial, free)
Output: search interest for bitcoin, crypto, ethereum (0-100 normalized)

High search interest = retail FOMO = often a contrarian bearish signal
Low search interest  = market bottom phase = often a bullish setup

Note: pytrends is rate-limited by Google. Cache results, fetch max once/hour.
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

CACHE_FILE   = "/tmp/finbuddy_trends_cache.json"
CACHE_HOURS  = 4   # re-fetch only every 4 hours
TIMEOUT      = 15
KEYWORDS     = ["bitcoin", "crypto", "ethereum"]


def load_cache() -> dict | None:
    """Return cached trends data if fresh enough."""
    if not Path(CACHE_FILE).exists():
        return None
    try:
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        fetched = datetime.fromisoformat(cached.get("fetched_at", "").replace("Z", ""))
        if datetime.utcnow() - fetched < timedelta(hours=CACHE_HOURS):
            cached["from_cache"] = True
            return cached
    except Exception:
        pass
    return None


def fetch_google_trends() -> dict:
    """
    Fetch Google Trends interest for bitcoin/crypto keywords.
    Returns normalized dict ready to inject into FreqAI features.
    """
    cached = load_cache()
    if cached:
        return cached

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360, timeout=(TIMEOUT, TIMEOUT))
        pytrends.build_payload(KEYWORDS, timeframe="now 7-d", geo="")
        interest_df = pytrends.interest_over_time()

        if interest_df.empty:
            raise ValueError("Empty trends response")

        latest = interest_df.iloc[-1]
        btc_interest  = float(latest.get("bitcoin",  50))
        eth_interest  = float(latest.get("ethereum", 25))
        cry_interest  = float(latest.get("crypto",   30))

        # Average across keywords for a composite retail attention score
        avg_interest = (btc_interest + eth_interest + cry_interest) / 3.0

        # Contrarian signal: high interest = potential top (sell signal)
        # Normalize to 0-1, then invert for contrarian interpretation
        normalized    = avg_interest / 100.0
        contrarian    = 1.0 - normalized   # high search = bearish contrarian

        # 7-day trend (latest vs week ago)
        week_avg = float(interest_df.head(24)["bitcoin"].mean()) if "bitcoin" in interest_df else btc_interest
        trend_7d = btc_interest - week_avg

        result = {
            "source": "google_trends",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": True,
            "from_cache": False,
            "btc_interest": btc_interest,
            "eth_interest": eth_interest,
            "crypto_interest": cry_interest,
            "avg_interest": avg_interest,
            "trend_7d_btc": trend_7d,
            # Ready-to-use feature columns for FreqAI
            "features": {
                "ext_trends_btc": btc_interest / 100.0,
                "ext_trends_avg": normalized,
                "ext_trends_contrarian": contrarian,
                "ext_trends_7d_change": trend_7d / 100.0,
            }
        }

        # Save to cache
        with open(CACHE_FILE, "w") as f:
            json.dump(result, f)

        return result

    except ImportError:
        return {
            "source": "google_trends",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": False,
            "error": "pytrends not installed. Run: pip install pytrends",
            "features": {
                "ext_trends_btc": 0.5,
                "ext_trends_avg": 0.5,
                "ext_trends_contrarian": 0.5,
                "ext_trends_7d_change": 0.0,
            }
        }
    except Exception as e:
        return {
            "source": "google_trends",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": False,
            "error": str(e),
            "features": {
                "ext_trends_btc": 0.5,
                "ext_trends_avg": 0.5,
                "ext_trends_contrarian": 0.5,
                "ext_trends_7d_change": 0.0,
            }
        }


if __name__ == "__main__":
    result = fetch_google_trends()
    import json as _json
    print(_json.dumps(result, indent=2))
    if result["ok"]:
        print(f"\nBTC Interest  : {result['btc_interest']:.0f}/100")
        print(f"Avg Interest  : {result['avg_interest']:.0f}/100")
        print(f"Contrarian    : {result['features']['ext_trends_contrarian']:.2f} (1.0 = no retail FOMO)")
