# Phase 5 — Karpathy Auto-Research Loop

> The self-improving engine. The brain that makes FinBuddy get smarter without Gaurav doing anything.
> Named after Andrej Karpathy's philosophy of continuous evaluation, hypothesis generation, and validation.
> This is what separates FinBuddy from every other trading bot — it researches and evolves itself.

---

## The Loop

```
[Every night at 2 AM]

1. RESEARCH (Gemini 2.5 Flash)
   → Reads news, on-chain data, macro signals, recent signal log
   → Generates market insights and observations
   → Writes to: finbuddy_memory/research/[date]-nightly.md

2. REASONING (DeepSeek R1)
   → Reads research notes + signal history + strategy graveyard
   → Reasons about what's working, what's not
   → Generates 1–3 strategy hypotheses
   → Writes hypotheses to: strategies/registry.json (status: in_development)

3. BACKTESTING (FreqTrade)
   → Detects new in_development strategies in registry
   → Runs walk-forward backtest automatically
   → Writes results back to registry

4. PROMOTION/DEMOTION (Claude Sonnet)
   → If backtest passes → promote to active, write Pine Script
   → If backtest fails → demote to deprecated, log to graveyard
   → Commits everything to git

5. Loop restarts next night
```

---

## Task 5.1 — Build Nightly Research Agent (Gemini)
**Status:** ⬜ Pending  
**Effort:** 3–4 hours  
**File:** `freqtrade/user_data/scripts/karpathy/research_agent.py`

### Setup
```bash
pip install google-generativeai --break-system-packages
# Store in env: GEMINI_API_KEY
```

### What it reads
- Last 24h of `finbuddy_memory/signals/log.md`
- Current regime from `finbuddy_memory/regimes/current.md`
- CryptoPanic headlines (from Phase 2)
- Fear & Greed history (last 7 days)
- Current open trades from FreqTrade API

### What it produces
A research note written to `finbuddy_memory/research/[YYYY-MM-DD]-nightly.md`:
```markdown
# Nightly Research — 2026-04-27

## Market Observations
...

## What Worked Today
...

## What Failed Today
...

## Macro Context
...

## Hypotheses for DeepSeek
- Hypothesis 1: ...
- Hypothesis 2: ...
```

### Gemini prompt template
```python
RESEARCH_PROMPT = """
You are FinBuddy's research analyst. Analyze the following data and produce a structured research note.

SIGNAL HISTORY (last 24h):
{signal_log}

CURRENT REGIME: {regime}

MARKET SENTIMENT: Fear & Greed = {fear_greed}

NEWS HEADLINES:
{news_headlines}

Produce:
1. Key market observations (3–5 bullet points)
2. What signals worked and why
3. What failed and why  
4. Macro context that matters for the next 24h
5. 1–2 concrete strategy hypotheses to test (be specific about indicators and parameters)

Be analytical, not descriptive. Focus on what CAUSES signals to succeed or fail.
"""
```

---

## Task 5.2 — Build Strategy Reasoning Agent (DeepSeek R1)
**Status:** ⬜ Pending (after 5.1)  
**Effort:** 3 hours  
**File:** `freqtrade/user_data/scripts/karpathy/reasoning_agent.py`

### Setup
```python
# DeepSeek uses OpenAI-compatible API
import openai
client = openai.OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)
```

### What it reads
- Tonight's research note
- `strategies/registry.json` — what's active, what's deprecated and why
- `finbuddy_memory/strategies/graveyard.md` — historical failures

### What it produces
Concrete strategy specifications written to `strategies/registry.json`:
```json
{
  "strategy_id": "rsi_divergence_v1",
  "status": "in_development",
  "hypothesis": "RSI divergence on 1h timeframe predicts reversals in BULL regime",
  "indicators": ["RSI_14", "PRICE_ACTION"],
  "timeframe": "1h",
  "regime_filter": ["BULL", "NEUTRAL"],
  "proposed_by": "deepseek_r1",
  "proposed_at": "2026-04-27"
}
```

---

## Task 5.3 — Auto-Backtest Pipeline
**Status:** ⬜ Pending (after 5.2)  
**Effort:** 4 hours  
**File:** `freqtrade/user_data/scripts/karpathy/backtest_runner.py`

Detects strategies with `status: in_development` in registry, generates strategy code, runs backtest, writes results.

### Steps
1. Read registry — find `in_development` strategies
2. For each: generate a FreqTrade strategy Python file from the spec (use Claude Sonnet API)
3. Run backtest:
   ```bash
   docker exec freqtrade freqtrade backtesting \
     --strategy {strategy_id} \
     --timerange 20250101-20260401
   ```
4. Parse backtest output (JSON results)
5. Update registry with results

### Acceptance criteria
```python
PASS_CRITERIA = {
    'win_rate': 0.50,
    'sharpe_ratio': 0.5,
    'max_drawdown': 0.20,
    'profit_factor': 1.2,
    'total_trades': 30  # Minimum trades for statistical significance
}
```

---

## Task 5.4 — Promotion/Demotion Logic
**Status:** ⬜ Pending (after 5.3)  
**Effort:** 2 hours  
**File:** `freqtrade/user_data/scripts/karpathy/promoter.py`

### If backtest PASSES
1. Update registry: `status → active`
2. Call Claude Sonnet API to write Pine Script version (for TradingView visualization)
3. Write to `finbuddy_memory/strategies/winners.md`
4. Send Telegram notification: "🧠 New strategy promoted: {id} | Win rate: {X}% | Sharpe: {Y}"

### If backtest FAILS
1. Update registry: `status → deprecated`
2. Write failure reason to `finbuddy_memory/strategies/graveyard.md`
3. Log: why it failed, what the hypothesis was, what the numbers showed

### Auto-commit everything
```bash
git add strategies/ finbuddy_memory/
git commit -m "karpathy: {promoted/deprecated} {strategy_id} — {reason}"
git push origin master
```

---

## Task 5.5 — Master Orchestration Script + Cron
**Status:** ⬜ Pending (after 5.1–5.4)  
**Effort:** 1 hour  
**File:** `freqtrade/user_data/scripts/karpathy/run_loop.py`

Master script that runs the full loop in sequence.

```python
# run_loop.py
from research_agent import run_research
from reasoning_agent import run_reasoning
from backtest_runner import run_backtests
from promoter import run_promotion

if __name__ == "__main__":
    research_note = run_research()
    hypotheses = run_reasoning(research_note)
    backtest_results = run_backtests(hypotheses)
    run_promotion(backtest_results)
```

### Cron (nightly at 2 AM — low traffic time)
```
0 2 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/karpathy/run_loop.py >> ~/.finbuddy/logs/karpathy.log 2>&1
```

---

## Phase 5 Complete When
- [ ] Nightly research note appears in `finbuddy_memory/research/` every morning
- [ ] DeepSeek generates at least 1 strategy hypothesis per week
- [ ] Auto-backtest runs without manual intervention
- [ ] At least 1 strategy promoted or deprecated by the loop (end-to-end test)
- [ ] Telegram notification fires on promotion/demotion
- [ ] Everything auto-committed to git
