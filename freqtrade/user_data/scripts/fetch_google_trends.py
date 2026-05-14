#!/usr/bin/env python3
"""
fetch_google_trends.py — Google Trends data with 429 retry logic.

Fixes:
  - Exponential backoff on 429 (waits 5s, 10s, 20s before giving up)
  - Random jitter to avoid predictable request patterns
  - User-agent rotation to appear as a real browser
  - Falls back to hardcoded defaults only if ALL retries fail
"""
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/google_trends.json")

# Pool of common browser User-Agents — rotated each request
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

DEFAULTS = {
    "gtrends_bitcoin": 50,
    "gtrends_bitcoin_crash": 10,
    "gtrends_buy_bitcoin": 20,
    "gtrends_crypto": 50,
}

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 5  # doubles on each retry: 5 → 10 → 20


def fetch_with_retry() -> dict:
    """Attempt to fetch Google Trends data with retry/backoff on 429."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("pytrends not installed — using defaults")
        return {**DEFAULTS, "error": "pytrends not installed"}

    kw_list = ["bitcoin", "bitcoin crash", "buy bitcoin", "crypto"]
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Jitter: random sleep before each attempt (1.5-4.0s)
            sleep_time = random.uniform(1.5, 4.0)
            if attempt > 0:
                # Exponential backoff on retries
                backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                jitter = random.uniform(0, backoff * 0.3)
                sleep_time = backoff + jitter
                print(f"Retry {attempt}/{MAX_RETRIES-1}: waiting {sleep_time:.1f}s after 429...")

            time.sleep(sleep_time)

            ua = random.choice(_USER_AGENTS)
            pt = TrendReq(
                hl="en-US",
                tz=0,
                timeout=(10, 25),
                requests_args={"headers": {"User-Agent": ua}},
            )
            pt.build_payload(kw_list, timeframe="now 7-d")
            df = pt.interest_over_time()

            if df.empty:
                raise ValueError("Empty trends response")

            latest = df.iloc[-1]
            return {
                "gtrends_bitcoin":       int(latest.get("bitcoin", DEFAULTS["gtrends_bitcoin"])),
                "gtrends_bitcoin_crash": int(latest.get("bitcoin crash", DEFAULTS["gtrends_bitcoin_crash"])),
                "gtrends_buy_bitcoin":   int(latest.get("buy bitcoin", DEFAULTS["gtrends_buy_bitcoin"])),
                "gtrends_crypto":        int(latest.get("crypto", DEFAULTS["gtrends_crypto"])),
            }

        except Exception as e:
            last_error = str(e)
            is_429 = "429" in last_error or "response" in last_error.lower()
            if not is_429 or attempt == MAX_RETRIES - 1:
                break  # non-retryable error or final attempt

    print(f"Google Trends failed after {MAX_RETRIES} attempts: {last_error}")
    return {**DEFAULTS, "error": last_error}


def fetch():
    result_data = fetch_with_retry()
    error = result_data.pop("error", None)

    result = {
        "updated": datetime.now(timezone.utc).isoformat(),
        **result_data,
    }
    if error:
        result["error"] = error
        print(f"Google Trends error (using defaults): {error}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(f"Google Trends: bitcoin={result.get('gtrends_bitcoin')}")


if __name__ == "__main__":
    fetch()
