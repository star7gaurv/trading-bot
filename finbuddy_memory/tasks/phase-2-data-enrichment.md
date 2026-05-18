# Phase 2 — Data Enrichment (Free External Data Sources)

> Feed the FreqAI brain with richer signals beyond raw OHLCV.
> All sources here are FREE — no paid APIs.
> Data is fetched by a background Python script and written to files that FreqAI reads as features.

---

## Architecture

```
Background script (runs every 15 min, cron or systemd)
    ↓
Fetches from multiple free APIs
    ↓
Writes to: freqtrade/user_data/data/external/
    ↓
FreqAI strategy reads these files as additional features
    ↓
LightGBM gets richer input → better signals
```

---

## Task 2.1 — Fear & Greed Index Integration
**Status:** ⬜ Pending  
**Effort:** 1 hour  
**File:** `freqtrade/user_data/scripts/fetch_fear_greed.py`

The Fear & Greed Index (0–100) is a reliable macro sentiment signal. Completely free API.

### API
```
GET https://api.alternative.me/fng/?limit=1
```

### Response
```json
{"data": [{"value": "35", "value_classification": "Fear", "timestamp": "..."}]}
```

### Output file
`freqtrade/user_data/data/external/fear_greed.json`

### FreqAI feature
Add `fear_greed_value` (0–100 normalized to 0–1) as a feature in `FinBuddyFreqAI.py`

---

## Task 2.2 — CoinGecko Market Data Integration
**Status:** ⬜ Pending  
**Effort:** 2 hours  
**File:** `freqtrade/user_data/scripts/fetch_coingecko.py`

Free CoinGecko API gives market cap dominance, total crypto market cap, and social data.

### Key endpoints (no API key needed)
```
GET https://api.coingecko.com/api/v3/global
→ total_market_cap, btc_dominance, market_cap_change_24h

GET https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&community_data=true
→ reddit_subscribers, twitter_followers, developer_activity
```

### Features to extract
- `btc_dominance` — BTC's share of total market cap
- `total_market_cap_usd` — total crypto market size
- `market_cap_change_24h_pct` — market momentum
- `btc_reddit_subscribers_change` — social growth signal

---

## Task 2.3 — CryptoPanic News Sentiment Integration
**Status:** ⬜ Pending  
**Effort:** 2 hours  
**File:** `freqtrade/user_data/scripts/fetch_cryptopanic.py`

CryptoPanic aggregates crypto news and tags each item as bullish/bearish. Free API key.

### Setup
1. Register at https://cryptopanic.com/developers/api/
2. Get free API key
3. Store in environment variable `CRYPTOPANIC_API_KEY`

### Endpoint
```
GET https://cryptopanic.com/api/v1/posts/?auth_token=KEY&currencies=BTC,ETH&filter=hot
```

### Features to extract
- `news_bullish_count` — bullish articles in last hour
- `news_bearish_count` — bearish articles in last hour
- `news_sentiment_ratio` — bullish / (bullish + bearish)

---

## Task 2.4 — DefiLlama TVL Integration
**Status:** ⬜ Pending  
**Effort:** 1 hour  
**File:** `freqtrade/user_data/scripts/fetch_defillama.py`

Total Value Locked in DeFi is a macro signal for crypto market health. Completely free, no auth.

### Endpoint
```
GET https://api.llama.fi/v2/chains
→ TVL by blockchain

GET https://api.llama.fi/v2/globalCharts
→ Historical total DeFi TVL
```

### Features
- `total_defi_tvl` — total DeFi TVL
- `tvl_change_24h_pct` — TVL momentum

---

## Task 2.5 — Google Trends Integration
**Status:** ⬜ Pending  
**Effort:** 1 hour  
**File:** `freqtrade/user_data/scripts/fetch_google_trends.py`

Search interest for "bitcoin", "crypto", "buy bitcoin" is a genuine leading indicator. Free via pytrends.

```bash
pip install pytrends --break-system-packages
```

### Keywords to track
- "bitcoin" — general interest
- "bitcoin crash" — fear signal
- "buy bitcoin" — retail FOMO signal
- "crypto" — general market interest

### Features
- `gtrends_bitcoin` — 0–100 interest score
- `gtrends_bitcoin_crash` — fear indicator

---

## Task 2.6 — TradingView Webhook Integration
**Status:** 🔴 ABANDONED (2026-05-04) — see [Phase 6 abandonment note]

> **2026-05-18**: TradingView free tier limits alerts to 1 per account; the webhook + scripts/PineScript on free account isn't viable for the multi-pair, multi-timeframe FinBuddy needs. Path abandoned. FreqAI is the sole signal source.

~~TradingView's alert system (free) can fire webhooks when Pine Script conditions are met. This lets us use ANY TradingView indicator as a signal source for free.~~ (abandoned — paid plan required)

### Architecture
```
TradingView Pine Script alert fires
    ↓
Webhook POST to http://REDACTED-SERVER_IP:9999/tradingview
    ↓
Lightweight Flask/FastAPI receiver on server (port 9999)
    ↓
Writes signal to: freqtrade/user_data/data/external/tradingview_signals.json
    ↓
FreqAI strategy reads this as a feature
```

### TradingView alerts to set up (free account, up to 1 alert)
- Supertrend direction change on 15m
- Volume anomaly (3x average)

### Server setup
```bash
pip install fastapi uvicorn --break-system-packages
# Add to crontab: @reboot uvicorn tradingview_webhook:app --port 9999
```

### Nginx proxy (add to existing nginx config)
```nginx
location /tradingview {
    proxy_pass http://127.0.0.1:9999;
}
```

---

## Task 2.7 — Build External Data Aggregator Script
**Status:** ⬜ Pending (after 2.1–2.5)  
**Effort:** 1 hour  
**File:** `freqtrade/user_data/scripts/fetch_all_external.py`

Master script that calls all individual fetchers and writes a combined JSON file.

### Output: `freqtrade/user_data/data/external/combined_context.json`
```json
{
  "timestamp": "2026-04-27T12:00:00Z",
  "fear_greed": 35,
  "btc_dominance": 54.2,
  "market_cap_change_24h_pct": -1.3,
  "news_sentiment_ratio": 0.42,
  "total_defi_tvl": 95000000000,
  "gtrends_bitcoin": 67
}
```

### Cron schedule
```
*/15 * * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/fetch_all_external.py
```

---

## Phase 2 Complete When
- [ ] All fetcher scripts run without errors
- [ ] `combined_context.json` updates every 15 minutes
- [ ] FreqAI strategy reads external data as features
- [ ] LightGBM retrain includes external features
- [ ] TradingView webhook receiver running and persistent
