# Phase 8 — Futures Account Setup

> Migrate FreqTrade from spot dry-run to Binance USDT-M Futures.
> All config changes, risk parameters, and safety guards for futures trading.
> **Prerequisite:** Phase 1 walk-forward backtest passed (Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2 on OOS window).

---

## Phase Status: ⬜ Pending

---

## Task 8.1 — Binance Futures API Key Setup
**Status:** ⬜ Pending

Create a **dedicated Futures API key** on Binance with restricted permissions.

### Steps
1. Log into Binance → Account → API Management
2. Create new API key labeled `finbuddy-futures-trading`
3. Permissions: ✅ Enable Futures Trading | ❌ No Spot | ❌ No Withdrawals | ❌ No Transfer
4. IP Whitelist: Add `REDACTED-SERVER_IP` (server IP) — **mandatory**
5. Store securely on server:
   ```bash
   echo 'BINANCE_FUTURES_API_KEY=your_key_here' >> /home/ubuntu/var/www/html/trade/freqtrade/.env
   echo 'BINANCE_FUTURES_API_SECRET=your_secret_here' >> /home/ubuntu/var/www/html/trade/freqtrade/.env
   ```
6. Verify `.env` is in `.gitignore` — **never commit keys**
7. Update `users/user_01_gaurav.json` → `"exchange": "binance_futures"`, `"paper_trading": true`

---

## Task 8.2 — Create Futures Config File
**Status:** ⬜ Pending

Create a **separate config file** for futures. Do NOT overwrite the spot config.

### File to create: `freqtrade/user_data/futures_config.json`

Key fields:
```json
{
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "exchange": {
    "name": "binance",
    "key": "${BINANCE_FUTURES_API_KEY}",
    "secret": "${BINANCE_FUTURES_API_SECRET}",
    "ccxt_config": {
      "defaultType": "future"
    }
  },
  "stake_currency": "USDT",
  "stake_amount": 200,
  "max_open_trades": 4,
  "dry_run": true,
  "dry_run_wallet": 1000,
  "strategy": "FinBuddyFreqAI",
  "freqaimodel": "LightGBMRegressor"
}
```

### Validate config:
```bash
docker exec freqtrade freqtrade check-exchange --config /freqtrade/user_data/futures_config.json
```

---

## Task 8.3 — Set Default Leverage Per Pair
**Status:** ⬜ Pending

All futures positions use **5× leverage max** to start. Adjust down for volatile pairs.

### Steps
1. In `futures_config.json`, add leverage section:
   ```json
   "leverage_config": {
     "default_leverage": 3,
     "max_leverage": 5
   }
   ```
2. In `FinBuddyFreqAI.py`, add:
   ```python
   def leverage(self, pair: str, current_time, current_rate: float,
                proposed_leverage: float, max_leverage: float,
                entry_tag, side: str, **kwargs) -> float:
       return min(3.0, max_leverage)
   ```
3. Verify leverage is applied in dry-run logs

---

## Task 8.4 — Docker Compose Futures Service
**Status:** ⬜ Pending

Add a **second FreqTrade service** in docker-compose for futures (keep spot service intact for reference).

```yaml
freqtrade-futures:
  image: freqtradeorg/freqtrade:develop_freqai
  restart: unless-stopped
  container_name: freqtrade-futures
  volumes:
    - ./user_data:/freqtrade/user_data
    - ./.env:/freqtrade/.env
  ports:
    - "8081:8080"
  command: >
    trade
    --logfile /freqtrade/user_data/logs/futures.log
    --config /freqtrade/user_data/futures_config.json
    --strategy FinBuddyFreqAI
    --freqaimodel LightGBMRegressor
  environment:
    - BINANCE_FUTURES_API_KEY=${BINANCE_FUTURES_API_KEY}
    - BINANCE_FUTURES_API_SECRET=${BINANCE_FUTURES_API_SECRET}
    - XAI_API_KEY=${XAI_API_KEY}
```

Note: futures service runs on **port 8081**, spot on 8080.

---

## Task 8.5 — Pair Selection for Futures
**Status:** ⬜ Pending

Start with **top 10 Binance USDT-M pairs by volume** only. No memecoins.

### Allowed initial pairs:
```
BTC/USDT:USDT, ETH/USDT:USDT, BNB/USDT:USDT,
SOL/USDT:USDT, ADA/USDT:USDT, AVAX/USDT:USDT,
DOT/USDT:USDT, LINK/USDT:USDT, MATIC/USDT:USDT, LTC/USDT:USDT
```

Blacklist: TRUMP, DOGE, SHIB, PEPE, WIF, BONK and all pairs with < $50M daily volume.

---

## Phase 8 Completion Checklist
- [ ] Futures API key created, IP-whitelisted, stored in .env
- [ ] `futures_config.json` created and validated
- [ ] Leverage set to 3× default, 5× max
- [ ] `freqtrade-futures` Docker service running
- [ ] FreqTrade futures dry-run active, Telegram notifications firing
- [ ] At least 10 dry-run trades visible in `trade.star7gaurav.in` on futures

---

## 🔗 Related Files
- [[CLAUDE]] ← infra, server details, environment
- [[FINBUDDY_PROJECT_MEMORY]] ← master hub
- [[tasks/phase-9-futures-risk]] ← next phase: risk engine
- [[tasks/phase-1-freqai-brain]] ← strategy that runs inside this setup
- `users/user_01_gaurav.json` ← user config to update with futures params
