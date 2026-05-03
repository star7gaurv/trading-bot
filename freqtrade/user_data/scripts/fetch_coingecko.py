#!/usr/bin/env python3
import requests, json, os, time
from datetime import datetime

OUT = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/coingecko.json"

def fetch():
    headers = {"accept": "application/json"}

    r1 = requests.get("https://api.coingecko.com/api/v3/global", headers=headers, timeout=15)
    r1.raise_for_status()
    g = r1.json()["data"]

    time.sleep(2)

    r2 = requests.get(
        "https://api.coingecko.com/api/v3/coins/bitcoin"
        "?localization=false&tickers=false&market_data=false&community_data=true&developer_data=false",
        headers=headers, timeout=15
    )
    r2.raise_for_status()
    btc = r2.json()

    result = {
        "updated": datetime.utcnow().isoformat(),
        "btc_dominance": round(g["market_cap_percentage"].get("btc", 0), 2),
        "eth_dominance": round(g["market_cap_percentage"].get("eth", 0), 2),
        "total_market_cap_usd": g["total_market_cap"].get("usd", 0),
        "market_cap_change_24h_pct": round(g.get("market_cap_change_percentage_24h_usd", 0), 4),
        "active_cryptos": g.get("active_cryptocurrencies", 0),
        "btc_reddit_subscribers": btc.get("community_data", {}).get("reddit_subscribers", 0),
        "btc_twitter_followers": btc.get("community_data", {}).get("twitter_followers", 0),
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"CoinGecko: BTC dominance {result['btc_dominance']}%, market cap change {result['market_cap_change_24h_pct']}%")

if __name__ == "__main__":
    fetch()
