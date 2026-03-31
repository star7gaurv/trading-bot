# AI Crypto Trading Bot — Session Log
**Date:** March 31 – April 1, 2026 
**Server:** `ubuntu@gaurav-instance` (Oracle Free Tier, 140.245.17.121) 
**Repo:** https://github.com/star7gaurv/trading-bot

---

## Session Goals
1. Remove Dify completely and clean up the server
2. Fix FreqTrade (wrong strategy, broken API, config issues)
3. Get OpenClaw running and identify how N8N will call it
4. Move toward dry run readiness

---

## Starting State (before this session)

| Component | Status | Notes |
|---|---|---|
| Server | ✅ Running | Oracle Free Tier, 24GB RAM, 4 vCPUs |
| FreqTrade | ⚠️ Partial | API pinging but `show_config` returning 25 bytes |
| N8N | ✅ Running | `n8n.star7gaurav.in`, port 5678 |
| OpenClaw | ❌ Down | Installed but process not running, 502 on `jack.star7gaurav.in` |
| Dify | 🗑️ To Remove | Still running as Docker containers despite being "dropped in Feb 2026" |
| Strategy | ❌ Missing | `AI_Hybrid_Strategy.py` didn't exist; `SampleStrategy` was loading |
| Integration Test | ❌ 0% | Nothing end-to-end tested |

---

## Task 1 — Remove Dify

### Problem
Dify was still running as 9 Docker containers despite being officially dropped from the project.

### Steps Taken
```bash
cd ~/var/www/html/trade/dify
docker-compose down -v
# All 9 containers + 2 networks removed cleanly

docker rmi langgenius/dify-api:latest \
 langgenius/dify-web:latest \
 langgenius/dify-plugin-daemon:0.4.1-local \
 langgenius/dify-sandbox:latest \
 semitechnologies/weaviate:1.27.0

sudo rm -rf ~/var/www/html/trade/dify/
```

### Result
- All Dify containers, images, networks, volumes removed ✅
- Disk usage dropped from **53.4% → 39%** (freed ~6GB) ✅
- FreqTrade was accidentally stopped during cleanup — restarted with `docker start freqtrade` ✅

### Git Commit
```
remove: dify fully dropped, replaced by openclaw
```

---

## Task 2 — Fix Git Remote

### Problem
`git push` was failing — no remote was configured.

### Fix
```bash
git remote add origin git@github.com:star7gaurv/trading-bot.git
git push -u origin master
```

### Also Fixed .gitignore
Added rules to stop committing logs, SQLite databases, binary data files:
```
freqtrade/user_data/logs/
freqtrade/user_data/data/
freqtrade/user_data/tradesv3.sqlite*
freqtrade/user_data/notebooks/
```

Removed already-committed files from tracking:
```bash
git rm -r --cached freqtrade/user_data/logs/ freqtrade/user_data/data/ \
 freqtrade/user_data/notebooks/
git rm --cached freqtrade/user_data/tradesv3.sqlite*
```

---

## Task 3 — Fix FreqTrade

### Problem 1: `show_config` returning 25 bytes (same as ping)
**Root cause:** API credentials `bot:bot123` were not set in `config.json`. The old config had no `username`/`password` in the `api_server` block.

**Fix:**
```python
c['api_server'] = {
 'enabled': True,
 'listen_ip_address': '0.0.0.0',
 'listen_port': 8080,
 'username': 'bot',
 'password': 'bot123',
 ...
}
```

---

### Problem 2: FreqTrade loading `SampleStrategy` instead of `AiGuardrailStrategy`
**Root cause:** `docker-compose.yml` had `--strategy SampleStrategy` hardcoded in the `command:` block — this overrides anything in `config.json`.

**Fix:**
```bash
sudo sed -i 's/--strategy SampleStrategy/--strategy AiGuardrailStrategy/' \
 ~/var/www/html/trade/freqtrade/docker-compose.yml
```

---

### Problem 3: `AiGuardrailStrategy.py` syntax error on line 88
**Root cause:** Backslash escapes inside f-string `{}` expressions are not allowed in Python < 3.12. The FreqTrade container runs an older Python version.

**Offending line:**
```python
# BAD — backslash escapes inside f-string braces
logger.warning(f"AI Trade Rejected: {pair} RSI is {last_candle[\"rsi\"]} (Too overbought).")
```

**Fix:** Rewrote all f-strings to use single quotes on the outside:
```python
# GOOD
logger.warning(f'AI Trade Rejected: {pair} RSI is {last_candle["rsi"]} (Too overbought).')
```

---

### Problem 4: Config values were wrong
The Python script that rewrote `config.json` for API credentials reset `strategy` back to default.

**Final correct config values:**
```json
{
 "strategy": "AiGuardrailStrategy",
 "strategy_path": "user_data/strategies",
 "stoploss": -0.03,
 "dry_run": true,
 "dry_run_wallet": 1000,
 "max_open_trades": 4,
 "stake_amount": 200
}
```

---

### Final FreqTrade Verification
```
docker logs freqtrade --tail 5:
 *Strategy:* `AiGuardrailStrategy`
 *Stake per trade:* `200 USDT`
 *Trailing Stoploss:* `-0.03`
 Dry run is enabled. All trades are simulated.
 Whitelist with 20 pairs loaded from Binance.
```

**FreqTrade status: ✅ FULLY WORKING**

---

## Task 4 — Fix OpenClaw

### Discovery
OpenClaw is installed via npm globally (`~/.npm-global/bin/openclaw`) and runs as `openclaw-gateway` on port **18789** (UI) and **18791** (ACP bridge).

Nginx config maps `jack.star7gaurav.in` → `http://127.0.0.1:18789`

### Problem 1: Process was dead after `pkill`
OpenClaw process was killed during restart attempt, causing 502.

**Fix:**
```bash
npm install -g openclaw --prefix ~/.npm-global # reinstall (binary was missing)
~/.npm-global/bin/openclaw > /dev/null & # restart
```

### Problem 2: Version was outdated (v2026.3.23-2)
```bash
npm update -g openclaw --prefix ~/.npm-global
# Updated to v2026.3.28
```

### Startup persistence
OpenClaw is NOT managed by systemd or pm2 — it needs a crontab entry for reboot survival:
```bash
(crontab -l 2>/dev/null; echo "@reboot ~/.npm-global/bin/openclaw > ~/.openclaw/logs/startup.log 2>&1") | crontab -
```
> ⚠️ **This was identified but not yet applied — still TODO**

---

## Task 5 — Identify OpenClaw ↔ N8N Integration Method

### Discovery: OpenClaw uses WebSocket (not REST)
Port 18789 serves the web UI (HTML). Port 18791 is the ACP WebSocket bridge. 
All HTTP curl attempts to `18791/api/agent` returned empty or "Not Found".

The `openclaw acp` command is a WebSocket client — N8N cannot call it via standard HTTP Request node.

### Decision: N8N calls OpenRouter directly
The `openclaw.json` config already has a working **OpenRouter API key** configured:
```
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
```

This is a standard REST API — ideal for N8N HTTP nodes.

### N8N analyze_market HTTP Node Configuration

**URL:** `https://openrouter.ai/api/v1/chat/completions` 
**Method:** POST 
**Headers:**
```
Authorization: Bearer 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
Content-Type: application/json
```

**Body:**
```json
{
 "model": "deepseek/deepseek-v3",
 "max_tokens": 200,
 "messages": [
 {
 "role": "system",
 "content": "You are a crypto trading signal analyzer. Respond with ONLY valid JSON, no markdown, no explanation. Format: {\"signal\":\"BUY\"|\"SELL\"|\"HOLD\",\"confidence\":0-100,\"reason\":\"one sentence\",\"risk\":\"low\"|\"medium\"|\"high\"}"
 },
 {
 "role": "user",
 "content": "Pair: {{$json.pair}}\nRSI(14): {{$json.rsi}}\nMACD Histogram: {{$json.macd_hist}}\nEMA9: {{$json.ema9}}\nEMA21: {{$json.ema21}}\nVolume spike: {{$json.volume_spike}}\nPrice above EMA200: {{$json.price_vs_ema200}}"
 }
 ]
}
```

**Expected response:**
```json
{"signal": "BUY", "confidence": 72, "reason": "EMA golden cross with RSI in neutral zone", "risk": "low"}
```

> ⚠️ **Test curl not yet confirmed — still pending as of session end**

---

## Git Commits This Session

| Commit | Message |
|---|---|
| `9a5d11e` | remove: dify fully dropped, replaced by openclaw |
| `2801b65` | chore: ignore logs, data, sqlite, notebooks |
| `39a9f65` | fix: stoploss -0.03, wallet 1000 USDT, max_trades 4, stake 200, api creds |
| `082c0bc` | fix: strategy syntax error fixed, AiGuardrailStrategy loading cleanly |
| `4832890` | fix: config.json - bot creds, strategy, stoploss, wallet, stake |

---

## End-of-Session Status

| Component | Status | Notes |
|---|---|---|
| Server | ✅ Done | Disk 39%, clean |
| FreqTrade | ✅ Done | AiGuardrailStrategy, dry_run, 1000 USDT wallet |
| Git | ✅ Done | Remote set, .gitignore clean, all pushed |
| OpenClaw | ✅ Running | v2026.3.28, port 18789, UI accessible at jack.star7gaurav.in |
| Dify | ✅ Removed | All containers, images, volumes gone |
| N8N | ⏳ Next | Market Signal Pipeline not built yet |
| OpenRouter test | ⏳ Next | Curl test pending |
| Dry Run | ❌ Not started | Blocked on N8N pipeline |

---

## Next Session — What To Do First

1. **Confirm OpenRouter curl test works** (paste result from last command)
2. **Add OpenClaw to crontab** so it survives reboots
3. **Build N8N Market Signal Pipeline** (15-min cron → Binance OHLCV → OpenRouter → IF confidence > 65 → FreqTrade forcebuy)
4. **Build N8N Trade Event Handler** (FreqTrade webhook → Telegram)
5. **Run end-to-end integration test** using the checklist

---

## Key Credentials Reference

| Service | Credential | Value |
|---|---|---|
| FreqTrade API | username | `bot` |
| FreqTrade API | password | `bot123` |
| FreqTrade API | URL | `http://localhost:8080/api/v1` |
| OpenClaw UI | URL | `https://jack.star7gaurav.in` |
| OpenClaw port | local | `http://localhost:18789` |
| OpenRouter | API key | `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` |
| N8N | URL | `https://n8n.star7gaurav.in` |
| N8N | local port | `5678` |
| GitHub | repo | `git@github.com:star7gaurv/trading-bot.git` |