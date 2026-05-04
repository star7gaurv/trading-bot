#!/usr/bin/env python3
import json, os
from datetime import datetime

OUT = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/google_trends.json"

def fetch():
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        kw_list = ["bitcoin", "bitcoin crash", "buy bitcoin", "crypto"]
        pt.build_payload(kw_list, timeframe="now 7-d")
        df = pt.interest_over_time()

        if df.empty:
            raise ValueError("Empty trends response")

        latest = df.iloc[-1]
        result = {
            "updated": datetime.utcnow().isoformat(),
            "gtrends_bitcoin": int(latest.get("bitcoin", 0)),
            "gtrends_bitcoin_crash": int(latest.get("bitcoin crash", 0)),
            "gtrends_buy_bitcoin": int(latest.get("buy bitcoin", 0)),
            "gtrends_crypto": int(latest.get("crypto", 0)),
        }
    except Exception as e:
        result = {
            "updated": datetime.utcnow().isoformat(),
            "error": str(e),
            "gtrends_bitcoin": 50,
            "gtrends_bitcoin_crash": 10,
            "gtrends_buy_bitcoin": 20,
            "gtrends_crypto": 50,
        }
        print(f"Google Trends error (using defaults): {e}")

    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Google Trends: bitcoin={result['gtrends_bitcoin']}")

if __name__ == "__main__":
    fetch()
