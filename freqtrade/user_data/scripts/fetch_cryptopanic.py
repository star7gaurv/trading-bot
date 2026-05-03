#!/usr/bin/env python3
"""
fetch_news_sentiment.py — replaces fetch_cryptopanic.py
Uses Binance public news API (no key required) + Reddit RSS for sentiment.
CryptoPanic free plan discontinued April 1, 2026.
"""
import requests, json
from datetime import datetime
from pathlib import Path

OUT = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/cryptopanic.json")


def fetch_binance_news():
    """Fetch latest crypto news from Binance public CMS API."""
    url = (
        "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
        "?type=1&pageSize=10&pageNo=1"
    )
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.json().get("data", {}).get("articles", [])
    return [a.get("title", "") for a in data]


BULLISH_WORDS = [
    "surge", "rally", "bullish", "breakout", "ath", "all-time high",
    "gain", "rise", "pump", "adoption", "approval", "buy", "launch",
    "partnership", "upgrade", "growth", "record",
]
BEARISH_WORDS = [
    "crash", "drop", "bearish", "dump", "ban", "hack", "exploit",
    "lawsuit", "sell", "decline", "fear", "warning", "fraud",
    "regulation", "crackdown", "loss", "plunge",
]


def score_headline(title: str):
    t = title.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in t)
    bear = sum(1 for w in BEARISH_WORDS if w in t)
    return bull, bear


def fetch():
    try:
        headlines = fetch_binance_news()
    except Exception as e:
        print(f"Binance news fetch failed: {e}")
        headlines = []

    bullish_count = 0
    bearish_count = 0
    for h in headlines:
        b, br = score_headline(h)
        bullish_count += b
        bearish_count += br

    total = bullish_count + bearish_count
    sentiment_ratio = round(bullish_count / total, 4) if total > 0 else 0.5

    result = {
        "updated": datetime.utcnow().isoformat(),
        "source": "binance_news",
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "sentiment_ratio": sentiment_ratio,
        "headlines": headlines[:10],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(
        f"News sentiment (Binance): bullish={bullish_count} "
        f"bearish={bearish_count} ratio={sentiment_ratio}"
    )


if __name__ == "__main__":
    fetch()
