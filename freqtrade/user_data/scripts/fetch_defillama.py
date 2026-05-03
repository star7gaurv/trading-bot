#!/usr/bin/env python3
import requests, json, os
from datetime import datetime

OUT = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/defillama.json"

def fetch():
    r = requests.get("https://api.llama.fi/v2/globalCharts", timeout=15)
    r.raise_for_status()
    data = r.json()

    if len(data) >= 2:
        current_tvl = data[-1][1]
        prev_tvl = data[-2][1]
        change_24h_pct = round((current_tvl - prev_tvl) / prev_tvl * 100, 4) if prev_tvl else 0
    else:
        current_tvl = data[-1][1] if data else 0
        change_24h_pct = 0

    result = {
        "updated": datetime.utcnow().isoformat(),
        "total_defi_tvl_usd": current_tvl,
        "tvl_change_24h_pct": change_24h_pct,
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"DeFiLlama: TVL=${current_tvl:,.0f} change={change_24h_pct}%")

if __name__ == "__main__":
    fetch()
