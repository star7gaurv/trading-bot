# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-01 ~18:30 IST  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

> Read this entire file before doing anything on the server.
> Complete tasks in ORDER. Do not skip ahead.

---

## 📊 What Changed This Session

| # | What | File | Status |
|---|---|---|---|
| 1 | Strategy v4 | `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | ✅ In repo |
| 2 | Automated grid search | `scripts/autobacktest.py` | ✅ In repo — run this |
| 3 | Parameter grid | `scripts/autobacktest_grid.json` | ✅ In repo |
| 4 | Scripts docs | `scripts/README.md` | ✅ Updated |
| 5 | .gitignore | `.gitignore` | ✅ Backtest artifacts now excluded |

---

## ✅ Step 1 — Pull Latest

```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
git pull origin gaurav
```

Verify the new files exist:
```bash
ls scripts/autobacktest.py
ls scripts/autobacktest_grid.json
```

---

## ✅ Step 2 — Run Automated Grid Search (Task 1.3)

> This replaces the manual backtest → tweak → repeat loop.
> The script tests 12 parameter combinations automatically.
> Run it in tmux so it survives session disconnects.

```bash
tmux new -s autobacktest
python3 scripts/autobacktest.py
# Detach: Ctrl+B then D
# Reattach later: tmux attach -t autobacktest
```

The script handles:
- Patching `FinBuddyFreqAI.py` per combo
- Clearing FreqAI prediction cache between runs
- Running `run_backtest.sh`
- Parsing metrics
- Logging to `_autobacktest_results.csv`
- Restoring original strategy file when done

Estimated runtime: **1–3 hours** depending on server speed.

---

## ✅ Step 3 — After Grid Search Completes

### If a WINNER was found:
1. Commit `_autobacktest_results.csv`
2. Add winner params + metrics to `finbuddy_memory/strategies/winners.md`
3. Update `tasks/phase-1-freqai-brain.md` — Task 1.3 status: ⚠️ NEEDS PERPLEXITY REVIEW
4. Update `FINBUDDY_PROJECT_MEMORY.md` current state table
5. Push all changes to `gaurav`

### If NO winner found:
1. Commit `_autobacktest_results.csv`
2. Add all combos + metrics to `finbuddy_memory/strategies/graveyard.md`
3. Leave Task 1.3 as ⚠️
4. Push and wait for Perplexity to expand the grid

---

## ✅ Step 4 — Task 1.4: Switch Dry-Run (only after Perplexity marks 1.3 ✅)

Do NOT proceed to this step until Perplexity reviews the CSV and confirms.

```bash
sed -i 's/AiGuardrailStrategy/FinBuddyFreqAI/' \
  /home/ubuntu/var/www/html/trade/freqtrade/docker-compose.yml
docker restart freqtrade
```

Verify:
- Strategy: `FinBuddyFreqAI`
- FreqAI model: `FinBuddyLLMModel`

---

## ✅ Step 5 — Phase 2 + Phase 4 (after Phase 1 fully confirmed by Perplexity)

Phase 2 and Phase 4 setup is cron-based. Full commands in:
- `tasks/phase-2-data-enrichment.md`
- `scripts/README.md`

Brief:
```bash
# Phase 2: test fetchers, then install cron
docker exec freqtrade pip install pytrends
docker exec freqtrade python /freqtrade/scripts/phase2/external_data_aggregator.py
# Then follow phase-2 task file for cron install

# Phase 4: one-time cron install
chmod +x scripts/phase4/setup_cron.sh
./scripts/phase4/setup_cron.sh
```

---

## 🧠 Memory Update Pattern (mandatory after every task)

1. Update `finbuddy_memory/` with metrics, lessons, decisions.
2. Update `FINBUDDY_PROJECT_MEMORY.md` if phase status changed.
3. Commit and push to `gaurav`.

---

*Updated by Perplexity AI — 2026-05-01 ~18:30 IST*
