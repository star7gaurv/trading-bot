#!/usr/bin/env python3
import requests, json, os
from datetime import datetime

OUT = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/fear_greed.json"

def fetch():
    r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    result = {
        "updated": datetime.utcnow().isoformat(),
        "current_value": int(data[0]["value"]),
        "current_label": data[0]["value_classification"],
        "normalized": round(int(data[0]["value"]) / 100, 4),
        "history_7d": [{"value": int(d["value"]), "label": d["value_classification"]} for d in data]
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Fear & Greed: {result['current_value']} ({result['current_label']})")

if __name__ == "__main__":
    fetch()
