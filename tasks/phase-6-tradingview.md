# Phase 6 — TradingView Integration

> TradingView is the world's most popular charting platform.
> Their Pine Script alert system (free) can fire webhooks to our server.
> This lets us use hundreds of community indicators as signal sources without paying for their data API.

---

## How It Works (Free Tier)

TradingView free account allows:
- 1 active alert at a time
- Webhook URL destination for alerts
- Pine Script custom indicators

TradingView paid (Pro, ~$15/month) allows:
- Unlimited alerts
- Multiple webhook destinations

**Start with free (1 alert). Expand to paid only if it proves valuable.**

---

## Task 6.1 — Set Up Webhook Receiver on Server
**Status:** ⬜ Pending  
**Effort:** 2 hours  
**File:** `freqtrade/user_data/scripts/tradingview/webhook_receiver.py`

Lightweight FastAPI server that receives TradingView alert payloads.

### Install
```bash
pip install fastapi uvicorn --break-system-packages
```

### Server code
```python
from fastapi import FastAPI, Request
import json, os
from datetime import datetime

app = FastAPI()

SIGNAL_FILE = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/tradingview_signals.json"

@app.post("/tradingview")
async def receive_signal(request: Request):
    body = await request.json()
    
    signal = {
        "timestamp": datetime.utcnow().isoformat(),
        "ticker": body.get("ticker"),
        "signal": body.get("signal"),        # "BUY", "SELL", "HOLD"
        "indicator": body.get("indicator"),  # "supertrend", "volume_spike", etc.
        "timeframe": body.get("timeframe"),
        "price": body.get("price")
    }
    
    # Append to signal history
    history = []
    if os.path.exists(SIGNAL_FILE):
        with open(SIGNAL_FILE) as f:
            history = json.load(f)
    
    history.append(signal)
    history = history[-100:]  # Keep last 100 signals
    
    with open(SIGNAL_FILE, 'w') as f:
        json.dump(history, f, indent=2)
    
    return {"status": "ok"}
```

### Start on boot
```bash
# Add to crontab
@reboot uvicorn tradingview_webhook_receiver:app --host 0.0.0.0 --port 9999 --log-level warning &
```

### Nginx proxy (add to existing config)
```nginx
location /tradingview {
    proxy_pass http://127.0.0.1:9999;
}
```

---

## Task 6.2 — Configure TradingView Alert (Free)
**Status:** ⬜ Pending (after 6.1)  
**Effort:** 30 minutes

### On TradingView (free account)
1. Open BTC/USDT 15m chart
2. Add Supertrend indicator (built-in, free)
3. Create alert: Supertrend direction change
4. Alert settings:
   - Condition: Supertrend changes to bullish / bearish
   - Webhook URL: `https://trade.star7gaurav.in/tradingview`
   - Message body (JSON):
     ```json
     {
       "ticker": "{{ticker}}",
       "signal": "{{strategy.order.action}}",
       "indicator": "supertrend",
       "timeframe": "15m",
       "price": {{close}}
     }
     ```
5. Save alert

### Recommended starting indicator
**Supertrend** — extremely popular, directional, clean BUY/SELL signals. Works well on crypto 15m.

---

## Task 6.3 — Wire TradingView Signals into FreqAI Features
**Status:** ⬜ Pending (after 6.1)  
**Effort:** 1 hour

In `FinBuddyFreqAI.py`, read `tradingview_signals.json` and add as features:

```python
def read_tradingview_signals(self):
    signal_file = ".../data/external/tradingview_signals.json"
    if not os.path.exists(signal_file):
        return {"tv_supertrend_bullish": 0, "tv_signal_age_minutes": 999}
    
    with open(signal_file) as f:
        signals = json.load(f)
    
    if not signals:
        return {"tv_supertrend_bullish": 0, "tv_signal_age_minutes": 999}
    
    latest = signals[-1]
    age_minutes = (datetime.utcnow() - datetime.fromisoformat(latest['timestamp'])).seconds / 60
    
    return {
        "tv_supertrend_bullish": 1 if latest['signal'] == 'BUY' else 0,
        "tv_signal_age_minutes": age_minutes  # Stale signals should have less weight
    }
```

---

## Phase 6 Complete When
- [ ] Webhook receiver running on port 9999 and surviving reboots
- [ ] Nginx proxying /tradingview to receiver
- [ ] At least 1 TradingView alert firing to server (verify in logs)
- [ ] `tradingview_signals.json` updating on alert fire
- [ ] FreqAI reads TradingView signal as a feature
