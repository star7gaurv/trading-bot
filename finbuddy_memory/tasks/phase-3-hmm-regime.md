# Phase 3 — HMM Five-Regime Detection Engine

**Status:** ✅ LIVE (cron `0 */4 * * *`) — outputs `finbuddy_memory/regimes/current.json`

> **2026-05-18 update**: HMM is live and feeding the strategy directly. The Task 3.3 N8N integration is **dead** (N8N pipeline permanently disabled). FreqAI strategy + brain hypothesis engine read `regimes/current.json` directly; backtest mode now also reads `regimes/historical_regime.parquet`.

> Build the Hidden Markov Model that classifies the current market into one of five regimes.
> This feeds into FreqAI features and the Obsidian memory vault.

---

## The Five Regimes

| Regime | Description | Brain Behavior |
|---|---|---|
| CRASH | Rapid price collapse, extreme fear | No new entries. Defensive only. |
| BEAR | Sustained downtrend, elevated fear | Reduce position sizes. Higher confidence threshold. |
| NEUTRAL | Sideways/ranging market | Normal trading. Default sizing. |
| BULL | Sustained uptrend, greed building | Normal to aggressive trading. |
| EUPHORIA | Parabolic move, extreme greed | Reduce new entries. Take profits faster. |

---

## Task 3.1 — Build HMM Regime Detection Script
**Status:** ⬜ Pending  
**Effort:** 4–6 hours  
**File:** `freqtrade/user_data/scripts/hmm_regime_detector.py`

### Dependencies
```bash
pip install hmmlearn pandas numpy python-binance --break-system-packages
```

### Input features for HMM
- Daily returns (log returns of BTC close)
- Rolling 7-day volatility
- Rolling 14-day trend (linear regression slope)
- Fear & Greed Index (from Phase 2)
- BTC 30-day drawdown from ATH

### HMM Setup
```python
from hmmlearn import hmm
import numpy as np

model = hmm.GaussianHMM(
    n_components=5,          # 5 regimes
    covariance_type="full",
    n_iter=200,
    random_state=42
)
```

### Regime labeling
After fitting, label each state by its mean return and volatility:
- Highest volatility + negative return → CRASH
- Negative return, medium volatility → BEAR
- Near-zero return → NEUTRAL
- Positive return, medium volatility → BULL
- Highest return + rising volatility → EUPHORIA

### Output file: `finbuddy_memory/regimes/current.md`
```markdown
---
regime: BULL
confidence: 0.82
since: 2026-04-20
updated: 2026-04-27T12:00:00Z
---
Current regime: BULL (confidence: 82%)
Active since: 2026-04-20
Previous: NEUTRAL
```

### Cron schedule
```
0 */4 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/hmm_regime_detector.py
```
(Re-runs every 4 hours — regime doesn't change minute to minute)

---

## Task 3.2 — Wire Regime into FreqAI Strategy
**Status:** ⬜ Pending (after 3.1)  
**Effort:** 1 hour

In `FinBuddyFreqAI.py`, read the current regime file and:
- Add `current_regime` as a categorical feature for LightGBM
- Block entries if regime is CRASH
- Reduce position_size_pct if regime is BEAR
- Use higher confidence threshold in BEAR/CRASH

```python
import json, os

def get_current_regime(self):
    regime_file = os.path.join(self.config['user_data_dir'], 
                               '../finbuddy_memory/regimes/current.json')
    with open(regime_file) as f:
        data = json.load(f)
    return data.get('regime', 'NEUTRAL')
```

---

## Task 3.3 — Wire Regime into N8N Signal Prompt
**Status:** ⬜ Pending (after 3.1)  
**Effort:** 1 hour

In the N8N v3 pipeline, add a step that reads `finbuddy_memory/regimes/current.md` and injects the regime into the Groq prompt:

```
Current market regime: BULL (HMM confidence: 82%)
This means: sustained uptrend conditions. Normal position sizing applies.
```

This makes the LLM signal aware of macro context.

---

## Task 3.4 — Regime History Logging
**Status:** ⬜ Pending (after 3.1)  
**Effort:** 30 minutes  
**File:** `finbuddy_memory/regimes/history.md`

Each time regime changes, append to history file:
```markdown
| 2026-04-20 | NEUTRAL → BULL | Confidence: 82% |
| 2026-03-15 | BEAR → NEUTRAL | Confidence: 71% |
```

Auto-commit via git after each regime change.

---

## Task 3.5 — Regime-Based Position Sizing
**Status:** ⬜ Pending (after 3.2)  
**Effort:** 1 hour

Implement ATR-based dynamic sizing with regime multipliers:

```python
BASE_RISK_PCT = 0.02  # 2% of capital per Turtle Trading rule

REGIME_MULTIPLIERS = {
    'CRASH':    0.0,   # No new trades
    'BEAR':     0.5,   # Half size
    'NEUTRAL':  1.0,   # Normal
    'BULL':     1.0,   # Normal
    'EUPHORIA': 0.75,  # Slightly reduced (avoid FOMO top)
}

def calculate_position_size(capital, atr, regime):
    multiplier = REGIME_MULTIPLIERS.get(regime, 1.0)
    risk_amount = capital * BASE_RISK_PCT * multiplier
    position_size = risk_amount / (atr * 2.0)  # 2x ATR stop
    return position_size
```

---

## Phase 3 Complete When
- [ ] HMM model trains on 90+ days of BTC daily data
- [ ] Regime classified every 4 hours and written to `finbuddy_memory/regimes/current.md`
- [ ] Regime auto-committed to git
- [ ] FreqAI strategy reads regime and adjusts behavior
- [ ] N8N prompt includes current regime
- [ ] Position sizing uses regime multipliers

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
