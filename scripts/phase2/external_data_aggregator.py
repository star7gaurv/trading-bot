#!/usr/bin/env python3
"""
FinBuddy Phase 2 — External Data Aggregator

Runs all 5 data fetchers and combines their output into:
  1. A single JSON file for logging/memory vault
  2. A flat dict of FreqAI-ready features

Usage:
  python scripts/phase2/external_data_aggregator.py
  python scripts/phase2/external_data_aggregator.py --output /path/to/output.json

Cron setup (run every 15 minutes to stay in sync with FreqTrade candles):
  */15 * * * * docker exec freqtrade python /freqtrade/scripts/phase2/external_data_aggregator.py

Output file: finbuddy_memory/signals/external_data_latest.json
(also written to /tmp/finbuddy_ext_data.json for in-process reads)
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Add scripts dir to path so fetchers can be imported
sys.path.insert(0, str(Path(__file__).parent))

from fetch_fear_greed   import fetch_fear_greed
from fetch_coingecko    import fetch_coingecko
from fetch_cryptopanic  import fetch_cryptopanic
from fetch_defillama    import fetch_defillama
from fetch_google_trends import fetch_google_trends

DEFAULT_OUTPUT  = "finbuddy_memory/signals/external_data_latest.json"
TMP_OUTPUT       = "/tmp/finbuddy_ext_data.json"


def run_all_fetchers() -> dict:
    """Run all 5 fetchers. Never crash — each has its own fallback."""
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] Fetching external data...")

    fear_greed   = fetch_fear_greed()
    coingecko    = fetch_coingecko()
    cryptopanic  = fetch_cryptopanic()
    defillama    = fetch_defillama()
    google_trends = fetch_google_trends()

    sources = [fear_greed, coingecko, cryptopanic, defillama, google_trends]
    ok_count = sum(1 for s in sources if s.get("ok", False))

    # Merge all features into one flat dict
    all_features = {}
    for source in sources:
        all_features.update(source.get("features", {}))

    # Composite market score (-1 to +1)
    # Weights: Fear/Greed 30%, CoinGecko 20%, News 25%, DeFi TVL 15%, Trends 10%
    composite = (
        fear_greed["features"].get("ext_fear_greed_regime", 0)    * 0.30 +
        coingecko["features"].get("ext_mcap_signal", 0)           * 0.20 +
        cryptopanic["features"].get("ext_news_sentiment", 0)      * 0.25 +
        defillama["features"].get("ext_defi_tvl_signal_24h", 0)   * 0.15 +
        (google_trends["features"].get("ext_trends_contrarian", 0.5) - 0.5) * 2 * 0.10
    )
    all_features["ext_composite_score"] = round(composite, 4)

    payload = {
        "aggregated_at": datetime.utcnow().isoformat() + "Z",
        "sources_ok": ok_count,
        "sources_total": len(sources),
        "composite_score": round(composite, 4),
        "composite_label": (
            "STRONG_BULL" if composite >  0.50 else
            "BULL"        if composite >  0.20 else
            "NEUTRAL"     if composite > -0.20 else
            "BEAR"        if composite > -0.50 else
            "STRONG_BEAR"
        ),
        "features": all_features,
        "sources": {
            "fear_greed":    fear_greed,
            "coingecko":     coingecko,
            "cryptopanic":   cryptopanic,
            "defillama":     defillama,
            "google_trends": google_trends,
        }
    }

    print(f"  Sources OK   : {ok_count}/{len(sources)}")
    print(f"  Composite    : {composite:+.3f} — {payload['composite_label']}")
    if fear_greed.get("ok"):
        print(f"  Fear & Greed : {fear_greed['value']} ({fear_greed['classification']})")
    if coingecko.get("ok"):
        print(f"  BTC Dominance: {coingecko['btc_dominance']:.1f}%")
    if defillama.get("ok"):
        print(f"  DeFi TVL     : ${defillama['tvl_billions']:.1f}B ({defillama['change_24h_pct']:+.1f}% 24h)")

    return payload


def save_output(payload: dict, output_path: str):
    """Save to output path and /tmp for in-process reads."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    with open(TMP_OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  Saved to     : {output_path}")
    print(f"  Also at      : {TMP_OUTPUT}")


def load_latest_features() -> dict:
    """
    Quick loader for FreqAI strategy to call.
    Returns flat feature dict, or neutral defaults if file is stale/missing.
    """
    try:
        p = Path(TMP_OUTPUT)
        if not p.exists():
            raise FileNotFoundError
        with open(p) as f:
            data = json.load(f)
        # Check if data is fresh (within 30 minutes)
        fetched = datetime.fromisoformat(data["aggregated_at"].replace("Z", ""))
        age_mins = (datetime.utcnow() - fetched).total_seconds() / 60
        if age_mins > 30:
            raise ValueError(f"External data is {age_mins:.0f} min old")
        return data["features"]
    except Exception:
        # Return neutral defaults — never crash the strategy
        return {
            "ext_fear_greed": 0.5,
            "ext_fear_greed_regime": 0.0,
            "ext_fear_greed_trend_7d": 0.0,
            "ext_btc_dominance": 0.5,
            "ext_btc_dom_normalized": 0.5,
            "ext_mcap_change_24h": 0.0,
            "ext_mcap_signal": 0.0,
            "ext_news_sentiment": 0.0,
            "ext_news_bull_ratio": 0.5,
            "ext_news_bear_ratio": 0.5,
            "ext_defi_tvl_billions": 50.0,
            "ext_defi_tvl_signal_24h": 0.0,
            "ext_defi_tvl_signal_7d": 0.0,
            "ext_trends_btc": 0.5,
            "ext_trends_avg": 0.5,
            "ext_trends_contrarian": 0.5,
            "ext_trends_7d_change": 0.0,
            "ext_composite_score": 0.0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinBuddy external data aggregator")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = run_all_fetchers()
    save_output(payload, args.output)
    print(f"\nDone. Composite: {payload['composite_score']:+.3f} — {payload['composite_label']}")
