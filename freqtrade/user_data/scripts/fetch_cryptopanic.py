#!/usr/bin/env python3
import requests, json, os
from datetime import datetime

OUT = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/cryptopanic.json"
API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")

def fetch():
    if not API_KEY:
        result = {
            "updated": datetime.utcnow().isoformat(),
            "error": "CRYPTOPANIC_API_KEY not set",
            "bullish_count": 0, "bearish_count": 0,
            "sentiment_ratio": 0.5, "headlines": []
        }
        with open(OUT, "w") as f:
            json.dump(result, f, indent=2)
        print("CryptoPanic: API key not set — skipping")
        return

    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={API_KEY}&currencies=BTC,ETH&filter=hot&public=true"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    posts = r.json().get("results", [])

    bullish = sum(1 for p in posts if p.get("votes", {}).get("positive", 0) > p.get("votes", {}).get("negative", 0))
    bearish = sum(1 for p in posts if p.get("votes", {}).get("negative", 0) > p.get("votes", {}).get("positive", 0))
    total = bullish + bearish
    ratio = round(bullish / total, 4) if total > 0 else 0.5

    result = {
        "updated": datetime.utcnow().isoformat(),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "sentiment_ratio": ratio,
        "headlines": [p.get("title", "") for p in posts[:10]]
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"CryptoPanic: bullish={bullish} bearish={bearish} ratio={ratio}")

if __name__ == "__main__":
    fetch()
