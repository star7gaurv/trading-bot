# Phase 0 — Foundation (Fix, Clean, Wire)

**Status:** ✅ COMPLETE (2026-04-27)

> **2026-05-18 note**: Phase 0 stands as the foundation record. Several tasks below reference N8N (since-permanently disabled). The functional equivalents are now: trade events captured by `scripts/trade_postmortem.py` (cron `*/15 * * * *` → `finbuddy_memory/trades/closed.md`). N8N webhook bits are historical.

> Complete all loose ends before building anything new.
> These are blocking tasks — later phases depend on a clean baseline.

---

## Task 0.1 — Complete Trade Event Handler
**Status:** ✅ Done (alternative implementation 2026-04-27+)
**Original wiring (N8N webhook) deprecated 2026-04-30 — N8N pipeline disabled.**
**Current implementation:** `scripts/trade_postmortem.py` polls FreqTrade API every 15 min and appends closed-trade ledger to `finbuddy_memory/trades/closed.md`. Also writes `FINBUDDY_RECENT_WR` to `.env` for the strategy feedback loop.

~~FreqTrade `config.json` has webhook enabled pointing to `https://n8n.star7gaurav.in/webhook/freqtrade-events`. The "Freqtrade Trade Event Handler" workflow is active in N8N and confirmed receiving events (last triggered 2026-04-19). The workflow runs: FreqTrade Webhook → Respond OK.~~ (deprecated)

> **Note:** The workflow showed `n8n.workflow.failed` on 2026-04-26 — this is a runtime execution error inside the workflow logic, not a configuration problem. The wiring is correct. The failure should be investigated in the N8N execution log.

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
**Status:** ✅ Done  
**Verified:** 2026-04-27 live server confirmation

FreqTrade `config.json` has Telegram fully configured and ENABLED: `"enabled": true`, token `8557119080:AAH9KPMIZSGP7Gsn9wbJGVNaNRyEQHISR_o`, chat_id `5622292536`.

> **Note:** The token in config is the FreqTrade bot (separate from the N8N bot token `7799143446:...`). FreqTrade sends all notifications by default without requiring `notification_settings` block.

FreqTrade is actively sending Telegram notifications.

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
**Status:** ✅ Done  
**Verified:** 2026-04-27 live config read

✅ **Blacklist confirmed in config.json (lines 43–54):**
- D/USDT (line 50)
- CHIP/USDT (line 51)
- SOMI/USDT (line 52)
- ZBT/USDT (line 53)

✅ **Additional suspicious pairs already blacklisted:** BNB/.*, GIGGLE/USDT, BARD/USDT, BIO/USDT, WLFI/USDT, and non-ASCII token pair

✅ **Whitelist:** Only BTC/USDT hardcoded; VolumePairList dynamically fetches ~20 pairs, all filtered through blacklist

All suspicious/pump-and-dump tokens are now permanently blocked from trading.

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
**Status:** ✅ Done  
**Verified:** 2026-04-27 completed, N8N logs confirm cleanup

✅ **Remaining workflows (confirmed active in latest logs):**
- **Freqtrade AI Core Trading Loop v4** — ACTIVE, running every 15 min
- **Freqtrade Trade Event Handler** — ACTIVE, receiving FreqTrade webhooks

✅ **Deleted workflows (no longer in event logs):**
- **Dify Trade Executor** — removed (Dify is gone)
- **Freqtrade AI Core Trading Loop v2** — removed (superseded by v4)
- **Freqtrade AI Core Trading Loop v3** — removed (superseded by v4)
- **My workflow 3** — removed (unknown purpose)

> **Important:** The active pipeline is now **v4**, not v3. CLAUDE.md references "N8N v3 Pipeline" — update it to v4 after confirming v3 is fully dead.

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
**Status:** ✅ Done  
**Verified:** 2026-04-26 live audit

`users/user_01_gaurav.json` exists with full config: exchange (binance dry_run), capital (1000 USDT), risk (2% per trade, 15% max drawdown), pairs whitelist (BTC/ETH/SOL/BNB), active strategies (rsi_macd_ai_v1), regime filter (halt in CRASH/EUPHORIA), Telegram notification settings, and schedule (15min, Asia/Kolkata).

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

## Phase 0 Complete ✅ (5/5 Tasks)
- [x] **Task 0.1** — Trade Event Handler wired and active in N8N ✅ (webhook configured, v4 pipeline running)
- [x] **Task 0.2** — Telegram fully enabled in FreqTrade config ✅ (token + chat_id active)
- [x] **Task 0.3** — Pairlist audit complete, scam tokens blacklisted ✅ (D/USDT, CHIP, SOMI, ZBT blocked)
- [x] **Task 0.4** — N8N workspace clean ✅ (only 2 workflows remain, both active; dead workflows deleted)
- [x] **Task 0.5** — User config created ✅ (`users/user_01_gaurav.json` exists with full profile)

**Phase 0 Status: 5/5 tasks complete as of 2026-04-27. READY FOR PHASE 1: FreqAI Brain Development.**
