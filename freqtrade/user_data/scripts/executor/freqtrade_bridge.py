#!/usr/bin/env python3
"""
FreqTrade → Executor bridge.
Reads open/recent trades from the FreqTrade REST API and writes them
to executor_signals.json so executor.py can dedup-track and audit them.
This runs before executor.py in the cron (see executor_wrapper.sh).
"""
import json
import urllib.request
import urllib.error
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path

ROOT        = Path("/home/ubuntu/var/www/html/trade")
SIGNAL_FILE = ROOT / "freqtrade/user_data/data/external/executor_signals.json"
REGIME_FILE = ROOT / "finbuddy_memory/regimes/current.json"
API_BASE    = "http://localhost:8080/api/v1"
API_USER    = "bot"
API_PASS    = "REDACTED-FREQTRADE__API_SERVER__PASSWORD"


def _api_get(path: str) -> dict | list | None:
    url = f"{API_BASE}{path}"
    creds = b64encode(f"{API_USER}:{API_PASS}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[bridge] API error {path}: {e}")
        return None


def _load_regime() -> str:
    try:
        return json.loads(REGIME_FILE.read_text()).get("regime", "NEUTRAL")
    except Exception:
        return "NEUTRAL"


def run_bridge() -> int:
    """Pull open trades from FreqTrade and write to executor_signals.json.
    Returns number of signals written."""
    data = _api_get("/trades?limit=50&offset=0")
    if data is None:
        print("[bridge] FreqTrade API unreachable — skipping signal sync")
        return 0

    regime   = _load_regime()
    trades   = data.get("trades", [])
    open_t   = [t for t in trades if t.get("is_open")]
    signals  = []

    for t in open_t:
        side = "buy" if not t.get("is_short") else "sell"
        enter_tag = t.get("enter_tag", "")
        # Derive confidence from enter_tag version label (v16 = newer = higher confidence)
        confidence = 0.75 if "v16" in enter_tag else 0.65

        signals.append({
            "signal_id": f"ft_{t['trade_id']}",
            "pair":      t.get("pair", "?"),
            "side":      side,
            "confidence": confidence,
            "regime":    regime,
            "enter_tag": enter_tag,
            "open_rate": t.get("open_rate"),
            "stake_amount": t.get("stake_amount"),
            "created_at": t.get("open_date", datetime.now(timezone.utc).isoformat()),
        })

    SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_FILE.write_text(json.dumps(signals, indent=2))
    print(f"[bridge] wrote {len(signals)} open-trade signals to executor_signals.json (regime={regime})")
    return len(signals)


if __name__ == "__main__":
    run_bridge()
