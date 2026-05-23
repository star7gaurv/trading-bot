# Phase 10 — Live Capital Migration

> The go-live checklist. Moving from dry-run to real money on futures.
> Most consequential phase. Every item checked manually by Gaurav.

---

## Phase Status: ⛔ BLOCKED (as of 2026-05-18)

**Why blocked:**
- Walk-forward gate FAILED (v22, May 16): WR 21.2%, Sharpe -9.45, PF 0.54, -$2,302 — all 4 criteria miss
- Live v22 dry-run is +$107 (+10.86%) but only ~3 weeks old, single regime (BEAR)

**Two valid paths to unblock (either is sufficient):**

| Path | Criteria | Status |
|---|---|---|
| **A. Track record** | 60 days live dry-run + PF > 1.2 + survived a regime flip | 🟠 ~21 days in, BEAR only so far |
| **B. Brain-promoted variant** | Brain finds v23 variant profitable on BULL + BEAR + PF ≥ 1.2 → Telegram Apply button → swap → enters track record path | 🔴 0/3 (no positive v23 results yet, brain still searching) |

WF is no longer a gate — see `phase-1-freqai-brain.md` Task 1.3.

---

## ⚠️ HARD RULES FOR GO-LIVE

1. **Never go live without 30-day dry-run track record** — no exceptions
2. **Start with $100 USDT real capital** — not the full $1000
3. **Max 2% risk per trade** — hardcoded in risk engine (Phase 9)
4. **Daily loss limit: $10** (10% of $100 pilot) — circuit breaker must be live
5. **No manual overrides during first month** — let the system run
6. **Kill switch must work** before first real trade

---

## Task 10.1 — 30-Day Dry-Run Report
**Status:** ⬜ Pending

Before going live, generate a full performance report from the 30-day dry-run.

### Create: `scripts/dry_run_report.py`

Fetch from FreqTrade API and generate:
- Total trades, WR, PF, Sharpe, max DD
- Per-pair breakdown
- Regime distribution during period
- Circuit breaker trigger count (must be 0)
- Funding rate impact estimate

Pass criteria to proceed to live:
| Metric | Threshold |
|---|---|
| Win Rate | > 50% |
| Sharpe | > 0.3 (dry-run is noisier than backtest) |
| Max Drawdown | < 15% |
| Profit Factor | > 1.1 |
| Circuit Breaker Triggers | 0 |
| Days with > 5% daily loss | 0 |

If ANY criteria fail → do NOT go live. Fix and re-run 30 days.

---

## Task 10.2 — Kill Switch
**Status:** ⬜ Pending

One command to stop ALL trading instantly, close open positions, and send Telegram confirmation.

### Create: `scripts/kill_switch.sh`
```bash
#!/bin/bash
set -e
echo "🛑 KILL SWITCH ACTIVATED — $(date)" | tee -a /home/ubuntu/.finbuddy/logs/kill_switch.log

# Stop FreqTrade from opening new trades
curl -s -X POST -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/stopbuy
echo "New trade entries: BLOCKED"

# Cancel all open orders
curl -s -X POST -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/forceexit/all -H 'Content-Type: application/json' -d '{"ordertype": "market"}'
echo "All open positions: FORCE EXITED"

# Stop the container
docker stop freqtrade-futures
echo "FreqTrade futures container: STOPPED"

# Telegram alert
TOKEN="8557119080:AAH9KPMIZSGP7Gsn9wbJGVNaNRyEQHISR_o"
CHAT="5622292536"
curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" \
  -d chat_id="$CHAT" \
  -d text="🛑 FinBuddy KILL SWITCH activated. All positions closed. Container stopped. $(date)"

echo "Kill switch complete."
```

Test on dry-run BEFORE going live:
```bash
chmod +x scripts/kill_switch.sh
bash scripts/kill_switch.sh  # test on dry-run first
```

---

## Task 10.3 — Real Capital Config
**Status:** ⬜ Pending

Create a **separate live config** — do NOT modify dry-run config.

### File: `freqtrade/user_data/futures_live_config.json`

Key changes from dry-run config:
```json
{
  "dry_run": false,
  "stake_amount": 25,
  "max_open_trades": 4,
  "dry_run_wallet": 0,
  "trading_mode": "futures",
  "margin_mode": "isolated"
}
```

Total exposure: 4 × $25 × 3× leverage = $300 max exposure on $100 capital.
Risk per trade: $25 × 5% stoploss = $1.25 = 1.25% of $100 ✅

---

## Task 10.4 — Phased Capital Ramp
**Status:** ⬜ Pending

Do NOT put full capital in immediately. Ramp in 4 phases:

| Phase | Capital | Condition to proceed |
|---|---|---|
| Pilot | $100 USDT real | 30-day dry-run pass |
| Month 1 | $100 real, watch closely | 14 days live, no circuit breaker |
| Month 2 | $250 real | 30 days live, Sharpe > 0.2 |
| Month 3 | $500 real | 60 days live, Sharpe > 0.3, max DD < 10% |
| Full | $1000 real | 90 days live, consistent profitability |

Each step requires Gaurav's manual approval before capital increase.

---

## Task 10.5 — Go-Live Protocol (Day 1 Checklist)
**Status:** ⬜ Pending

Run through this list manually on go-live day:

```
PRE-FLIGHT CHECKLIST — LIVE TRADING DAY 1

SECURITY
[ ] Futures API key IP-whitelisted to REDACTED-SERVER_IP only
[ ] No withdrawal permissions on API key
[ ] .env file NOT committed to git (verify: git status)
[ ] All passwords changed from defaults (bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD → unique password)

RISK
[ ] Circuit breaker tested and confirmed working on dry-run
[ ] Kill switch tested on dry-run
[ ] Drawdown watchdog cron is ACTIVE (crontab -l | grep watchdog)
[ ] Funding rate monitor cron is ACTIVE
[ ] Daily loss limit = $10 confirmed in drawdown_watchdog.py

BOT STATE  
[ ] FreqTrade futures container on live config (futures_live_config.json)
[ ] FreqAI model trained on at least 500 candles per pair
[ ] HMM regime NOT in CRASH (check finbuddy_memory/regimes/current.json)
[ ] Pairlist has no blacklisted tokens

MONITORING
[ ] Telegram notifications firing (send /status to bot)
[ ] Memory writer cron running (check last CONTEXT.md timestamp)
[ ] Server disk > 20% free (df -h)
[ ] Server memory < 80% used (free -h)

CAPITAL
[ ] Starting with $100 USDT real only
[ ] Remaining capital in separate Binance sub-account (NOT in trading account)
[ ] Stake amount = $25 confirmed

ONCE LIVE
[ ] First trade notification received on Telegram ✓
[ ] Verified trade appears in FreqTrade UI with correct size
[ ] Confirmed leverage = 3× on first trade
```

---

## Task 10.6 — First-Month Monitoring Schedule
**Status:** ⬜ Pending

| Frequency | Check |
|---|---|
| Daily (5 min) | Open trades, daily P&L, circuit breaker status |
| Weekly (15 min) | WR, Sharpe, max DD vs dry-run baseline |
| Monthly (30 min) | Full performance report, decide capital ramp or hold |

Command for quick daily check from phone (Termius):
```bash
curl -s -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/profit | python3 -m json.tool | grep -E 'profit_all|trade_count|winning_trades|max_drawdown'
```

---

## Phase 10 Completion Checklist
- [ ] 30-day dry-run report generated and passed all criteria
- [ ] Kill switch tested and confirmed working
- [ ] Live config created with `dry_run: false` and $25 stake
- [ ] Pre-flight checklist completed and signed off
- [ ] First real trade executed and confirmed on Telegram
- [ ] 14-day live soak complete with no circuit breaker triggers

---

## 🔗 Related Files
- [[CLAUDE]] ← infra, credentials, server config
- [[FINBUDDY_PROJECT_MEMORY]] ← master hub, overall vision
- [[tasks/phase-9-futures-risk]] ← prerequisite risk engine
- [[tasks/phase-8-futures-setup]] ← futures account setup
- `users/user_01_gaurav.json` ← user config with capital settings
- [[finbuddy_memory/regimes/current]] ← must not be CRASH on go-live
- [[docs/ADR-001-multi-tenant-architecture]] ← eventual SaaS vision
