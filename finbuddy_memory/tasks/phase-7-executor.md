# Phase 7 — Python Signal Executor (Multi-Tenant Shape)

**Status:** ✅ LIVE (cron `*/5 * * * *` `scripts/executor/executor.py` — paper mode)

> **2026-05-18 update**: Executor is live and runs in paper mode. Tasks 7.2 and 7.3 (N8N → executor signal flow) are **dead** — N8N permanently disabled. The signal source today is FreqAI inside the live FreqTrade bot; multi-tenant signal-as-a-service shape (per ADR-001) remains the future direction but not yet wired since there is no production signal stream to fan out.

> The thin per-user executor that receives signals from the central brain and places trades.
> ~300–500 lines of Python. Non-custodial — each user's API key never leaves their executor.
> Phase 1: runs for Gaurav only. Phase 2: one config file per user, same code.

---

## Task 7.1 — Build Minimal Python Executor
**Status:** ⬜ Pending  
**Effort:** 4–6 hours  
**File:** `freqtrade/user_data/scripts/executor/executor.py`

### Install
```bash
pip install fastapi uvicorn ccxt --break-system-packages
```

### Core logic

```python
from fastapi import FastAPI, Request
import ccxt, sqlite3, json, os
from datetime import datetime, timezone

app = FastAPI()
USER_CONFIG = json.load(open("users/user_01_gaurav.json"))
DB_PATH = "freqtrade/user_data/executor.sqlite"

# Init DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_signals (
            signal_id TEXT PRIMARY KEY,
            received_at TEXT,
            action TEXT
        )
    """)
    conn.commit()

@app.post("/signals")
async def receive_signal(request: Request):
    signal = await request.json()
    
    # 1. Validate schema version
    if signal.get("schema_version") != "1.0":
        return {"status": "rejected", "reason": "unknown schema version"}
    
    # 2. Dedupe on signal_id
    conn = sqlite3.connect(DB_PATH)
    exists = conn.execute("SELECT 1 FROM seen_signals WHERE signal_id=?", 
                          [signal["signal_id"]]).fetchone()
    if exists:
        return {"status": "conflict", "reason": "duplicate signal_id"}
    
    # 3. Check signal age (reject if older than 10 min)
    emitted = datetime.fromisoformat(signal["emitted_at"].replace("Z", "+00:00"))
    age_minutes = (datetime.now(timezone.utc) - emitted).seconds / 60
    if age_minutes > 10:
        return {"status": "rejected", "reason": f"signal too old ({age_minutes:.1f} min)"}
    
    # 4. Check confidence threshold
    if signal["confidence"] < USER_CONFIG["min_confidence_threshold"]:
        return {"status": "skipped", "reason": "below confidence threshold"}
    
    # 5. Check regime filter
    blocked = USER_CONFIG["regime_filter"]["blocked_regimes"]
    if signal["regime"] in blocked:
        return {"status": "skipped", "reason": f"regime {signal['regime']} is blocked"}
    
    # 6. Execute trade
    if signal["side"] == "buy":
        place_buy(signal)
    elif signal["side"] == "sell":
        place_sell(signal)
    # hold = log and skip
    
    # 7. Mark as seen
    conn.execute("INSERT INTO seen_signals VALUES (?, ?, ?)",
                 [signal["signal_id"], datetime.utcnow().isoformat(), signal["side"]])
    conn.commit()
    
    return {"status": "accepted"}


def calculate_position_size(signal):
    capital = USER_CONFIG["capital_usd"]
    risk_pct = USER_CONFIG["max_risk_per_trade_pct"]
    atr = signal["market_context"]["atr_14"]
    stop_multiplier = signal["stop_loss_atr_multiplier"]
    
    risk_amount = capital * risk_pct
    position_size_usd = risk_amount / (atr * stop_multiplier)
    return min(position_size_usd, capital * 0.25)  # Never more than 25% in one trade


def place_buy(signal):
    exchange = ccxt.binance({
        "apiKey": os.getenv("BINANCE_API_KEY"),
        "secret": os.getenv("BINANCE_API_SECRET"),
    })
    size = calculate_position_size(signal)
    # Paper trading check
    if USER_CONFIG.get("paper_trading"):
        print(f"[PAPER] BUY {signal['pair']} size=${size:.2f}")
        return
    exchange.create_market_buy_order(signal["pair"], size)
```

---

## Task 7.2 — Run Executor as a Service
**Status:** ⬜ Pending (after 7.1)  
**Effort:** 30 minutes

```bash
# Add to crontab
@reboot uvicorn executor:app --host 127.0.0.1 --port 8787 --log-level info &
```

The signal generator (N8N or future Python script) POSTs to `http://localhost:8787/signals`.

---

## Task 7.3 — Wire N8N Signal Generator to Executor
**Status:** ⬜ Pending (after 7.1)  
**Effort:** 1 hour

In N8N v3 pipeline, after generating a signal, add a final HTTP Request node:
- URL: `http://localhost:8787/signals`
- Method: POST
- Body: signal JSON conforming to `docs/signal-contract.md`
- Generate `signal_id` as UUID in N8N code node

---

## Task 7.4 — Signal History Dashboard (Simple)
**Status:** ⬜ Pending (after 7.1)  
**Effort:** 1 hour

Add a simple GET endpoint to the executor for viewing signal history:

```python
@app.get("/history")
def get_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT signal_id, received_at, action 
        FROM seen_signals 
        ORDER BY received_at DESC 
        LIMIT 50
    """).fetchall()
    return {"signals": [{"id": r[0], "at": r[1], "action": r[2]} for r in rows]}
```

---

## Phase 7 Complete When
- [ ] Executor running on localhost:8787 and surviving reboots
- [ ] Signal deduplication working (test by sending same signal_id twice)
- [ ] Paper trading mode active — orders logged but not placed on exchange
- [ ] N8N wired to POST signals to executor
- [ ] Signal history accessible via GET /history
