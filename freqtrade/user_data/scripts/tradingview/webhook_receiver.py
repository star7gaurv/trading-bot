#!/usr/bin/env python3
"""TradingView webhook receiver — FastAPI on port 9999."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json, os
from datetime import datetime
from pathlib import Path

app = FastAPI()
SIGNAL_FILE = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/tradingview_signals.json")
SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)

@app.post("/tradingview")
async def receive_signal(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "reason": "invalid JSON"}, status_code=400)

    signal = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ticker": body.get("ticker", ""),
        "signal": body.get("signal", ""),
        "indicator": body.get("indicator", ""),
        "timeframe": body.get("timeframe", ""),
        "price": body.get("price", 0),
    }

    history = []
    if SIGNAL_FILE.exists():
        try:
            with open(SIGNAL_FILE) as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append(signal)
    history = history[-100:]

    with open(SIGNAL_FILE, "w") as f:
        json.dump(history, f, indent=2)

    return {"status": "ok", "received": signal}

@app.get("/health")
def health():
    try:
        with open(SIGNAL_FILE) as f:
            count = len(json.load(f))
    except Exception:
        count = 0
    return {"status": "ok", "signals_stored": count}
