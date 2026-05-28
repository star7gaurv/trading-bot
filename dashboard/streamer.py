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
EXP_LOG_FILE = REPO_ROOT / "finbuddy_memory/experiments/log.jsonl"
BRAIN_RUN_LOG = Path("/home/ubuntu/.finbuddy/logs/brain_run.log")
WF_RESULTS_DIR = REPO_ROOT / "walkforward_results"
CONFIG_JSON = REPO_ROOT / "freqtrade/user_data/config.json"
WF_RUN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+_\d{8}T\d{6}$")
ACTIVE_STALE_S = 12 * 3600

# FreqTrade API
FT_BASE = "http://127.0.0.1:8080/api/v1"
FT_USER = os.environ.get("FT_USER", "bot")
FT_PASS = os.environ.get("FT_PASS", "REDACTED-FREQTRADE__API_SERVER__PASSWORD")
FT_AUTH = "Basic " + base64.b64encode(f"{FT_USER}:{FT_PASS}".encode()).decode()


# ───────────────────────── Lifecycle ─────────────────────────
def _preflight():
    """Fail fast if required env vars are missing — surfaces config errors at startup."""
    missing = []
    if not os.environ.get("DASHBOARD_PASSWORD"):
        missing.append("DASHBOARD_PASSWORD")
    if not os.environ.get("DASHBOARD_SECRET_KEY"):
        missing.append("DASHBOARD_SECRET_KEY")
    if not os.environ.get("FT_USER") or not os.environ.get("FT_PASS"):
        pass # Optional fallback
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
    allow_origins=["https://trade.star7gaurav.in", "http://localhost:5173", "http://REDACTED-SERVER_IP:5173"],
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
    statuses: dict[str, int] = {}
    recent: list[dict] = []
    oldest_queued_ts: Optional[int] = None

    # Read queue.jsonl — pending/queued experiments
    if QUEUE_FILE.exists():
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
                    status = str(row.get("status", "queued"))
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
            pass

    # Read log.jsonl — completed/failed experiments (ground truth for run counts)
    if EXP_LOG_FILE.exists():
        try:
            with open(EXP_LOG_FILE) as f:
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
        except OSError:
            pass

    return {
        "total": sum(statuses.values()),
        "by_status": statuses,
        "oldest_queued_ts": oldest_queued_ts,
        "recent": recent[-30:],
    }


@app.get("/api/brain/experiments")
async def brain_experiments(
    limit: int = Query(50, ge=1, le=200), _: dict = Depends(require_auth)
):
    """Return recent brain experiments from log.jsonl (ground truth with window + timestamps)."""
    if not EXP_LOG_FILE.exists():
        return {"items": []}

    items: list[dict] = []
    try:
        with open(EXP_LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = row.get("metrics") or {}
                cfg = row.get("config") or {}
                # Extract profit_pct — log stores as decimal (0.052 = 5.2%), convert to %
                profit_pct = m.get("profit_pct")
                wr = m.get("wr")
                items.append({
                    "verdict": row.get("status", "unknown"),
                    "hypothesis_id": row.get("hypothesis_id", ""),
                    "window": row.get("window", ""),
                    "version": cfg.get("target_version", "v23"),
                    "ts": row.get("completed_at") or row.get("created_at"),
                    "kvs": {
                        "profit": f"{profit_pct * 100:.2f}" if profit_pct is not None else "",
                        "WR": f"{wr * 100:.1f}" if wr is not None else "",
                        "sharpe": f"{m.get('sharpe', ''):.3f}" if m.get("sharpe") is not None else "",
                        "trades": str(m.get("trades", "")),
                    },
                })
    except OSError:
        return {"items": []}

    # Most recent first (sort by completed_at descending)
    items.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return {"items": items[:limit]}


# ───────────────────── Walk-Forward ─────────────────────
def _wf_runs_sorted() -> list[Path]:
    if not WF_RESULTS_DIR.exists():
        return []
    runs = [
        p for p in WF_RESULTS_DIR.iterdir()
        if p.is_dir() and WF_RUN_PATTERN.match(p.name)
    ]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs


@app.get("/api/wf/latest")
async def wf_latest(_: dict = Depends(require_auth)):
    runs = _wf_runs_sorted()
    if not runs:
        return {"available": False}
        
    active_run_name = None
    for run in runs:
        if not (run / "summary.json").exists():
            age_s = time.time() - run.stat().st_mtime
            if age_s < ACTIVE_STALE_S:
                active_run_name = run.name
                break

    # Walk sorted runs (newest first) and return the first one WITH a summary.json
    for latest in runs:
        summary_path = latest / "summary.json"
        if not summary_path.exists():
            continue
        try:
            with open(summary_path) as f:
                data = json.load(f)
            max_fold = 21
            active_run = None
            if active_run_name:
                active_run = next((r for r in runs if r.name == active_run_name), None)
            try:
                logs = list(active_run.glob("fold_*.log")) if active_run else list(latest.glob("fold_*.log"))
                if logs:
                    max_fold = max([int(p.stem.split('_')[1]) for p in logs if p.stem.split('_')[1].isdigit()], default=21)
            except Exception:
                pass
            return {"available": True, "name": latest.name, "summary": data, "active_run_name": active_run_name, "target_folds": max_fold}
        except (OSError, json.JSONDecodeError):
            continue
    
    # No run with a valid summary found
    return {"available": False, "name": runs[0].name if runs else "", "active_run_name": active_run_name}




@app.get("/api/wf/running-folds")
async def wf_running_folds(_: dict = Depends(require_auth)):
    runs = _wf_runs_sorted()
    active_run = None
    for run in runs:
        if not (run / "summary.json").exists():
            age_s = __import__('time').time() - run.stat().st_mtime
            if age_s < ACTIVE_STALE_S:
                active_run = run
                break
                
    if not active_run:
        return {"available": False}
        
    folds_data = []
    fold_results = []
    
    for f in sorted(active_run.glob("fold_*_result.json")):
        parts = f.name.split('_')
        if len(parts) >= 2 and parts[1].isdigit():
            fold_num = int(parts[1])
            log_files = list(active_run.glob(f"fold_{fold_num:02d}_*.log"))
            if not log_files:
                continue
            
            try:
                log_name = log_files[0].stem
                dates = log_name.split('_')[-1]
                ts_str, te_str = dates.split('-')
                from datetime import datetime
                test_start = datetime.strptime(ts_str, "%Y%m%d")
                test_end = datetime.strptime(te_str, "%Y%m%d")
                
                fr = parse_fold(f, fold_num, test_start, test_end)
                if fr:
                    fold_results.append(fr)
                    from dataclasses import asdict
                    folds_data.append(asdict(fr))
            except Exception as e:
                print(f"Error parsing running fold {f.name}: {e}")
                
    if not fold_results:
        return {"available": False, "active_run_name": active_run.name}
        
    agg = aggregate(fold_results)
    
    return {
        "available": True,
        "name": active_run.name,
        "folds": folds_data,
        "aggregate": agg
    }


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
        item["is_active"] = (
            not summary_path.exists()
            and (time.time() - run.stat().st_mtime) < ACTIVE_STALE_S
        )
        item["completed_folds"] = len(list(run.glob("fold_*_result.json")))

        if summary_path.exists():
            try:
                with open(summary_path) as f:
                    s = json.load(f)
                item["pass"] = bool(s.get("pass"))
                item["verdict"] = s.get("verdict") or ""
                agg = s.get("aggregate") or {}
                item["wr"]     = agg.get("weighted_win_rate")
                item["sharpe"] = agg.get("weighted_sharpe") or agg.get("sharpe")
                item["pf"]     = agg.get("weighted_profit_factor")
                item["dd"]     = agg.get("worst_drawdown")
                item["trades"] = agg.get("total_trades")
                item["pnl"]    = agg.get("total_profit_abs")
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
    return await ft_get("/trades", params={"limit": limit, "offset": offset, "order_by_id": "false"})


@app.get("/api/performance/daily")
async def performance_daily(days: int = Query(30, ge=1, le=365), _: dict = Depends(require_auth)):
    # FreqTrade wraps the list as {"data": [...], "stake_currency": "USDT"}
    result = await ft_get("/daily", params={"timescale": days})
    return result.get("data", result) if isinstance(result, dict) else result


@app.get("/api/performance/weekly")
async def performance_weekly(weeks: int = Query(12, ge=1, le=52), _: dict = Depends(require_auth)):
    result = await ft_get("/weekly", params={"timescale": weeks})
    return result.get("data", result) if isinstance(result, dict) else result


@app.get("/api/performance/monthly")
async def performance_monthly(months: int = Query(6, ge=1, le=24), _: dict = Depends(require_auth)):
    result = await ft_get("/monthly", params={"timescale": months})
    return result.get("data", result) if isinstance(result, dict) else result


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
async def websocket_brain(websocket: WebSocket, token: str = Query(None)):
    if not token or not verify_token(token):
        await websocket.close(code=1008)
        return
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
async def websocket_memory(websocket: WebSocket, token: str = Query(None)):
    if not token or not verify_token(token):
        await websocket.close(code=1008)
        return
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
