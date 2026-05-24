"""
FinBuddy Dashboard Streamer — FastAPI server on :8501.

Exposes:
- WebSockets:
    /ws/brain   — tails freqtrade.log, emits "FinBuddyLLMModel" lines (legacy v1, preserved)
    /ws/memory  — polls CONTEXT.md, emits regime + fear/greed (legacy v1, preserved)
- Auth:
    POST /api/auth/login    — { password } -> { token }
    GET  /api/auth/me       — verify token, return subject
- Read-only data endpoints (require Bearer token):
    GET  /api/cron/status   — all cron jobs with last-run + status + log tail
    GET  /api/system/health — load/disk/memory/docker/freqtrade
    GET  /api/brain/queue   — read experiments/queue.jsonl
    GET  /api/brain/experiments?limit=50 — recent results from brain_run.log
    GET  /api/wf/latest     — most recent walkforward summary.json
    GET  /api/wf/history    — list of recent WF runs
    GET  /api/regime/current
    GET  /api/regime/pair-stats
    GET  /api/trades/open       — proxy FreqTrade /api/v1/status
    GET  /api/trades/closed?limit&offset — proxy FreqTrade /api/v1/trades
    GET  /api/performance/daily?days=30
    GET  /api/performance/pair
    GET  /api/balance       — proxy FreqTrade /api/v1/balance
    GET  /api/whitelist     — proxy FreqTrade /api/v1/whitelist
    GET  /api/config        — current strategy + identifier + thresholds

Required env vars: DASHBOARD_PASSWORD, DASHBOARD_SECRET_KEY
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import aiofiles
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Local modules (same directory)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from auth import check_password, issue_token, verify_token, extract_bearer  # noqa: E402
from cron_status import parse_crontab, summarize as summarize_crons  # noqa: E402
from system_health import full_snapshot as system_snapshot  # noqa: E402


# ─────────────────────────── Paths ───────────────────────────
REPO_ROOT = Path("/home/ubuntu/var/www/html/trade")
LOG_FILE = REPO_ROOT / "freqtrade/user_data/logs/freqtrade.log"
CONTEXT_FILE = REPO_ROOT / "finbuddy_memory/CONTEXT.md"
REGIME_CURRENT = REPO_ROOT / "finbuddy_memory/regimes/current.json"
PAIR_REGIME_STATS = REPO_ROOT / "finbuddy_memory/regimes/pair_regime_stats.json"
QUEUE_FILE = REPO_ROOT / "finbuddy_memory/experiments/queue.jsonl"
BRAIN_RUN_LOG = Path("/home/ubuntu/.finbuddy/logs/brain_run.log")
WF_RESULTS_DIR = REPO_ROOT / "walkforward_results"
CONFIG_JSON = REPO_ROOT / "freqtrade/user_data/config.json"

# FreqTrade API
FT_BASE = "http://127.0.0.1:8080/api/v1"
FT_USER = "bot"
FT_PASS = "REDACTED-FREQTRADE__API_SERVER__PASSWORD"
FT_AUTH = "Basic " + base64.b64encode(f"{FT_USER}:{FT_PASS}".encode()).decode()


# ───────────────────────── Lifecycle ─────────────────────────
def _preflight():
    """Fail fast if required env vars are missing — surfaces config errors at startup."""
    missing = []
    if not os.environ.get("DASHBOARD_PASSWORD"):
        missing.append("DASHBOARD_PASSWORD")
    if not os.environ.get("DASHBOARD_SECRET_KEY"):
        missing.append("DASHBOARD_SECRET_KEY")
    if missing:
        print(f"FATAL: required env vars missing: {missing}", file=sys.stderr)
        print(
            'Generate a secret key with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"',
            file=sys.stderr,
        )
        sys.exit(1)


_preflight()

app = FastAPI(title="FinBuddy Dashboard Streamer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────────── Auth dependency ─────────────────────
async def require_auth(authorization: Optional[str] = Header(default=None)) -> dict:
    token = extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ───────────────────── TTL cache ─────────────────────
_cache: dict[str, tuple[float, Any]] = {}


def cached(key: str, ttl: float, compute):
    """In-memory TTL cache. Compute is a zero-arg callable."""
    now = time.time()
    hit = _cache.get(key)
    if hit and (now - hit[0] < ttl):
        return hit[1]
    value = compute()
    _cache[key] = (now, value)
    return value


async def cached_async(key: str, ttl: float, compute_coro):
    now = time.time()
    hit = _cache.get(key)
    if hit and (now - hit[0] < ttl):
        return hit[1]
    value = await compute_coro()
    _cache[key] = (now, value)
    return value


# ───────────────────── FreqTrade proxy ─────────────────────
async def ft_get(path: str, params: dict | None = None) -> Any:
    url = f"{FT_BASE}{path}"
    headers = {"Authorization": FT_AUTH}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers, params=params or {})
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        raise HTTPException(status_code=502, detail=f"FreqTrade API error: {e}") from e


# ───────────────────── Auth routes ─────────────────────
class LoginIn(BaseModel):
    password: str


@app.post("/api/auth/login")
async def auth_login(body: LoginIn):
    if not check_password(body.password):
        # tiny sleep to slow brute-force without holding worker
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=401, detail="Invalid password")
    token = issue_token(subject="admin")
    return {"token": token, "expires_in": 7 * 24 * 3600}


@app.get("/api/auth/me")
async def auth_me(payload: dict = Depends(require_auth)):
    return {"sub": payload.get("sub"), "exp": payload.get("exp")}


# ───────────────────── System / Cron ─────────────────────
@app.get("/api/cron/status")
async def cron_status(_: dict = Depends(require_auth)):
    def compute():
        jobs = parse_crontab()
        return {"summary": summarize_crons(jobs), "jobs": jobs}

    return cached("cron_status", ttl=30.0, compute=compute)


@app.get("/api/system/health")
async def system_health(_: dict = Depends(require_auth)):
    return cached("system_health", ttl=15.0, compute=system_snapshot)


# ───────────────────── Brain ─────────────────────
@app.get("/api/brain/queue")
async def brain_queue(_: dict = Depends(require_auth)):
    if not QUEUE_FILE.exists():
        return {"total": 0, "by_status": {}, "recent": []}

    statuses: dict[str, int] = {}
    recent: list[dict] = []
    oldest_queued_ts: Optional[int] = None

    try:
        with open(QUEUE_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = str(row.get("status", "unknown"))
                statuses[status] = statuses.get(status, 0) + 1
                if status == "queued":
                    ts = row.get("created_at_ts") or row.get("ts")
                    if isinstance(ts, (int, float)):
                        if oldest_queued_ts is None or ts < oldest_queued_ts:
                            oldest_queued_ts = int(ts)
                recent.append({
                    "hypothesis_id": row.get("hypothesis_id"),
                    "status": status,
                    "ts": row.get("ts") or row.get("created_at_ts"),
                    "band": row.get("band") or row.get("kind"),
                })
    except OSError:
        return {"error": "queue file unreadable"}

    return {
        "total": sum(statuses.values()),
        "by_status": statuses,
        "oldest_queued_ts": oldest_queued_ts,
        "recent": recent[-30:],
    }


_BRAIN_LOG_RE = re.compile(
    r"\[brain\]\s+(\w+)\s+(\S+)\s+\[(\w+)\]\s*\?\s*(.*)"
)


@app.get("/api/brain/experiments")
async def brain_experiments(
    limit: int = Query(50, ge=1, le=200), _: dict = Depends(require_auth)
):
    if not BRAIN_RUN_LOG.exists():
        return {"items": []}
    out = subprocess.run(
        ["tail", "-n", "2000", str(BRAIN_RUN_LOG)],
        capture_output=True, text=True, timeout=5,
    )
    items: list[dict] = []
    for line in out.stdout.splitlines():
        m = _BRAIN_LOG_RE.search(line)
        if not m:
            continue
        verdict, hid, version, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        # Parse trailing "profit=X% WR=Y%" style fragments
        kvs: dict[str, str] = {}
        for kv in re.finditer(r"(\w+)=([^\s]+)", rest):
            kvs[kv.group(1)] = kv.group(2)
        # Timestamp prefix
        ts_match = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
        items.append({
            "verdict": verdict,
            "hypothesis_id": hid,
            "version": version,
            "raw": line.strip(),
            "kvs": kvs,
            "ts": ts_match.group(1) if ts_match else None,
        })
    items.reverse()
    return {"items": items[:limit]}


# ───────────────────── Walk-Forward ─────────────────────
def _wf_runs_sorted() -> list[Path]:
    if not WF_RESULTS_DIR.exists():
        return []
    runs = [p for p in WF_RESULTS_DIR.iterdir() if p.is_dir()]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs


@app.get("/api/wf/latest")
async def wf_latest(_: dict = Depends(require_auth)):
    runs = _wf_runs_sorted()
    if not runs:
        return {"available": False}
    # Walk sorted runs (newest first) and return the first one WITH a summary.json
    for latest in runs:
        summary_path = latest / "summary.json"
        if not summary_path.exists():
            continue
        try:
            with open(summary_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        return {"available": True, "name": latest.name, "summary": data}
    # No run with a valid summary found
    return {"available": False, "name": runs[0].name if runs else ""}



@app.get("/api/wf/history")
async def wf_history(limit: int = Query(20, ge=1, le=100), _: dict = Depends(require_auth)):
    runs = _wf_runs_sorted()[:limit]
    items = []
    for run in runs:
        summary_path = run / "summary.json"
        item = {
            "name": run.name,
            "mtime": int(run.stat().st_mtime),
            "has_summary": summary_path.exists(),
        }
        if summary_path.exists():
            try:
                with open(summary_path) as f:
                    s = json.load(f)
                item["pass"] = bool(s.get("pass"))
                item["verdict"] = s.get("verdict") or ""
                agg = s.get("aggregate") or s.get("summary") or {}
                item["wr"] = agg.get("win_rate")
                item["sharpe"] = agg.get("weighted_sharpe") or agg.get("sharpe")
                item["pf"] = agg.get("profit_factor")
                item["dd"] = agg.get("max_drawdown")
            except (OSError, json.JSONDecodeError):
                pass
        items.append(item)
    return {"items": items}


# ───────────────────── Regime ─────────────────────
@app.get("/api/regime/current")
async def regime_current(_: dict = Depends(require_auth)):
    if not REGIME_CURRENT.exists():
        return {"available": False}
    try:
        with open(REGIME_CURRENT) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}


@app.get("/api/regime/pair-stats")
async def regime_pair_stats(_: dict = Depends(require_auth)):
    if not PAIR_REGIME_STATS.exists():
        return {"available": False}
    try:
        with open(PAIR_REGIME_STATS) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}


# ───────────────────── FreqTrade proxies ─────────────────────
@app.get("/api/trades/open")
async def trades_open(_: dict = Depends(require_auth)):
    return await ft_get("/status")


@app.get("/api/trades/closed")
async def trades_closed(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_auth),
):
    return await ft_get("/trades", params={"limit": limit, "offset": offset})


@app.get("/api/performance/daily")
async def performance_daily(days: int = Query(30, ge=1, le=365), _: dict = Depends(require_auth)):
    return await ft_get("/daily", params={"timescale": days})


@app.get("/api/performance/weekly")
async def performance_weekly(weeks: int = Query(12, ge=1, le=52), _: dict = Depends(require_auth)):
    return await ft_get("/weekly", params={"timescale": weeks})


@app.get("/api/performance/monthly")
async def performance_monthly(months: int = Query(6, ge=1, le=24), _: dict = Depends(require_auth)):
    return await ft_get("/monthly", params={"timescale": months})


@app.get("/api/performance/pair")
async def performance_pair(_: dict = Depends(require_auth)):
    return await ft_get("/performance")


@app.get("/api/profit")
async def profit_summary(_: dict = Depends(require_auth)):
    return await ft_get("/profit")


@app.get("/api/balance")
async def balance(_: dict = Depends(require_auth)):
    return await ft_get("/balance")


@app.get("/api/whitelist")
async def whitelist(_: dict = Depends(require_auth)):
    return await ft_get("/whitelist")


@app.get("/api/config")
async def get_config(_: dict = Depends(require_auth)):
    # Pull the relevant slice of config.json — strategy, identifier, thresholds, pairs
    if not CONFIG_JSON.exists():
        return {"available": False}
    try:
        with open(CONFIG_JSON) as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}

    freqai = cfg.get("freqai", {}) or {}
    return {
        "strategy": cfg.get("strategy"),
        "max_open_trades": cfg.get("max_open_trades"),
        "stake_currency": cfg.get("stake_currency"),
        "dry_run": cfg.get("dry_run"),
        "dry_run_wallet": cfg.get("dry_run_wallet"),
        "timeframe": cfg.get("timeframe"),
        "stoploss": cfg.get("stoploss"),
        "trailing_stop": cfg.get("trailing_stop"),
        "freqai_identifier": freqai.get("identifier"),
        "live_retrain_hours": freqai.get("live_retrain_hours"),
        "pair_whitelist": (cfg.get("exchange") or {}).get("pair_whitelist", []),
        "pair_blacklist": (cfg.get("exchange") or {}).get("pair_blacklist", []),
    }


# ───────────────────── WebSockets (legacy preserved) ─────────────────────
@app.websocket("/ws/brain")
async def websocket_brain(websocket: WebSocket):
    await websocket.accept()
    try:
        tail_output = subprocess.check_output(
            ["tail", "-n", "5000", str(LOG_FILE)], timeout=5
        ).decode("utf-8", errors="replace")
        hist_lines = [l.strip() for l in tail_output.split("\n") if "FinBuddyLLMModel" in l and "[" in l]
        for line in hist_lines[-50:]:
            await websocket.send_json({"type": "brain_log", "log": line})
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        print(f"Error fetching history: {e}", file=sys.stderr)

    try:
        async with aiofiles.open(LOG_FILE, "r") as f:
            await f.seek(0, os.SEEK_END)
            while True:
                line = await f.readline()
                if not line:
                    await asyncio.sleep(0.5)
                    continue
                if "FinBuddyLLMModel" in line and "[" in line:
                    await websocket.send_json({"type": "brain_log", "log": line.strip()})
    except Exception as e:
        print(f"Error in brain streamer: {e}", file=sys.stderr)
        try:
            await websocket.close()
        except RuntimeError:
            pass


@app.websocket("/ws/memory")
async def websocket_memory(websocket: WebSocket):
    await websocket.accept()
    last_mtime = 0.0
    try:
        while True:
            if CONTEXT_FILE.exists():
                mtime = CONTEXT_FILE.stat().st_mtime
                if mtime > last_mtime:
                    async with aiofiles.open(CONTEXT_FILE, "r") as f:
                        content = await f.read()
                    regime = "UNKNOWN"
                    fear_greed = "UNKNOWN"
                    for line in content.split("\n"):
                        if line.startswith("Regime:"):
                            m = re.search(r"\*\*(.*?)\*\*", line)
                            if m:
                                regime = m.group(1)
                        elif line.startswith("Fear & Greed:"):
                            fear_greed = line.replace("Fear & Greed:", "").strip()
                    await websocket.send_json({
                        "type": "memory_update",
                        "regime": regime,
                        "fear_greed": fear_greed,
                    })
                    last_mtime = mtime
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Error in memory streamer: {e}", file=sys.stderr)
        try:
            await websocket.close()
        except RuntimeError:
            pass


# ───────────────────── Health endpoint (unauthenticated) ─────────────────────
@app.get("/api/ping")
async def ping():
    return {"ok": True, "ts": int(time.time())}


# ───────────────────── Custom error formatting ─────────────────────
@app.exception_handler(HTTPException)
async def _format_http_exception(_request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8501)
