# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-03  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

> This file is the **live action queue** for Claude Code. It should always reflect
> the **next concrete ops steps** on the server, assuming the repo is already
> up to date. Older backtest detail and v10 walk-forward history is now
> captured in `CLAUDE.md` and `FINBUDDY_PROJECT_MEMORY.md`.

---

## ✅ Current State (May 4 2026 PM — Claude Code)

- v11.2 live in docker, Binance futures connected (dry-run), FinBuddyFreqAI v11 loaded
- RiskEngine wired into custom_stake_amount: regime-aware stake sizing active (NEUTRAL → 0.75×)
- label_period_candles=12 in both config.json and backtest_config.json
- ml_threshold grid extended to [0.50, 0.55, 0.60, 0.65, 0.70] (90 total combos)
- finbuddy_memory/regimes/ bind-mounted into container at /freqtrade/finbuddy_memory/regimes/
- Bull grid running: BACKTEST_TIMERANGE=20240101-20250101, PID 327995, /tmp/bull_futures_backtest.log
- Pending: walk-forward result from current grid, Phase 10 go-live decision

---

## ✅ What’s Already Done On Server (From Previous Session — 2026-05-03)

You reported the following in your **FINAL REPORT (2026-05-03)**:

1. **FreqTrade Container Status**  
   - ✅ RUNNING — container up for ~29 hours  
   - `FinBuddyFreqAI` **v11** loaded  
   - Accepting API calls on port 8080

2. **Crontab (core automation)**  
   These jobs are installed and live:
   ```cron
   */15 * * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/fetch_all_external.py >> /home/ubuntu/.finbuddy/logs/data_fetcher.log 2>&1
   0 */4 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/hmm_regime_detector.py >> /home/ubuntu/.finbuddy/logs/hmm_regime.log 2>&1
   */15 * * * * python3 /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/memory_writer.py && bash /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/git_commit.sh >> /home/ubuntu/.finbuddy/logs/memory_writer.log 2>&1
   0 2 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/karpathy/run_loop.py >> /home/ubuntu/.finbuddy/logs/karpathy.log 2>&1
   */5 * * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/executor/executor.py >> /home/ubuntu/.finbuddy/logs/executor.log 2>&1
   ```

3. **Executor `/health`**  
   - ✅ `Executor OK: 0 signals processed (DB initialized and functional)` — schema OK, no signals yet

4. **TradingView Webhook `/health`**  
   - ⚠️ **Receiver file exists but NOT running**  
   - `freqtrade/user_data/scripts/tradingview/webhook_receiver.py` created  
   - FastAPI/uvicorn not installed on server → `/tradingview/health` behind Nginx returns 502

5. **Phases 0–7**  
   - ✅ All 7 phases in `tasks/TASKS.md` marked as **complete or deployed** as per your report  
   - The only partial is **Phase 6** (TradingView): app file written, but dependencies missing and process not started

This handoff assumes all of the above is still true at the start of your next session.

---

## 📌 Your Next Actions (In Order)

### 1. Sync Repo & Read Context

```bash
cd /home/ubuntu/var/www/html/trade
git pull origin gaurav
```

Then skim these files (they have been updated to reflect your last session):
- `CLAUDE.md` — master project context
- `FINBUDDY_PROJECT_MEMORY.md` — high-level status (now includes Phases 8–10 and your crontab)
- `tasks/TASKS.md` — authoritative phase list + statuses
- `tasks/phase-6-tradingview.md` — detailed TradingView plan

You do **not** need to re-read the huge historical backtest sections — those are for Perplexity.

---

### 2. Fix Phase 6: Start TradingView Webhook Service

Goal: get `/tradingview/health` returning 200 OK via Nginx.

#### 2.1 Install FastAPI + uvicorn (if not installed)

```bash
cd /home/ubuntu/var/www/html/trade
pip install fastapi uvicorn --break-system-packages
```

You can verify with:
```bash
python3 -c "import fastapi, uvicorn; print('fastapi version', fastapi.__version__)"
```

#### 2.2 Start the webhook receiver

```bash
cd /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/tradingview
nohup uvicorn webhook_receiver:app --host 0.0.0.0 --port 9999 --log-level warning \
  >> /home/ubuntu/.finbuddy/logs/tradingview_webhook.log 2>&1 &

sleep 3
curl -s http://localhost:9999/health
```

You should see a small JSON with a `status` field. If it errors, check the log file.

#### 2.3 Ensure it starts on reboot

You already added an `@reboot` cron line when the file was created. Verify it exists:

```bash
crontab -l | grep tradingview || echo "No tradingview @reboot cron found"
```

If missing, add:
```bash
(crontab -l 2>/dev/null; echo "@reboot cd /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/tradingview && uvicorn webhook_receiver:app --host 0.0.0.0 --port 9999 --log-level warning >> /home/ubuntu/.finbuddy/logs/tradingview_webhook.log 2>&1 &") | crontab -
```

#### 2.4 Verify Nginx proxy

There should already be a `location /tradingview` block in the relevant site config pointing to `http://127.0.0.1:9999`. Sanity check:

```bash
grep -R "tradingview" -n /etc/nginx/sites-available
nginx -t && sudo systemctl reload nginx
curl -s https://trade.star7gaurav.in/tradingview/health
```

If the last curl returns JSON with 200 OK, Phase 6 is now **fully live**.

Update status:
- `tasks/phase-6-tradingview.md` → mark webhook tasks as ✅
- `tasks/TASKS.md` → Phase 6 `⚠️ Partial` → `✅ Live`

Commit:
```bash
cd /home/ubuntu/var/www/html/trade
git add tasks/phase-6-tradingview.md tasks/TASKS.md
git commit -m "phase6: TradingView webhook receiver live"
git push origin gaurav
```

---

### 3. Light Sanity Checks on All Crons

Do a quick one-pass check that each cron’s output looks healthy — **no deep dive**, just spot-check:

```bash
tail -n 20 /home/ubuntu/.finbuddy/logs/data_fetcher.log
tail -n 20 /home/ubuntu/.finbuddy/logs/hmm_regime.log
tail -n 20 /home/ubuntu/.finbuddy/logs/memory_writer.log
tail -n 20 /home/ubuntu/.finbuddy/logs/karpathy.log
tail -n 20 /home/ubuntu/.finbuddy/logs/executor.log
```

If any script is erroring repeatedly (stack traces, ImportError, etc.):
- Fix only **obvious** issues (missing pip packages, bad paths)
- Re-run that script once manually to confirm it completes without exceptions
- Leave complex logic/strategy issues to Perplexity to change in the repo

If everything looks clean, you don’t need to touch anything else here.

---

### 4. Confirm FreqTrade v11 Health (Quick Smoke Test)

A short health check on the live bot:

```bash
curl -s -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/status | python3 -m json.tool | head -40
curl -s -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/profit | python3 -m json.tool | grep -E "profit_all|trade_count|winning_trades|max_drawdown"
```

You’re checking for:
- API responds quickly
- No obvious error messages in the JSON
- `dry_run` true, `trade_count` reasonable, `max_drawdown` small

No further changes needed here unless you see clear red flags.

---

### 5. If You Have Extra Budget — Tag the Current State in Git

Optional but nice: create a lightweight git tag for this “infra-complete” milestone:

```bash
cd /home/ubuntu/var/www/html/trade
git tag -a v0.7-infra-complete -m "Phases 0-7 wired; executor + memory + regimes + research live"
git push origin v0.7-infra-complete
```

This gives us a stable reference point before any future label/strategy changes.

---

## 🧠 What NOT To Do in This Session

- Do **not** run new long backtests, walk-forward jobs, or hyperopt unless explicitly added to this file by Perplexity.
- Do **not** modify strategy logic (`FinBuddyFreqAI.py`) or FreqAI models on your own.
- Do **not** touch `finbuddy_memory/` contents manually — they are now owned by cron scripts.

Your job for this session is **ops & verification only**:
- Get the TradingView webhook service running
- Sanity-check the existing crons and v11 health
- Update phase/task statuses accordingly

Anything that looks like “research” or “strategy design” belongs to Perplexity and will show up here in a future revision of this file.

---

*End of handoff — 2026-05-03. When you finish these steps, commit any status/README updates you make so Perplexity sees them next session.*
