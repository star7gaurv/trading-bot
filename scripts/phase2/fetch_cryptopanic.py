#!/usr/bin/env python3
"""
FinBuddy Phase 2 — CryptoPanic News Sentiment Fetcher
Source: CryptoPanic API
Free tier: limited to public posts (no auth token needed for basic use)
Optional: set CRYPTOPANIC_TOKEN env var for more results

Scores news as bullish/bearish/neutral based on votes and keywords.
"""

import os
import re
import requests
from datetime import datetime, timedelta

BASE_URL = "https://cryptopanic.com/api/v1/posts/"
TIMEOUT  = 10

# Bearish/bullish keyword lists for scoring unvoted articles
BULLISH_WORDS = [
    "rally", "surge", "soar", "breakout", "bullish", "moon", "ath", "all-time high",
    "pump", "adoption", "etf approved", "institutional", "upgrade", "partnership"
]
BEARISH_WORDS = [
    "crash", "plunge", "dump", "bear", "hack", "exploit", "ban", "regulation",
    "lawsuit", "sec", "fraud", "liquidation", "sell-off", "correction", "fear"
]


def score_title(title: str) -> float:
    """Keyword-based sentiment score: -1.0 (bearish) to +1.0 (bullish)"""
    t = title.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in t)
    bear = sum(1 for w in BEARISH_WORDS if w in t)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def fetch_cryptopanic(currencies: str = "BTC,ETH,SOL") -> dict:
    """
    Fetch recent crypto news and compute aggregate sentiment score.
    Returns normalized dict ready to inject into FreqAI features.
    """
    token = os.getenv("CRYPTOPANIC_TOKEN", "")
    params = {
        "format":     "json",
        "currencies": currencies,
        "kind":       "news",
        "public":     "true",
    }
    if token:
        params["auth_token"] = token

    try:
        resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        posts = resp.json().get("results", [])

        scores = []
        bullish_count = 0
        bearish_count = 0

        for post in posts[:20]:  # Top 20 most recent
            title = post.get("title", "")
            votes = post.get("votes", {})

            # Use vote data if available (auth token), else keyword scoring
            v_pos = votes.get("positive", 0) + votes.get("liked", 0)
            v_neg = votes.get("negative", 0) + votes.get("disliked", 0)
            v_total = v_pos + v_neg

            if v_total > 0:
                score = (v_pos - v_neg) / v_total
            else:
                score = score_title(title)

            scores.append(score)
            if score > 0.1:
                bullish_count += 1
            elif score < -0.1:
                bearish_count += 1

        avg_score    = sum(scores) / len(scores) if scores else 0.0
        total_scored = len(scores)
        bull_ratio   = bullish_count / total_scored if total_scored > 0 else 0.5
        bear_ratio   = bearish_count / total_scored if total_scored > 0 else 0.5

        return {
            "source": "cryptopanic",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": True,
            "currencies": currencies,
            "articles_scored": total_scored,
            "avg_sentiment": avg_score,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "bull_ratio": bull_ratio,
            "bear_ratio": bear_ratio,
            # Ready-to-use feature columns for FreqAI
            "features": {
                "ext_news_sentiment": avg_score,
                "ext_news_bull_ratio": bull_ratio,
                "ext_news_bear_ratio": bear_ratio,
            }
        }

    except Exception as e:
        return {
            "source": "cryptopanic",
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "ok": False,
            "error": str(e),
            "features": {
                "ext_news_sentiment": 0.0,
                "ext_news_bull_ratio": 0.5,
                "ext_news_bear_ratio": 0.5,
            }
        }


if __name__ == "__main__":
    import json
    result = fetch_cryptopanic()
    print(json.dumps(result, indent=2))
    if result["ok"]:
        print(f"\nArticles scored : {result['articles_scored']}")
        print(f"Avg sentiment   : {result['avg_sentiment']:+.3f}")
        print(f"Bullish / Bearish: {result['bullish_count']} / {result['bearish_count']}")
