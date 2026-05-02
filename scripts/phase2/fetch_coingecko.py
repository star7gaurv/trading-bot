#!/usr/bin/env python3
"""
FinBuddy Phase 2 — CoinGecko Market Data Fetcher
Source: CoinGecko free API (no key needed, rate limit: 10-30 req/min)
Output: BTC dominance, global market cap, 24h change, trending coins
"""

import requests
from datetime import datetime

GLOBAL_URL  = "https://api.coingecko.com/api/v3/global"
TREND_URL   = "https://api.coingecko.com/api/v3/search/trending"
BTC_URL     = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true&include_market_cap=true"
TIMEOUT = 10


def fetch_coingecko() -> dict:
    """
    Fetch global market stats + trending coins.
    Returns normalized dict ready to inject into FreqAI features.
    """
    try:
        # --- Global market data ---
        resp = requests.get(GLOBAL_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        gdata = resp.json()["data"]

        btc_dominance    = gdata.get("market_cap_percentage", {}).get("btc", 50.0)
        eth_dominance    = gdata.get("market_cap_percentage", {}).get("eth", 15.0)
        total_mcap_usd   = gdata.get("total_market_cap", {}).get("usd", 0)
        mcap_change_24h  = gdata.get("market_cap_change_percentage_24h_usd", 0.0)
        active_coins     = gdata.get("active_cryptocurrencies", 0)
        defi_volume_24h  = gdata.get("total_volume", {}).get("usd", 0)

        # Normalize BTC dominance (historically 38-72%): 0.0 = altcoin season, 1.0 = BTC season
        btc_dom_normalized = (btc_dominance - 38) / (72 - 38)
        btc_dom_normalized = max(0.0, min(1.0, btc_dom_normalized))

        # Market cap change signal: normalize to -1 to +1
        mcap_signal = max(-1.0, min(1.0, mcap_change_24h / 10.0))

        return {
            "source": "coingecko",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": True,
            "btc_dominance": btc_dominance,
            "eth_dominance": eth_dominance,
            "total_mcap_usd": total_mcap_usd,
            "mcap_change_24h_pct": mcap_change_24h,
            "active_coins": active_coins,
            "defi_volume_24h": defi_volume_24h,
            # Ready-to-use feature columns for FreqAI
            "features": {
                "ext_btc_dominance": btc_dominance / 100.0,
                "ext_btc_dom_normalized": btc_dom_normalized,
                "ext_mcap_change_24h": mcap_change_24h / 100.0,
                "ext_mcap_signal": mcap_signal,
            }
        }

    except Exception as e:
        return {
            "source": "coingecko",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": False,
            "error": str(e),
            "features": {
                "ext_btc_dominance": 0.50,
                "ext_btc_dom_normalized": 0.50,
                "ext_mcap_change_24h": 0.0,
                "ext_mcap_signal": 0.0,
            }
        }


if __name__ == "__main__":
    import json
    result = fetch_coingecko()
    print(json.dumps(result, indent=2))
    if result["ok"]:
        print(f"\nBTC Dominance : {result['btc_dominance']:.1f}%")
        print(f"Market Cap 24h: {result['mcap_change_24h_pct']:+.2f}%")
        print(f"Total Mcap    : ${result['total_mcap_usd']:,.0f}")
