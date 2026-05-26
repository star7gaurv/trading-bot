#!/usr/bin/env python3
"""Master external data fetcher — runs all sub-fetchers and writes combined JSON."""
import subprocess, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data")
SCRIPTS = ROOT / "scripts"
EXTERNAL = ROOT / "data/external"
COMBINED = EXTERNAL / "combined_context.json"

FETCHERS = [
    "fetch_fear_greed.py",
    "fetch_coingecko.py",
    "fetch_cryptopanic.py",
    "fetch_defillama.py",
    "fetch_google_trends.py",
]

def load_json_safe(path, defaults):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return defaults

def main():
    for script in FETCHERS:
        try:
            subprocess.run(
                [sys.executable, str(SCRIPTS / script)],
                timeout=30, check=True
            )
        except Exception as e:
            print(f"Warning: {script} failed: {e}")

    fg    = load_json_safe(EXTERNAL / "fear_greed.json",  {"current_value": 50, "normalized": 0.5})
    cg    = load_json_safe(EXTERNAL / "coingecko.json",   {"btc_dominance": 50, "market_cap_change_24h_pct": 0})
    cp    = load_json_safe(EXTERNAL / "cryptopanic.json", {"sentiment_ratio": 0.5, "bullish_count": 0, "bearish_count": 0})
    dl    = load_json_safe(EXTERNAL / "defillama.json",   {"total_defi_tvl_usd": 0, "tvl_change_24h_pct": 0})
    gt    = load_json_safe(EXTERNAL / "google_trends.json", {"gtrends_bitcoin": 50})

    # Load regime
    regime_file = Path("/home/ubuntu/var/www/html/trade/finbuddy_memory/regimes/current.json")
    if regime_file.exists():
        regime_data = load_json_safe(regime_file, {"regime": "NEUTRAL", "confidence": 0.5})
    else:
        regime_data = {"regime": "NEUTRAL", "confidence": 0.5}

    combined = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
        "fear_greed": fg.get("current_value", 50),
        "fear_greed_label": fg.get("current_label", "Neutral"),
        "fear_greed_normalized": fg.get("normalized", 0.5),
        "btc_dominance": cg.get("btc_dominance", 50),
        "total_market_cap_usd": cg.get("total_market_cap_usd", 0),
        "market_cap_change_24h_pct": cg.get("market_cap_change_24h_pct", 0),
        "news_bullish_count": cp.get("bullish_count", 0),
        "news_bearish_count": cp.get("bearish_count", 0),
        "news_sentiment_ratio": cp.get("sentiment_ratio", 0.5),
        "total_defi_tvl_usd": dl.get("total_defi_tvl_usd", 0),
        "tvl_change_24h_pct": dl.get("tvl_change_24h_pct", 0),
        "gtrends_bitcoin": gt.get("gtrends_bitcoin", 50),
        "gtrends_bitcoin_crash": gt.get("gtrends_bitcoin_crash", 10),
        "gtrends_buy_bitcoin": gt.get("gtrends_buy_bitcoin", 20),
        "current_regime": regime_data.get("regime", "NEUTRAL"),
        "regime_confidence": regime_data.get("confidence", 0.5),
        "regime_since": regime_data.get("since", ""),
    }

    with open(COMBINED, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"Combined context written: {COMBINED}")

if __name__ == "__main__":
    main()
