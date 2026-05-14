#!/usr/bin/env python3
"""
fetch_news_sentiment.py — Binance public news API for crypto sentiment.

Fixed: targets catalogId=48 (New Listings) and catalogId=49 (Latest Binance News)
instead of type=1 which returns maintenance/system announcements.

CryptoPanic free plan discontinued April 1, 2026.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    import urllib.request
    _HAS_REQUESTS = False

OUT = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/cryptopanic.json")

# Target catalogIds — confirmed correct via API inspection (2026-05-14)
# 48 = New Cryptocurrency Listing, 49 = Latest Binance News
TARGET_CATALOG_IDS = [48, 49]


def fetch_binance_news() -> list[str]:
    """Fetch latest crypto news from Binance public CMS API (correct catalogs)."""
    all_titles = []
    for catalog_id in TARGET_CATALOG_IDS:
        url = (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
            f"?type=1&pageSize=10&pageNo=1&catalogId={catalog_id}"
        )
        try:
            if _HAS_REQUESTS:
                r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                catalogs = r.json().get("data", {}).get("catalogs", [])
            else:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    catalogs = json.loads(resp.read().decode()).get("data", {}).get("catalogs", [])

            for catalog in catalogs:
                if catalog.get("catalogId") == catalog_id:
                    articles = catalog.get("articles", [])
                    all_titles.extend(a.get("title", "") for a in articles)
                    break
            time.sleep(0.5)  # polite delay between catalog requests
        except Exception as e:
            print(f"Binance news fetch failed for catalogId={catalog_id}: {e}")

    return all_titles


BULLISH_WORDS = [
    "surge", "rally", "bullish", "breakout", "ath", "all-time high",
    "gain", "rise", "pump", "adoption", "approval", "buy", "launch",
    "partnership", "upgrade", "growth", "record", "listing", "adds",
    "new", "integration", "expansion", "support", "launch",
]
BEARISH_WORDS = [
    "crash", "drop", "bearish", "dump", "ban", "hack", "exploit",
    "lawsuit", "sell", "decline", "fear", "warning", "fraud",
    "regulation", "crackdown", "loss", "plunge", "delist", "remove",
    "suspend", "halt", "investigation",
]


def score_headline(title: str) -> tuple[int, int]:
    t = title.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in t)
    bear = sum(1 for w in BEARISH_WORDS if w in t)
    return bull, bear


def fetch():
    headlines = fetch_binance_news()

    bullish_count = 0
    bearish_count = 0
    for h in headlines:
        b, br = score_headline(h)
        bullish_count += b
        bearish_count += br

    total = bullish_count + bearish_count
    sentiment_ratio = round(bullish_count / total, 4) if total > 0 else 0.5

    result = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "binance_news_v2",
        "catalog_ids": TARGET_CATALOG_IDS,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "sentiment_ratio": sentiment_ratio,
        "headlines": headlines[:20],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(
        f"News sentiment (Binance catalogs {TARGET_CATALOG_IDS}): "
        f"bullish={bullish_count} bearish={bearish_count} ratio={sentiment_ratio} "
        f"({len(headlines)} headlines)"
    )


if __name__ == "__main__":
    fetch()
