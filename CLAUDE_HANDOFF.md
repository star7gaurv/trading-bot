# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-01 ~18:05 IST  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

> Read this entire file before doing anything on the server.
> Complete tasks in ORDER.

---

## 📊 What Changed This Session

| # | What | File | Change |
|---|---|---|---|
| 1 | Strategy upgraded to v4 | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | Raised ML threshold, added 1h trend filter, tightened RSI |
| 2 | .gitignore updated | `.gitignore` | Backtest ZIPs, meta.json, logs now ignored |

### Why v4 was needed

Task 1.3 backtest (stoploss = -0.035) produced:
- Win rate: 60.3% ✅ — ML signal is working
- Sharpe: **-1.40** ❌ — 36 stoploss exits at avg -3.69% wiped all gains
- Profit factor: **0.54** ❌

Root cause: entries were firing in counter-trend moves on 15m. Positions got stopped out before the exit signal could catch up.

### Fixes in v4
1. **ML entry threshold raised**: `&-s_close > 0.008` → `> 0.012` (high-conviction only)
2. **1h macro trend filter added**: only enter if `1h close >= 1h EMA-50`
3. **RSI entry ceiling tightened**: `< 72` → `< 68` (avoid overbought entries)
4. **Stoploss unchanged at -0.035** (root cause was entry quality, not stoploss width)

---

## ✅ Step 1 — Pull Latest

```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
git pull origin gaurav
```

Verify the strategy is v4:
```bash
grep -n "freqai_lgbm_v4\|0.012\|ema_50_1h" freqtrade/user_data/strategies/FinBuddyFreqAI.py
# Must see: enter_tag = "freqai_lgbm_v4", threshold 0.012, and ema_50_1h column
```

---

## ✅ Step 2 — Clear Prediction Cache and Rerun Task 1.3 Backtest

> ⚠️ IMPORTANT: Clear the FreqAI prediction cache before running. Without this,
> FreqAI reuses cached .feather predictions and the new entry filters have no effect.

```bash
# Clear cached backtest predictions (not the trained models — those are fine)
rm -f freqtrade/user_data/models/*/predictions_backtest_*.feather 2>/dev/null || true
rm -f freqtrade/user_data/backtest_results/* 2>/dev/null || true

# Copy updated strategy into container
docker cp freqtrade/user_data/strategies/FinBuddyFreqAI.py \
  freqtrade:/freqtrade/user_data/strategies/FinBuddyFreqAI.py

# Run backtest
chmod +x scripts/run_backtest.sh
./scripts/run_backtest.sh
```

**Accept if ALL criteria pass:**
- Win rate > 50%
- Sharpe ratio > 0.5
- Max drawdown < 20%
- Profit factor > 1.2

**If PASS:**
1. Mark Task 1.3 ✅ in `tasks/phase-1-freqai-brain.md`
2. Update `strategies/registry.json` → `validated`
3. Add metrics to `finbuddy_memory/strategies/winners.md`
4. Proceed to Step 3 (Task 1.4)

**If FAIL:**
1. Log metrics + failure summary in `finbuddy_memory/strategies/graveyard.md`
2. Leave Task 1.3 as ⚠️
3. Do NOT change strategy code — leave that to Perplexity
4. Commit memory updates and push

---

## ✅ Step 3 — Task 1.4: Switch Dry-Run to FinBuddyFreqAI (only after 1.3 passes)

```bash
sed -i 's/AiGuardrailStrategy/FinBuddyFreqAI/' \
  /home/ubuntu/var/www/html/trade/freqtrade/docker-compose.yml
docker restart freqtrade
```

Verify via logs/UI:
- Strategy: `FinBuddyFreqAI`
- FreqAI model: `FinBuddyLLMModel`

---

## ✅ Step 4 — Phase 2 External Data (after Phase 1 fully green)

```bash
# Install dependency if missing
docker exec freqtrade pip install pytrends

# Test all fetchers end-to-end
docker exec freqtrade python /freqtrade/scripts/phase2/external_data_aggregator.py
```

Expect a JSON/print summary with all 5 sources OK.
Then set up a **cron job** (not AI loop) to run aggregator every 15 min.
Full commands in `tasks/phase-2-data-enrichment.md`.

---

## ✅ Step 5 — Phase 4 Memory Writer (after Phase 2 cron is live)

```bash
chmod +x scripts/phase4/setup_cron.sh
./scripts/phase4/setup_cron.sh

# Verify
crontab -l | grep memory_writer
tail -40 /tmp/finbuddy_memory_writer.log
```

---

## 🧠 Memory Update Pattern (mandatory after every task)

1. Update `finbuddy_memory/` with metrics, lessons, status.
2. Update `FINBUDDY_PROJECT_MEMORY.md` if phase status changed.
3. Commit and push.

---

*Updated by Perplexity AI — 2026-05-01 ~18:05 IST*
