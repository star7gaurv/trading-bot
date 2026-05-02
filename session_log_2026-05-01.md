# FinBuddy — Session Log
**Date:** May 1, 2026
**Interface:** Perplexity AI (with GitHub MCP tools)
**Who:** Gaurav

---

## Session Summary

This session continued Phase 1 work after Claude Code hit its usage limit. Perplexity AI wrote and committed Task 1.2 directly to the `gaurav` branch via GitHub API.

---

## What Was Done

### Task 1.2 — FinBuddyLLMModel.py ✅ COMMITTED

**File:** `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py`  
**Commit:** [55848d7](https://github.com/star7gaurv/trading-bot/commit/55848d79305557914a5ef72f68dfad56d283f422)

**Architecture implemented:**
```
Market data + indicators
        ↓
  LightGBM prediction (inherited from LightGBMRegressor)
        ↓
  If abs(prediction) > 0.006 (0.6% move) AND per-pair cooldown elapsed:
    → Call Groq Llama 3.3 70B with full market context
    → Parse: CONFIRM / REJECT / HOLD
    → Final signal = LightGBM * 0.60 + LightGBM * multiplier * 0.40
  Else:
    → LightGBM signal used as-is
```

**LLM multipliers:**
- CONFIRM → x1.30 (LLM agrees, amplify signal)
- REJECT  → x0.15 (LLM disagrees, near-zero dampening)
- HOLD    → x0.50 (uncertain, moderate dampening)

**Key safety features:**
- GROQ_TIMEOUT = 4 seconds (never blocks a trade decision)
- Per-pair 60-min cooldown (protects free tier: 6000 req/day)
- On any Groq error/timeout → returns HOLD → LightGBM signal unchanged
- On 429 rate limit → extends cooldown to 2 hours automatically
- Graceful import fallback (works with both LightGBMRegressor and BaseRegressionModel)

**Groq prompt includes:**
- Pair, timestamp, timeframe
- ML signal direction + strength + predicted % change
- RSI(14), MACD histogram, EMA50 trend, BB position, volume change, price 24h position

---

## Deployment Instructions (for Claude Code session)

When Claude Code resets (2:40 AM IST), run these commands on the server:

```bash
# 1. Pull latest
cd /home/ubuntu/var/www/html/trade/freqtrade && git pull

# 2. Add GROQ_API_KEY to docker-compose.yml environment
# Under freqtrade service:
# environment:
#   - GROQ_API_KEY=gsk_your_key_here

# 3. Ensure freqaimodels dir is in volumes (add if not present):
# - ./user_data/freqaimodels:/freqtrade/user_data/freqaimodels

# 4. Update config.json
sed -i 's/"freqaimodel": "LightGBMRegressor"/"freqaimodel": "FinBuddyLLMModel"/' \
  /home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json

# 5. Restart
docker restart freqtrade

# 6. Verify (look for FinBuddyLLMModel in logs)
docker logs freqtrade --tail=50
```

---

## Current Phase 1 Status After This Session

| Task | Status |
|---|---|
| 1.1 — FinBuddyFreqAI strategy (LightGBM) | ✅ COMPLETE |
| 1.2 — FinBuddyLLMModel (Groq layer) | ✅ COMPLETE (this session) |
| 1.3 — Walk-forward backtest | ⬜ Next |
| 1.4 — Switch dry-run to FinBuddyFreqAI | ⬜ After backtest |

---

## Notes

- Perplexity AI can write and commit code to GitHub directly (no SSH needed)
- Use Perplexity for code writing + commits when Claude Code is rate-limited
- Claude Code handles server-side deployment (docker restart, git pull, log checking)
- Best workflow: Perplexity writes → Claude Code deploys
