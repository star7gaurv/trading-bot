# Phase 9 — Futures Risk Engine

> Build the safety layer for futures trading: dynamic position sizing,
> liquidation guards, funding rate monitoring, and drawdown circuit breakers.
> **Prerequisite:** Phase 8 complete. Futures dry-run active and stable.

---

## Phase Status: ⬜ Pending

---

## Task 9.1 — Liquidation Guard
**Status:** ⬜ Pending

Prevent any trade from being placed if it risks more than 2% of account.

### Add to `FinBuddyFreqAI.py`:
```python
def custom_stake_amount(
    self, current_time, current_rate: float,
    proposed_stake: float, min_stake, max_stake: float,
    leverage: float, entry_tag: str, side: str, **kwargs
) -> float:
    """Never risk more than 2% of wallet per trade."""
    wallet = self.wallets.get_available_stake_amount()
    max_risk = wallet * 0.02
    # With leverage, actual market exposure = stake * leverage
    # Risk per trade = stake * stoploss_pct
    safe_stake = max_risk / abs(self.stoploss)
    return max(min_stake or 0, min(proposed_stake, safe_stake))
```

---

## Task 9.2 — Funding Rate Monitor
**Status:** ⬜ Pending

Avoid entering positions when funding rate is extremely negative (being short costs too much).

### Create: `freqtrade/user_data/scripts/funding_rate_monitor.py`

```python
#!/usr/bin/env python3
"""Monitor Binance USDT-M funding rates. Block trades when rate is extreme."""
import requests, json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/funding_rates.json")

def fetch():
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    # Build dict: pair -> funding_rate
    rates = {}
    for item in data:
        symbol = item["symbol"]
        rate = float(item.get("lastFundingRate", 0))
        rates[symbol] = rate

    # Flag extreme rates (> 0.1% or < -0.1% per 8h = > 9% per month)
    extreme = {s: r for s, r in rates.items() if abs(r) > 0.001}

    result = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "rates": rates,
        "extreme_pairs": extreme,
        "alert": len(extreme) > 5  # broad market funding stress
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(f"Funding rates fetched. Extreme pairs: {len(extreme)}")

if __name__ == "__main__":
    fetch()
```

Add to crontab (every 8h, before funding settlement):
```
0 0,8,16 * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/funding_rate_monitor.py >> /home/ubuntu/.finbuddy/logs/funding_rate.log 2>&1
```

### Wire into strategy:
In `populate_entry_trend()`, read `funding_rates.json` and skip entry if pair is in `extreme_pairs` and side conflicts with funding direction.

---

## Task 9.3 — Drawdown Circuit Breaker
**Status:** ⬜ Pending

Auto-pause trading if total account drawdown exceeds 10% in 24h.

### Create: `freqtrade/user_data/scripts/drawdown_watchdog.py`

```python
#!/usr/bin/env python3
"""Monitor daily drawdown. Set TRADING_PAUSED flag if threshold exceeded."""
import requests, json, os
from pathlib import Path
from datetime import datetime, timezone

FT_API = "http://localhost:8080/api/v1"
FT_AUTH = ("bot", os.getenv("FT_API_PASSWORD", "REDACTED-FREQTRADE__API_SERVER__PASSWORD"))
FLAG_FILE = Path("/home/ubuntu/.finbuddy/TRADING_PAUSED")
DD_THRESHOLD = 0.10  # 10% daily drawdown

def check():
    r = requests.get(f"{FT_API}/profit", auth=FT_AUTH, timeout=5)
    r.raise_for_status()
    data = r.json()

    daily_dd = abs(float(data.get("profit_today_percent", 0)))
    total_dd = abs(float(data.get("max_drawdown_abs", 0)))
    
    if daily_dd >= DD_THRESHOLD:
        FLAG_FILE.touch()
        # Also pause via FreqTrade API
        requests.post(f"{FT_API}/stopbuy", auth=FT_AUTH)
        print(f"CIRCUIT BREAKER TRIGGERED: daily DD={daily_dd:.2%}. Trading paused.")
    else:
        if FLAG_FILE.exists():
            FLAG_FILE.unlink()
        print(f"Drawdown OK: daily={daily_dd:.2%}, all-time max={total_dd:.2f} USDT")

if __name__ == "__main__":
    check()
```

Add to crontab (every 15 min):
```
*/15 * * * * python3 /home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts/drawdown_watchdog.py >> /home/ubuntu/.finbuddy/logs/drawdown_watchdog.log 2>&1
```

---

## Task 9.4 — HMM Regime → Leverage Scaling
**Status:** ⬜ Pending

Scale leverage dynamically based on current regime (Phase 3 output).

| Regime | Max Leverage | Long Allowed | Short Allowed |
|---|---|---|---|
| CRASH | 0× | ❌ | ❌ |
| BEAR | 1× | ❌ | ✅ |
| NEUTRAL | 2× | ✅ | ✅ |
| BULL | 3× | ✅ | ⚠️ Gate |
| EUPHORIA | 1× | ⚠️ Gate | ❌ |

### Add to strategy:
```python
_REGIME_LEVERAGE = {
    "CRASH": 0, "BEAR": 1, "NEUTRAL": 2,
    "BULL": 3, "EUPHORIA": 1
}

def leverage(self, pair, current_time, current_rate,
             proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
    regime = self._get_current_regime()  # from Phase 3
    max_by_regime = self._REGIME_LEVERAGE.get(regime, 2)
    if max_by_regime == 0:
        return 0.0  # signals block via custom_stake returning 0
    return min(float(max_by_regime), max_leverage)
```

---

## Task 9.5 — Telegram Risk Alerts
**Status:** ⬜ Pending

Send Telegram message on:
- Circuit breaker triggered
- Extreme funding rate detected
- Regime change (from memory writer)
- Any single trade loss > 3%

Use FreqTrade native Telegram for trade alerts. For script-level alerts:
```python
def send_telegram(message: str):
    import requests, os
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8557119080:AAH9KPMIZSGP7Gsn9wbJGVNaNRyEQHISR_o")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "5622292536")
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": f"🚨 FinBuddy Risk Alert:\n{message}"},
        timeout=5
    )
```

---

## Phase 9 Completion Checklist
- [ ] `custom_stake_amount()` caps risk at 2% per trade
- [ ] `funding_rate_monitor.py` running via cron, writing to `external/`
- [ ] `drawdown_watchdog.py` running every 15 min, circuit breaker tested
- [ ] Leverage scales with regime (0× on CRASH, 3× on BULL)
- [ ] Telegram risk alerts firing for each risk event type
- [ ] 7-day dry-run soak with no margin calls or unexpected liquidations

---

## 🔗 Related Files
- [[CLAUDE]] ← infra, credentials
- [[FINBUDDY_PROJECT_MEMORY]] ← master hub
- [[tasks/phase-8-futures-setup]] ← prerequisite
- [[tasks/phase-10-live-migration]] ← next phase: go live
- [[tasks/phase-3-hmm-regime]] ← regime data this phase consumes
- [[finbuddy_memory/regimes/current]] ← live regime file
