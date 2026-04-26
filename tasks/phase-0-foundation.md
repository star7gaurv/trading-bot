# Phase 0 — Foundation (Fix, Clean, Wire)

> Complete all loose ends before building anything new.
> These are blocking tasks — later phases depend on a clean baseline.

---

## Task 0.1 — Complete Trade Event Handler
**Status:** 🔴 Not Done  
**Effort:** 15 minutes  
**Blocker for:** Everything

The N8N Trade Event Handler workflow was imported but never activated. FreqTrade needs to know where to send webhook events.

### Steps
1. SSH into server: `ssh ubuntu@REDACTED-SERVER_IP`
2. Open N8N at `https://n8n.star7gaurav.in`
3. Find the "Trade Event Handler" workflow
4. Click the FreqTrade Webhook node → copy the **Production URL**
5. Edit FreqTrade config:
   ```bash
   nano /home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json
   ```
6. Add webhook section:
   ```json
   "webhook": {
     "enabled": true,
     "url": "PASTE_PRODUCTION_URL_HERE",
     "webhookbuy": {"type": "buy"},
     "webhookbuycancel": {"type": "buy_cancel"},
     "webhooksell": {"type": "sell"},
     "webhooksellcancel": {"type": "sell_cancel"},
     "webhookstatus": {"type": "status"}
   }
   ```
7. Restart FreqTrade: `docker restart freqtrade`
8. Activate the workflow in N8N (toggle to Active)
9. Verify: open a test trade and check Telegram

---

## Task 0.2 — Wire Telegram into FreqTrade Config
**Status:** 🔴 Not Done  
**Effort:** 10 minutes

FreqTrade can send its own Telegram notifications independent of N8N. Currently not configured.

### Steps
1. Edit `config.json`:
   ```json
   "telegram": {
     "enabled": true,
     "token": "7799143446:AAElV1Yk6Mk7fBMCCaOfakGWQ0cheIcmIGU",
     "chat_id": "5622292536",
     "notification_settings": {
       "status": "on",
       "warning": "on",
       "startup": "on",
       "entry": "on",
       "exit": "on",
       "entry_cancel": "on",
       "exit_cancel": "on"
     }
   }
   ```
2. Restart FreqTrade: `docker restart freqtrade`
3. Send `/status` to Telegram bot to verify

---

## Task 0.3 — Pairlist Audit (Remove Scam Tokens)
**Status:** 🔴 Not Done  
**Effort:** 20 minutes

Tokens with Chinese/non-ASCII characters in their names were flagged as potentially fraudulent pump-and-dump tokens. Clean the whitelist.

### Steps
1. Check current whitelist:
   ```bash
   curl -s -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/whitelist | python3 -m json.tool
   ```
2. Identify suspicious pairs (Chinese characters, random strings, very low volume)
3. Edit `config.json` → `exchange.pair_whitelist` — remove suspicious pairs
4. Keep only established pairs: BTC, ETH, BNB, SOL, ADA, DOT, AVAX, MATIC, LINK, UNI, AAVE, etc.
5. Restart FreqTrade to reload whitelist

---

## Task 0.4 — N8N Workspace Cleanup
**Status:** 🔴 Not Done  
**Effort:** 30 minutes

N8N has accumulated dead workflows. Clean them out.

### Workflows to DELETE
- Any workflow referencing Dify (Dify is gone from server)
- Any duplicate v1 signal workflows (v3 is the active one)
- Any video generation workflows (unrelated, somehow ended up here)

### Workflows to KEEP
- N8N v3 Market Signal Pipeline (the active 15-min cron)
- Trade Event Handler (once activated in Task 0.1)

### Steps
1. Go to `https://n8n.star7gaurav.in`
2. Review all workflows
3. Delete confirmed dead ones
4. Document surviving workflows in `n8n/workflows/README.md`

---

## Task 0.5 — Create User Config File
**Status:** 🔴 Not Done  
**Effort:** 15 minutes

Create `users/user_01_gaurav.json` — the user config that the future executor and signal generator will read. Everything personal goes here, nothing hardcoded in workflows.

### File to create: `users/user_01_gaurav.json`
```json
{
  "user_id": "user_01_gaurav",
  "display_name": "Gaurav",
  "exchange": "binance",
  "binance_api_key": "${BINANCE_API_KEY}",
  "binance_api_secret": "${BINANCE_API_SECRET}",
  "capital_usd": 1000,
  "max_risk_per_trade_pct": 0.02,
  "max_drawdown_pct": 0.15,
  "max_open_trades": 4,
  "active_strategies": ["rsi_macd_ai_v1"],
  "regime_filter": {
    "blocked_regimes": ["CRASH"],
    "reduce_size_regimes": ["BEAR"]
  },
  "min_confidence_threshold": 0.65,
  "telegram_chat_id": "5622292536",
  "paper_trading": true,
  "created_at": "2026-04-27"
}
```

---

## Phase 0 Complete When
- [ ] FreqTrade sends Telegram messages directly
- [ ] Trade Event Handler is active in N8N
- [ ] Whitelist has no suspicious tokens
- [ ] N8N has no dead workflows
- [ ] `users/user_01_gaurav.json` exists
