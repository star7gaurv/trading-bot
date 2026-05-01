# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-01 ~15:50 IST  
**For:** Claude Code (next session after usage reset)  
**Branch:** `gaurav`

> Read this entire file before doing anything on the server.
> Complete tasks in ORDER. Delete this file only after all steps are done.

---

## 📊 What Perplexity Built / Changed This Session

| # | What | Files | Status |
|---|---|---|---|
| 1 | FinBuddyLLMModel (Task 1.2) | `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | ✅ Deployed earlier by you — now assumed live |
| 2 | **Stoploss tuning for Task 1.3** | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | ⚠️ Needs backtest rerun |
| 3 | Backtest runner (Task 1.3) | `scripts/run_backtest.sh`, `scripts/backtest_config.json`, `scripts/parse_backtest.py` | ⚠️ Re-run after stoploss change |
| 4 | Phase 2 data fetchers | `scripts/phase2/*.py` | ⚠️ Install cron after Phase 1 passes backtest |
| 5 | Phase 4 memory writer | `scripts/phase4/memory_writer.py`, `scripts/phase4/setup_cron.sh` | ⚠️ Install cron after Phase 2 live |

**Key change:** Stoploss in `FinBuddyFreqAI` was loosened from **-3% to -3.5%** to address a failed backtest (Sharpe -1.58 with too-tight stoploss). You must rerun Task 1.3 backtest with this updated strategy.[see commit message]

---

## ✅ Step 1 — Pull Latest
```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
git pull origin gaurav
```

Verify these files exist and are up to date:
```bash
ls user_data/freqaimodels/FinBuddyLLMModel.py    # Task 1.2
ls freqtrade/user_data/strategies/FinBuddyFreqAI.py  # stoploss now -0.035
ls scripts/run_backtest.sh                        # Task 1.3
ls scripts/phase2/external_data_aggregator.py    # Phase 2
ls scripts/phase4/memory_writer.py               # Phase 4
```

Open the strategy and confirm:
```bash
grep -n "stoploss" freqtrade/user_data/strategies/FinBuddyFreqAI.py
# Expect: stoploss = -0.035  (with comment about Sharpe -1.58)
```

---

## ✅ Step 2 — Rerun Task 1.3 Backtest (with new stoploss)

From the project root:
```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
chmod +x scripts/run_backtest.sh
./scripts/run_backtest.sh
```

The script should:
1. Ensure data is downloaded for the configured pairs
2. Run backtest for `FinBuddyFreqAI` + `FinBuddyLLMModel`
3. Call `scripts/parse_backtest.py` and print PASS/FAIL with metrics

**Accept the backtest if ALL of these hold:**
- Win rate > 50%
- Sharpe ratio > 0.5
- Max drawdown < 20%
- Profit factor > 1.2

If the test **still fails** (for example Sharpe < 0.5):
- Capture the printed metrics and the worst-loss trades
- Update `finbuddy_memory/strategies/graveyard.md` or a new note under `finbuddy_memory/strategies/` with:
  - Date
  - Stoploss value
  - 4 metrics
  - Short explanation of failure (e.g. "too many small losses", "rare big losers")

If the test **passes**:
1. Mark Task 1.3 as ✅ COMPLETE in `tasks/phase-1-freqai-brain.md`
2. Update `strategies/registry.json` and set this strategy to `validated` as described in that task file
3. Add a short line to `finbuddy_memory/strategies/winners.md` with the date + metrics

---

## ✅ Step 3 — Task 1.4: Switch Dry-Run Strategy (if 1.3 passed)

Only do this after Task 1.3 is marked ✅.

```bash
sed -i 's/AiGuardrailStrategy/FinBuddyFreqAI/' \
  /home/ubuntu/var/www/html/trade/freqtrade/docker-compose.yml
docker restart freqtrade
```

Then verify via UI / logs that:
- Dry-run is running `FinBuddyFreqAI`
- FreqAI shows `FinBuddyLLMModel` as the active freqaimodel

---

## ✅ Step 4 — Phase 2 External Data (after Phase 1 fully complete)

```bash
# Install dependencies inside container (if not already)
docker exec freqtrade pip install pytrends

# Test all fetchers
docker exec freqtrade python /freqtrade/scripts/phase2/external_data_aggregator.py
```

Expect a JSON/print summary with all 5 sources. If all are OK:
- Create a cron entry (or systemd timer) that runs the aggregator every 15 minutes and writes results to wherever `FinBuddyLLMModel` / FreqAI expects the features file.

> Note: Phase 2 cron install details are in `tasks/phase-2-data-enrichment.md`. Follow that file for exact commands once Phase 1 is validated.

---

## ✅ Step 5 — Phase 4 Memory Writer (after Phase 2 cron running)

Use the provided script:
```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
chmod +x scripts/phase4/setup_cron.sh
./scripts/phase4/setup_cron.sh
```

Then verify:
```bash
crontab -l | grep memory_writer
tail -40 /tmp/finbuddy_memory_writer.log
```

You should see vault updates every 15 minutes and new entries under `finbuddy_memory/`.

---

## 🧠 Reminder: Memory Update Pattern

Whenever you complete or change anything substantial (deploy, fix, tune):
1. Update the relevant memory files under `finbuddy_memory/` (status, bugs, lessons)
2. Update `FINBUDDY_PROJECT_MEMORY.md` summary if phase status changed
3. Commit and push so Perplexity and future you have an accurate snapshot

This is **not optional** — it's part of "done" for every task.

---

## 🗑️ Delete This File When Fully Done

After Task 1.3 passes, Phase 1 is marked complete, and Phase 2/4 cron are installed:

```bash
git rm CLAUDE_HANDOFF.md
git commit -m "chore: remove handoff — all steps complete"
git push origin gaurav
```

---

*Updated by Perplexity AI — 2026-05-01 ~15:50 IST*
