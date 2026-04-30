#!/usr/bin/env python3
"""
FinBuddy Phase 2 — DefiLlama TVL Fetcher
Source: DefiLlama API (100% free, no API key)
Output: total DeFi TVL, 24h/7d change, chain breakdown

TVL (Total Value Locked) measures how much capital is in DeFi protocols.
Rising TVL = capital flowing IN (bullish DeFi signal)
Falling TVL = capital flowing OUT (risk-off signal)
"""

import requests
from datetime import datetime

TVL_URL    = "https://api.llama.fi/v2/globalCharts"
CHAINS_URL = "https://api.llama.fi/v2/chains"
TIMEOUT    = 10


def fetch_defillama() -> dict:
    """
    Fetch total DeFi TVL and compute 24h/7d change.
    Returns normalized dict ready to inject into FreqAI features.
    """
    try:
        resp = requests.get(TVL_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        history = resp.json()  # List of [timestamp, tvl_usd]

        if not history or len(history) < 8:
            raise ValueError("Insufficient TVL history data")

        # Most recent entry
        current_tvl   = history[-1][1] if isinstance(history[-1], list) else history[-1].get("totalLiquidityUSD", 0)
        tvl_24h_ago   = history[-2][1] if isinstance(history[-2], list) else history[-2].get("totalLiquidityUSD", 0)
        tvl_7d_ago    = history[-8][1] if isinstance(history[-8], list) else history[-8].get("totalLiquidityUSD", 0)

        change_24h = ((current_tvl - tvl_24h_ago) / tvl_24h_ago * 100) if tvl_24h_ago else 0.0
        change_7d  = ((current_tvl - tvl_7d_ago)  / tvl_7d_ago  * 100) if tvl_7d_ago  else 0.0

        # Normalize TVL change to -1 to +1 signal
        # A 5% daily change in DeFi TVL is large; scale accordingly
        tvl_signal_24h = max(-1.0, min(1.0, change_24h / 5.0))
        tvl_signal_7d  = max(-1.0, min(1.0, change_7d  / 15.0))

        # TVL in billions for readability
        tvl_billions = current_tvl / 1e9

        return {
            "source": "defillama",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": True,
            "tvl_usd": current_tvl,
            "tvl_billions": round(tvl_billions, 2),
            "change_24h_pct": round(change_24h, 3),
            "change_7d_pct": round(change_7d, 3),
            # Ready-to-use feature columns for FreqAI
            "features": {
                "ext_defi_tvl_billions": tvl_billions,
                "ext_defi_tvl_signal_24h": tvl_signal_24h,
                "ext_defi_tvl_signal_7d": tvl_signal_7d,
            }
        }

    except Exception as e:
        return {
            "source": "defillama",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": False,
            "error": str(e),
            "features": {
                "ext_defi_tvl_billions": 50.0,     # rough neutral fallback
                "ext_defi_tvl_signal_24h": 0.0,
                "ext_defi_tvl_signal_7d": 0.0,
            }
        }


if __name__ == "__main__":
    import json
    result = fetch_defillama()
    print(json.dumps(result, indent=2))
    if result["ok"]:
        print(f"\nTotal DeFi TVL : ${result['tvl_billions']:.1f}B")
        print(f"24h change     : {result['change_24h_pct']:+.2f}%")
        print(f"7d change      : {result['change_7d_pct']:+.2f}%")
