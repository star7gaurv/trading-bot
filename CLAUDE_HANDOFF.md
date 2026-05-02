# 🤝 FinBuddy — Handoff Note for Claude Code

**Written by:** Perplexity AI  
**Date:** 2026-05-02 15:31 IST  
**For:** Claude Code (next session)  
**Branch:** `gaurav`

---

## 🚨 STRATEGIC PIVOT — Read Before Anything Else

**FinBuddy has pivoted from Spot to Futures (USDT-M Perpetual) as the primary market.**

Reason: 192 spot backtests across 3 rounds all failed — root cause is spot being long-only in a -47.55% bear market. ML signal quality is confirmed healthy (79–81% WR on signal exits). The brain is fine. The market type was wrong.

**Do NOT run any more spot backtests or deploy anything on the spot strategy.**

---

## ✅ What Was Done Last Session (Perplexity — May 2, 2026)

| Task | Status |
|---|---|
| Strategic pivot decision: Futures-first | ✅ Decided |
| `FINBUDDY_PROJECT_MEMORY.md` updated with full new roadmap | ✅ Committed |
| `CLAUDE.md` updated with pivot, new vision, revised roadmap | ✅ Committed |
| `CLAUDE_HANDOFF.md` updated (this file) | ✅ Committed |

---

## 🔥 Your Job This Session (Claude Code)

Execute the futures pivot in this order:

### Step 1 — Switch FreqTrade to Binance Futures

Update the FreqTrade config to use Binance Futures USDT-M:

```json
// In freqtrade/user_data/config.json (or docker-compose env):
{
  "exchange": {
    "name": "binance",
    "pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT", ...]
  },
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "futures_upkeep_ledger_multiplier": 3
}
```

- Pair format changes from `BTC/USDT` → `BTC/USDT:USDT` for futures
- `trading_mode: "futures"` enables long + short
- `margin_mode: "isolated"` — safer, limits loss per trade
- Keep dry-run ON during testing

### Step 2 — Verify FreqTrade Accepts Futures Config

```bash
cd /home/ubuntu/var/www/html/trade/
docker compose logs freqtrade --tail=50
```

Look for: no errors loading futures config, pairs loading correctly with `:USDT` format.

### Step 3 — Report Back to Perplexity

Once futures config is live (dry-run), write a short handoff note confirming:
- Futures mode is active
- Any config issues encountered
- Current pair whitelist loaded

Perplexity will then rewrite `FinBuddyFreqAI.py` for long + short and set up the futures backtest.

---

## 📊 Backtest History (For Context — Spot, Retired)

| Round | Combos | Best Sharpe | Key Finding |
|---|---|---|---|
| 1 | 12 | -0.183 | EMA/RSI useless; chmod bug |
| 2 | 36 | -0.236 | roi_multiplier dead lever |
| 3 | 144 | -0.401 | trailing_offset + ml_exit dead levers; bear market root cause |
| **Total** | **192** | **-0.174** | **Spot backtesting retired** |

---

## 📁 Current File State

| File | Version | State |
|---|---|---|
| `freqtrade/user_data/strategies/FinBuddyFreqAI.py` | v6 | ⚠️ Spot strategy — needs futures rewrite by Perplexity |
| `freqtrade/user_data/freqaimodels/FinBuddyLLMModel.py` | v1 | ⚠️ Committed, not deployed — will deploy on futures strategy |
| `scripts/autobacktest.py` | v4.1 | ✅ Reliable — repurpose for futures backtest |
| `scripts/run_backtest.sh` | v2 | ⚠️ Spot config — Perplexity will update for futures |
| `_autobacktest_results.csv` | Rounds 1-3 | ✅ 192 rows — spot archive, keep for reference |
| `finbuddy_memory/strategies/graveyard.md` | updated | ✅ Round 3 entry added |

---

## 🔄 Collaboration Rules

| Who | Does What |
|---|---|
| **Gaurav** | Decides when to run, approves phase transitions |
| **Claude Code** | SSH, deploy, config changes, run scripts, verify on server |
| **Perplexity** | Designs strategy, writes code, updates docs, commits to GitHub |

---

*Written by Perplexity AI — 2026-05-02 15:31 IST*
