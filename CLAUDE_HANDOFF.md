# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-01 ~01:00 IST  
**For:** Claude Code (next session after usage reset at 2:40 AM IST)  
**Branch:** `gaurav`

> **READ THIS FIRST** before doing anything on the server.
> This file tells you exactly what Perplexity AI did while you were rate-limited,
> what needs your review, and what to do next. Delete this file after you’ve completed the handoff tasks.

---

## 📦 What Perplexity AI Did (Code Written, NOT Deployed)

### Task 1.2 — FinBuddyLLMModel.py
**Status: ⚠️ NEEDS REVIEW + DEPLOYMENT**  
**Commit:** [55848d7](https://github.com/star7gaurv/trading-bot/commit/55848d79305557914a5ef72f68dfad56d283f422)  
**File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py`

Perplexity wrote the `FinBuddyLLMModel` custom FreqAI model. It has **NOT been pulled to the server, NOT been deployed, NOT been tested**. The file only exists in GitHub.

**What the code does:**
```
Market data + indicators
        ↓
  LightGBM predict() [inherited from LightGBMRegressor]
        ↓
  If abs(&-s_close prediction) > 0.006 AND per-pair cooldown elapsed:
    → Call Groq Llama 3.3 70B with market context
    → Parse response: CONFIRM / REJECT / HOLD
    → Final signal = LightGBM * 0.60 + LightGBM * multiplier * 0.40
      CONFIRM multiplier = 1.30  (amplify)
      REJECT  multiplier = 0.15  (near-zero)
      HOLD    multiplier = 0.50  (dampen)
  Else:
    → Raw LightGBM signal used unchanged
```

**Safety features already in the code:**
- 4-second Groq timeout (never blocks a trade decision)
- 60-min per-pair cooldown (rate limit protection)
- Graceful fallback on any Groq error → LightGBM signal used as-is
- 429 rate limit → auto-extends cooldown to 2 hours
- Works if `requests` library is missing (disables LLM silently)
- Works if `GROQ_API_KEY` env var is missing (disables LLM, logs warning)

---

## ✅ Your Job — Step by Step

### Step 1: Review the code
```bash
# Read the file Perplexity wrote
cat /home/ubuntu/var/www/html/trade/freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py
# (after git pull below)
```
Check for:
- Any FreqAI API incompatibilities with current `develop_freqai` image version
- Correct base class import (`LightGBMRegressor` path may differ in your version)
- Any syntax issues

### Step 2: Pull the latest code
```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
git pull origin gaurav
```

### Step 3: Verify the file exists
```bash
ls -la user_data/freqaimodels/
# Should show: FinBuddyLLMModel.py
```

### Step 4: Add GROQ_API_KEY to docker-compose.yml
```bash
# Open and add under freqtrade service > environment:
nano docker-compose.yml

# Add this line under environment:
#   - GROQ_API_KEY=gsk_your_actual_key_here

# Get key from: https://console.groq.com
# Gaurav already has a Groq account and key
```

### Step 5: Ensure freqaimodels volume is mounted
```bash
# Check if freqaimodels is in volumes section of docker-compose.yml
grep -n 'freqaimodels' docker-compose.yml

# If NOT present, add this line under volumes:
#   - ./user_data/freqaimodels:/freqtrade/user_data/freqaimodels
```

### Step 6: Test the model loads (dry run first)
```bash
# DON'T change config.json yet. First test that the model file is importable:
docker exec freqtrade python -c "
import sys
sys.path.insert(0, '/freqtrade/user_data/freqaimodels')
from FinBuddyLLMModel import FinBuddyLLMModel
print('FinBuddyLLMModel import OK')
"
```

### Step 7: If import test passes — switch config
```bash
# Change freqaimodel in config.json
jq '.freqaimodel = "FinBuddyLLMModel"' user_data/config.json > /tmp/config_new.json \
  && mv /tmp/config_new.json user_data/config.json

# Verify
grep freqaimodel user_data/config.json
# Expected: "freqaimodel": "FinBuddyLLMModel"
```

### Step 8: Restart and verify
```bash
docker restart freqtrade
sleep 10
docker logs freqtrade --tail=80

# Look for:
# ✅ Good: "FinBuddyLLMModel" in startup logs
# ✅ Good: "[FinBuddyLLMModel] ... LGBM=x.xxxx | LLM=CONFIRM | Blended=x.xxxx"
# ✅ Good: "[FinBuddyLLMModel] GROQ_API_KEY not set" (if key not added yet, still runs)
# ❌ Bad: ImportError, ModuleNotFoundError, AttributeError
```

### Step 9: If import fails — rollback and fix
```bash
# Rollback to LightGBMRegressor
jq '.freqaimodel = "LightGBMRegressor"' user_data/config.json > /tmp/config_new.json \
  && mv /tmp/config_new.json user_data/config.json
docker restart freqtrade

# Then fix the error in FinBuddyLLMModel.py and retry from Step 6
```

---

## 🚦 What Comes After (Task 1.3)

Once FinBuddyLLMModel is running and you've verified Groq calls appear in logs:

```bash
# Run walk-forward backtest
docker exec -it freqtrade freqtrade backtesting \
  --strategy FinBuddyFreqAI \
  --freqaimodel FinBuddyLLMModel \
  --timerange 20250101-20260401 \
  --timeframe 15m
```

**Accept if:**
- Win rate > 50%
- Sharpe ratio > 0.5
- Max drawdown < 20%
- Profit factor > 1.2

If backtest passes → update `strategies/registry.json` status to `validated`.

---

## 💬 How to Use Perplexity Going Forward

Perplexity AI can:
- ✅ Write Python code and commit directly to GitHub (no SSH needed)
- ✅ Update task files, memory vault, session logs
- ✅ Answer questions about the project state, read any file
- ❌ Cannot SSH into the server
- ❌ Cannot restart Docker containers
- ❌ Cannot read live logs

**Best workflow:**
- Perplexity writes code → commits to `gaurav` branch
- Claude Code reviews, deploys (`git pull` + `docker restart`), verifies
- Claude Code updates task status after live verification

---

## 🗑️ Delete This File

Once you’ve completed all steps above and verified FinBuddyLLMModel is running on the server, delete this file:
```bash
git rm CLAUDE_HANDOFF.md
git commit -m "chore: remove handoff note — Task 1.2 deployed and verified"
git push origin gaurav
```

---

*Generated by Perplexity AI — 2026-05-01*
