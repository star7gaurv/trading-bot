"""
Cortexa Dashboard Streamer — FastAPI server on :8501.

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
from datetime import datetime, timedelta
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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from auth import check_password, issue_token, verify_token, extract_bearer  # noqa: E402
from cron_status import parse_crontab, summarize as summarize_crons  # noqa: E402
from system_health import full_snapshot as system_snapshot  # noqa: E402
from ft_creds import get_ft_auth  # noqa: E402


# ─────────────────────────── Paths ───────────────────────────
REPO_ROOT = Path("/home/ubuntu/var/www/html/trade")
LOG_FILE = REPO_ROOT / "freqtrade/user_data/logs/freqtrade.log"
CONTEXT_FILE = REPO_ROOT / "finbuddy_memory/CONTEXT.md"
REGIME_CURRENT = REPO_ROOT / "finbuddy_memory/regimes/current.json"
PAIR_REGIME_STATS = REPO_ROOT / "finbuddy_memory/regimes/pair_regime_stats.json"
QUEUE_FILE = REPO_ROOT / "finbuddy_memory/experiments/queue.jsonl"
EXP_LOG_FILE = REPO_ROOT / "finbuddy_memory/experiments/log.jsonl"
COMBINED_CTX_FILE = REPO_ROOT / "freqtrade/user_data/data/external/combined_context.json"
FUNDING_CACHE_FILE = REPO_ROOT / "freqtrade/user_data/data/external/funding_rate_cache.json"
BRAIN_RUN_LOG = Path("/home/ubuntu/.finbuddy/logs/brain_run.log")
WF_RESULTS_DIR = REPO_ROOT / "walkforward_results"
CONFIG_JSON = REPO_ROOT / "freqtrade/user_data/config.json"
WF_RUN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+_\d{8}T\d{6}$")
ACTIVE_STALE_S = 12 * 3600
MANUAL_OVERRIDE_LOG = REPO_ROOT / "finbuddy_memory/trades/manual_overrides.jsonl"

# FreqTrade API
FT_BASE = "http://127.0.0.1:8080/api/v1"
FT_USER, FT_PASS = get_ft_auth()
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

# docs_url/redoc_url disabled (2026-07-17): FastAPI auto-enables an unauthenticated
# interactive API explorer at /docs by default. Currently unreachable only by accident
# (nginx has no location routing to it, and uvicorn binds 127.0.0.1 only) - explicitly
# disabling it here means that stays true even if nginx routing ever changes. Internal
# API/code documentation lives in the MkDocs site instead (finbuddy_memory/docs_site/).
app = FastAPI(title="Cortexa Dashboard Streamer", docs_url=None, redoc_url=None)

# 2026-07-05: server IP moved out of source into an env var (DASHBOARD_EXTRA_ORIGIN,
# optional) instead of being hardcoded and committed to git.
_extra_origin = os.environ.get("DASHBOARD_EXTRA_ORIGIN")
_cors_origins = ["https://trade.star7gaurav.in", "http://localhost:5173", "http://localhost:8502"]
if _extra_origin:
    _cors_origins.append(_extra_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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


async def ft_post(path: str, json_body: dict | None = None) -> httpx.Response:
    """Like ft_get but for state-changing calls — returns the raw Response so
    callers can inspect status_code/body themselves (e.g. to treat FreqTrade's
    "invalid argument" RPCException, surfaced as HTTP 502, as a soft-success
    when it just means the trade was already closed by something else)."""
    url = f"{FT_BASE}{path}"
    headers = {"Authorization": FT_AUTH}
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.post(url, headers=headers, json=json_body or {})


def _append_override_log(entry: dict) -> None:
    """Append-only audit trail for manual trade overrides (force-exit, pause/resume).
    No flock — these are rare, human-paced actions, unlike the brain's queue.jsonl
    which needs locking for concurrent worker writes."""
    MANUAL_OVERRIDE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.utcnow().isoformat() + "Z", **entry}
    with open(MANUAL_OVERRIDE_LOG, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")


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
                    # Queue entries store `created_at` as an ISO-8601 string (not a
                    # numeric `created_at_ts`/`ts`). Parse it to an epoch so the
                    # "oldest queued" age renders instead of always being None.
                    row_ts = row.get("created_at_ts") or row.get("ts")
                    if row_ts is None:
                        ca = row.get("created_at")
                        if isinstance(ca, str):
                            try:
                                row_ts = datetime.fromisoformat(
                                    ca.replace("Z", "+00:00")
                                ).timestamp()
                            except ValueError:
                                row_ts = None
                    if status == "queued" and isinstance(row_ts, (int, float)):
                        if oldest_queued_ts is None or row_ts < oldest_queued_ts:
                            oldest_queued_ts = int(row_ts)
                    recent.append({
                        "hypothesis_id": row.get("hypothesis_id"),
                        "status": status,
                        "ts": int(row_ts) if isinstance(row_ts, (int, float)) else None,
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

    # Detect live running experiment: try to take the flock non-blockingly.
    # If it fails (rc != 0), the brain runner holds it → 1 experiment is running.
    brain_running = 0
    try:
        probe = subprocess.run(
            ["flock", "-n", "/tmp/finbuddy_brain_run.lock", "true"],
            capture_output=True, timeout=2,
        )
        if probe.returncode != 0:
            brain_running = 1
            # Don't double-count: the running item is currently "queued" in queue.jsonl
            statuses["running"] = statuses.get("running", 0) + 1
            statuses["queued"] = max(0, statuses.get("queued", 0) - 1)
    except Exception:
        pass

    return {
        "total": sum(statuses.values()),
        "by_status": statuses,
        "oldest_queued_ts": oldest_queued_ts,
        "recent": recent[-30:],
        "brain_running": brain_running,
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
                # 2026-06-17 ×100 BUG FIX: profit_pct is ALREADY a percent in the log
                # (runner.py: sum(profits)/10000*100; the brain log prints "profit=-33.703%").
                # The old `profit_pct * 100` rendered -33.7% as -3370% — destroying trust in
                # every dashboard number. WR, by contrast, IS stored as a decimal (0.469) and
                # correctly keeps its ×100.
                profit_pct = m.get("profit_pct")
                wr = m.get("wr")
                items.append({
                    "verdict": row.get("status", "unknown"),
                    "hypothesis_id": row.get("hypothesis_id", ""),
                    "window": row.get("window", ""),
                    "version": cfg.get("target_version", "v23"),
                    "ts": row.get("completed_at") or row.get("created_at"),
                    "kvs": {
                        "profit": f"{profit_pct:.2f}" if profit_pct is not None else "",
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
            active_run = None
            if active_run_name:
                active_run = next((r for r in runs if r.name == active_run_name), None)
            # Derive target_folds from the summary itself (not hardcoded).
            # The summary "folds" list has the actual completed folds for this run.
            folds_list = data.get("folds", [])
            target_folds = len(folds_list) if folds_list else 0
            # Also check log files in case folds list is empty (run still in progress)
            try:
                log_dir = active_run or latest
                logs = list(log_dir.glob("fold_*.log"))
                if logs:
                    log_max = max([int(p.stem.split('_')[1]) for p in logs if p.stem.split('_')[1].isdigit()], default=0)
                    target_folds = max(target_folds, log_max)
            except Exception:
                pass
            return {"available": True, "name": latest.name, "summary": data, "active_run_name": active_run_name, "target_folds": target_folds}
        except (OSError, json.JSONDecodeError):
            continue
    
    # No run with a valid summary found
    return {"available": False, "name": runs[0].name if runs else "", "active_run_name": active_run_name}




def _parse_fold_result(path: Path) -> Optional[dict]:
    """Read a fold_N_result.json and return normalised dict."""
    try:
        with open(path) as f:
            d = json.load(f)
        # Normalise key aliases across walk_forward versions
        return {
            "fold": d.get("fold") or d.get("fold_num"),
            "period_start": d.get("period_start") or d.get("test_start"),
            "period_end": d.get("period_end") or d.get("test_end"),
            "trade_count": int(d.get("trade_count") or d.get("trades") or 0),
            "win_rate": float(d.get("win_rate") or d.get("wr") or 0.0),
            "profit_factor": float(d.get("profit_factor") or d.get("pf") or 0.0),
            "sharpe": float(d.get("sharpe") or 0.0),
            "max_drawdown": float(d.get("max_drawdown") or d.get("dd") or 0.0),
            "total_profit_abs": float(d.get("total_profit_abs") or d.get("profit_abs") or 0.0),
        }
    except Exception:
        return None


def _aggregate_folds(folds: list[dict]) -> dict:
    """Compute weighted aggregates from fold dicts."""
    total_trades = sum(f["trade_count"] for f in folds)
    if total_trades == 0:
        return {}

    def weighted(key: str) -> float:
        return sum(f[key] * f["trade_count"] for f in folds) / total_trades

    return {
        "total_trades": total_trades,
        "total_profit_abs": sum(f["total_profit_abs"] for f in folds),
        "weighted_win_rate": weighted("win_rate"),
        "weighted_profit_factor": weighted("profit_factor"),
        "weighted_sharpe": weighted("sharpe"),
        "worst_drawdown": min(f["max_drawdown"] for f in folds),
        "fold_count": len(folds),
    }


@app.get("/api/wf/running-folds")
async def wf_running_folds(_: dict = Depends(require_auth)):
    """Return live fold metrics for the currently-running WF (if any)."""
    runs = _wf_runs_sorted()
    active_run = None
    for run in runs:
        if not (run / "summary.json").exists():
            age_s = time.time() - run.stat().st_mtime
            if age_s < ACTIVE_STALE_S:
                active_run = run
                break

    if not active_run:
        return {"available": False}

    folds_data: list[dict] = []
    for f in sorted(active_run.glob("fold_*_result.json")):
        fd = _parse_fold_result(f)
        if fd:
            folds_data.append(fd)

    if not folds_data:
        return {"available": True, "name": active_run.name, "folds": [], "aggregate": {}}

    return {
        "available": True,
        "name": active_run.name,
        "folds": folds_data,
        "aggregate": _aggregate_folds(folds_data),
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
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}

    # Enrich with external macro context (Fear & Greed, BTC dominance, news
    # sentiment, market-cap change). Fixes the Overview StatStrip, which expected
    # `fear_greed`/`btc_funding_rate` fields that current.json never contained —
    # so Fear/Greed and Funding stats were permanently hidden. Best-effort: a
    # missing/unreadable file just leaves the base regime data untouched.
    try:
        if COMBINED_CTX_FILE.exists():
            ctx = json.loads(COMBINED_CTX_FILE.read_text())
            data.setdefault("fear_greed", ctx.get("fear_greed"))
            data["fear_greed_label"] = ctx.get("fear_greed_label")
            data["btc_dominance"] = ctx.get("btc_dominance")
            data["market_cap_change_24h_pct"] = ctx.get("market_cap_change_24h_pct")
            data["news_sentiment_ratio"] = ctx.get("news_sentiment_ratio")
            data["news_bullish_count"] = ctx.get("news_bullish_count")
            data["news_bearish_count"] = ctx.get("news_bearish_count")
            data["context_ts"] = ctx.get("timestamp")
    except (OSError, json.JSONDecodeError):
        pass
    try:
        if FUNDING_CACHE_FILE.exists():
            fc = json.loads(FUNDING_CACHE_FILE.read_text())
            data["btc_funding_rate"] = fc.get("funding_rate")
    except (OSError, json.JSONDecodeError):
        pass

    return data


@app.get("/api/regime/pair-stats")
async def regime_pair_stats(_: dict = Depends(require_auth)):
    if not PAIR_REGIME_STATS.exists():
        return {"available": False}
    try:
        with open(PAIR_REGIME_STATS) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}


# ───────────────────── Live Signal Monitor ─────────────────────
_LONG_REGIMES = {"NEUTRAL", "BULL", "EUPHORIA"}
_SHORT_REGIMES = {"NEUTRAL", "BEAR", "CRASH"}


def _load_pair_regime_blocks_map() -> dict[str, set]:
    """{pair: {blocked_regime, ...}} from pair_regime_stats.json 'blocked' list."""
    out: dict[str, set] = {}
    try:
        d = json.loads(PAIR_REGIME_STATS.read_text())
        for b in d.get("blocked", []):
            p = b.get("pair")
            r = b.get("regime")
            if p and r:
                out.setdefault(p, set()).add(r)
    except (OSError, json.JSONDecodeError):
        pass
    return out


def _direction_status(side: str, row: dict, regime: str, gated: bool,
                      entering: bool) -> str:
    """Why is this side (long/short) entering or not? Determined by elimination —
    replicates CortexaAI_v23.populate_entry_trend gate order exactly, so the
    reason is authoritative without needing to recompute the centered prediction."""
    if entering:
        return "enter"
    if (row.get("do_predict") or 0) != 1:
        return "no_predict"
    if gated:
        return "gated"
    close = row.get("close")
    ema = row.get("ema_50")
    rsi = row.get("rsi_14")
    bb = row.get("bb_pct")
    if side == "long":
        if regime not in _LONG_REGIMES:
            return "regime"
        if close is not None and ema is not None and close <= ema:
            return "ta_ema"      # price below EMA-50 (no long in downtrend)
        if rsi is not None and rsi >= 68:
            return "ta_rsi"      # overbought
        if bb is not None and bb >= 0.90:
            return "ta_bb"       # at upper band
    else:  # short
        if regime not in _SHORT_REGIMES:
            return "regime"
        if close is not None and ema is not None and close >= ema:
            return "ta_ema"      # price above EMA-50 (no short in uptrend)
        if rsi is not None and rsi <= 32:
            return "ta_rsi"      # oversold
        if bb is not None and bb <= 0.10:
            return "ta_bb"       # at lower band
    # All gates pass but no entry → model prediction did not cross the threshold.
    return "threshold"


def _strategy_timeframe(default: str = "1h") -> str:
    """Live strategy base timeframe from config.json. The bot flipped 15m→1h on
    2026-06-21; /pair_candles only returns the analysed dataframe for the timeframe
    the strategy actually runs, so the signals monitor must request the live one."""
    try:
        return json.loads(CONFIG_JSON.read_text()).get("timeframe") or default
    except (OSError, json.JSONDecodeError, ValueError):
        return default


@app.get("/api/signals")
async def signals(_: dict = Depends(require_auth)):
    """Live per-pair signal monitor: for every whitelisted pair, report the current
    entry signal and the EXACT reason it is / isn't entering. Answers 'why no trades'
    at a glance instead of digging through logs. Read-only (analysed dataframe only)."""
    async def compute():
        wl = await ft_get("/whitelist")
        pairs = wl.get("whitelist", []) if isinstance(wl, dict) else (wl or [])
        blocks = _load_pair_regime_blocks_map()
        tf = _strategy_timeframe()

        async def one(pair: str) -> Optional[dict]:
            try:
                cd = await ft_get("/pair_candles", params={
                    "pair": pair, "timeframe": tf, "limit": 3,
                })
            except Exception:
                return None
            cols = cd.get("columns", [])
            data = cd.get("data", [])
            if not cols or len(data) < 2:
                return None
            # Use the last CLOSED candle (row[-2]); row[-1] is the forming candle
            # whose enter_long/short are still None.
            row = dict(zip(cols, data[-2]))
            regime = row.get("regime") or "—"
            gated = regime in blocks.get(pair, set())
            el = row.get("enter_long")
            es = row.get("enter_short")
            long_status = _direction_status("long", row, regime, gated, el == 1)
            short_status = _direction_status("short", row, regime, gated, es == 1)
            return {
                "pair": pair,
                "regime": regime,
                "do_predict": int(row.get("do_predict") or 0),
                "gated": gated,
                "pred": row.get("&-future_return"),
                "long_threshold": row.get("dynamic_long_threshold"),
                "short_threshold": row.get("dynamic_short_threshold"),
                "close": row.get("close"),
                "ema_50": row.get("ema_50"),
                "rsi_14": row.get("rsi_14"),
                "long_status": long_status,
                "short_status": short_status,
                "entering": long_status == "enter" or short_status == "enter",
            }

        results = await asyncio.gather(*[one(p) for p in pairs])
        rows = [r for r in results if r]
        # Entering first, then by pair name
        rows.sort(key=lambda r: (not r["entering"], r["pair"]))
        return {
            "pairs": rows,
            "count": len(rows),
            "entering_count": sum(1 for r in rows if r["entering"]),
        }

    return await cached_async("signals", 20.0, compute)


# ───────────────────── FreqTrade proxies ─────────────────────
@app.get("/api/trades/open")
async def trades_open(_: dict = Depends(require_auth)):
    return await ft_get("/status")


# In-memory per-trade cooldown so a double-tap on the Close button can't fire
# two forceexit calls back to back. Resets on restart — acceptable, restarts
# are rare and a stale guard only costs a few seconds of extra safety.
_closing_trades: dict[int, float] = {}
FORCE_EXIT_COOLDOWN_S = 5.0


@app.post("/api/trades/{trade_id}/close")
async def force_exit_trade(trade_id: int, _: dict = Depends(require_auth)):
    """Manually close one open trade via FreqTrade's real /forceexit (places a
    genuine market exit order) — NOT the DELETE /trades/{id} pattern used
    elsewhere in this file (see flatten_trades below), which only deletes the
    local DB row without ever exiting the exchange position."""
    now = time.time()
    last = _closing_trades.get(trade_id, 0.0)
    if now - last < FORCE_EXIT_COOLDOWN_S:
        raise HTTPException(status_code=429, detail="Already closing this trade — please wait a moment.")
    _closing_trades[trade_id] = now

    try:
        open_trades = await ft_get("/status")
        snapshot = next((t for t in open_trades if t.get("trade_id") == trade_id), None)
    except HTTPException:
        snapshot = None

    if snapshot is None:
        _closing_trades.pop(trade_id, None)
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found or already closed.")

    try:
        r = await ft_post("/forceexit", {"tradeid": str(trade_id), "ordertype": "market"})
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        # Deliberately NOT popping _closing_trades here — leave the cooldown
        # standing for its full FORCE_EXIT_COOLDOWN_S window even on failure,
        # so a rapid double-tap after an error can't race a second forceexit
        # call while the first might still be settling on FreqTrade's side.
        # (Bug found in testing: this used to pop immediately in every path,
        # which meant the cooldown only ever blocked truly-simultaneous
        # in-flight requests, not a real time-based window.)
        raise HTTPException(status_code=502, detail=f"FreqTrade API error: {e}") from e

    snapshot_out = {
        "direction": "short" if snapshot.get("is_short") else "long",
        "open_rate": snapshot.get("open_rate"),
        "current_rate": snapshot.get("current_rate"),
        "profit_abs": snapshot.get("profit_abs"),
        "profit_pct": snapshot.get("profit_pct") or snapshot.get("profit_ratio"),
        "stake_amount": snapshot.get("stake_amount"),
        "open_date": snapshot.get("open_date"),
    }

    if r.status_code != 200:
        detail = r.text[:300]
        # FreqTrade raises RPCException("invalid argument") — surfaced as HTTP 502
        # by its own global handler — when the trade is no longer open. That's a
        # legitimate race (the bot may exit it the same instant the user taps
        # Close), not a real failure, so log it but don't scare the user with a
        # 502 for something that resolved the way they wanted anyway.
        already_closed = "invalid argument" in detail.lower()
        _append_override_log({
            "action": "force_exit", "channel": "dashboard", "trade_id": trade_id,
            "pair": snapshot.get("pair"),
            "result": "already_closed" if already_closed else "error",
            "ft_response": detail, "snapshot": snapshot_out,
        })
        if already_closed:
            return {"accepted": True, "trade_id": trade_id, "pair": snapshot.get("pair"),
                    "status": "already_closed", "message": "Trade was already closed."}
        raise HTTPException(status_code=502, detail=f"forceexit failed: {detail}")

    body = r.json()
    _append_override_log({
        "action": "force_exit", "channel": "dashboard", "trade_id": trade_id,
        "pair": snapshot.get("pair"), "result": "closed",
        "ft_response": body, "snapshot": snapshot_out,
    })
    return {"accepted": True, "trade_id": trade_id, "pair": snapshot.get("pair"),
            "status": "closing", "message": body.get("result", "Exit order submitted.")}


# ───────────────────── Global trading state (pause/resume entries) ─────────────────────
@app.get("/api/trading/state")
async def trading_state(_: dict = Depends(require_auth)):
    cfg = await ft_get("/show_config")
    return {"state": cfg.get("state"), "dry_run": cfg.get("dry_run")}


@app.post("/api/trading/pause")
async def trading_pause(_: dict = Depends(require_auth)):
    """Stop new entries. Existing open trades keep being managed normally —
    stop-loss/take-profit/exit_signal all still fire. Reversible, no confirm
    needed (unlike force-exit, this doesn't realize any P&L)."""
    r = await ft_post("/pause")
    ok = r.status_code == 200
    body = r.json() if ok else {}
    _append_override_log({"action": "pause_entries", "channel": "dashboard",
                           "result": "ok" if ok else "error", "ft_response": body or r.text[:300]})
    if not ok:
        raise HTTPException(status_code=502, detail=r.text[:300])
    return {"accepted": True, "message": body.get("status", "paused")}


@app.post("/api/trading/resume")
async def trading_resume(_: dict = Depends(require_auth)):
    r = await ft_post("/start")
    ok = r.status_code == 200
    body = r.json() if ok else {}
    _append_override_log({"action": "resume_entries", "channel": "dashboard",
                           "result": "ok" if ok else "error", "ft_response": body or r.text[:300]})
    if not ok:
        raise HTTPException(status_code=502, detail=r.text[:300])
    return {"accepted": True, "message": body.get("status", "running")}


@app.get("/api/trades/closed")
async def trades_closed(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_auth),
):
    return await ft_get("/trades", params={"limit": limit, "offset": offset, "order_by_id": "false"})


async def _trade_wl_buckets() -> dict[str, dict]:
    """Return {date_key: {wins, losses}} for all three bucket types.

    FreqTrade daily/weekly/monthly endpoints omit win/loss breakdown.
    We compute it here from closed trades so the UI can show "W / L".
    Returns {"day": {"2026-05-28": {"wins":3,"losses":2}},
             "week": {"2026-05-25": ...},
             "month": {"2026-05-01": ...}}
    """
    try:
        result = await ft_get("/trades", params={"limit": 1000, "offset": 0})
        trades = result.get("trades", []) if isinstance(result, dict) else []
    except Exception:
        return {"day": {}, "week": {}, "month": {}}

    day_b: dict[str, dict] = {}
    week_b: dict[str, dict] = {}
    month_b: dict[str, dict] = {}

    for t in trades:
        cd = t.get("close_date") or ""
        if not cd or len(cd) < 10:
            continue
        profit = t.get("profit_abs") or 0.0

        day_key = str(cd)[:10]
        try:
            d = datetime.strptime(day_key, "%Y-%m-%d")
            monday = d - timedelta(days=d.weekday())
            week_key = monday.strftime("%Y-%m-%d")
            month_key = day_key[:7] + "-01"
        except ValueError:
            continue

        for bucket, key in ((day_b, day_key), (week_b, week_key), (month_b, month_key)):
            if key not in bucket:
                bucket[key] = {"wins": 0, "losses": 0}
            if profit > 0:
                bucket[key]["wins"] += 1
            else:
                bucket[key]["losses"] += 1

    return {"day": day_b, "week": week_b, "month": month_b}


def _enrich_wl(data: list, bucket: dict) -> list:
    """Add winning_trades / losing_trades to each period row."""
    for row in data:
        key = str(row.get("date", ""))[:10]
        if key in bucket:
            row["winning_trades"] = bucket[key]["wins"]
            row["losing_trades"] = bucket[key]["losses"]
    return data


@app.get("/api/performance/daily")
async def performance_daily(days: int = Query(30, ge=1, le=365), _: dict = Depends(require_auth)):
    # Fetch FreqTrade data and W/L buckets in parallel
    ft_result, wl = await asyncio.gather(
        ft_get("/daily", params={"timescale": days}),
        _trade_wl_buckets(),
    )
    data = ft_result.get("data", ft_result) if isinstance(ft_result, dict) else ft_result
    return _enrich_wl(data, wl["day"]) if isinstance(data, list) else data


@app.get("/api/performance/weekly")
async def performance_weekly(weeks: int = Query(12, ge=1, le=52), _: dict = Depends(require_auth)):
    ft_result, wl = await asyncio.gather(
        ft_get("/weekly", params={"timescale": weeks}),
        _trade_wl_buckets(),
    )
    data = ft_result.get("data", ft_result) if isinstance(ft_result, dict) else ft_result
    return _enrich_wl(data, wl["week"]) if isinstance(data, list) else data


@app.get("/api/performance/monthly")
async def performance_monthly(months: int = Query(6, ge=1, le=24), _: dict = Depends(require_auth)):
    ft_result, wl = await asyncio.gather(
        ft_get("/monthly", params={"timescale": months}),
        _trade_wl_buckets(),
    )
    data = ft_result.get("data", ft_result) if isinstance(ft_result, dict) else ft_result
    return _enrich_wl(data, wl["month"]) if isinstance(data, list) else data


@app.get("/api/performance/pair")
async def performance_pair(_: dict = Depends(require_auth)):
    """Compute per-pair stats (WR, PF, P&L, avg duration) from closed trades.

    FreqTrade's /performance only returns profit_abs+count — no win_ratio,
    profit_factor or duration_avg. We compute everything from /trades instead.
    """
    # Fetch up to 1000 closed trades (single request covers most bots)
    result = await ft_get("/trades", params={"limit": 1000, "offset": 0, "order_by_id": "false"})
    all_trades = result.get("trades", []) if isinstance(result, dict) else []

    # Only closed trades (have a close_timestamp)
    closed = [t for t in all_trades if t.get("close_timestamp") and t.get("close_timestamp", 0) > 0]

    def _norm_pair(p: str) -> str:
        """Normalize pair name: strip futures settlement suffix.
        BTC/USDT:USDT → BTC/USDT  (groups old spot + futures trades together)"""
        return p.split(":")[0] if ":" in p else p

    # Group by normalized pair (merges e.g. BTC/USDT and BTC/USDT:USDT)
    by_pair: dict[str, list] = {}
    for t in closed:
        by_pair.setdefault(_norm_pair(t.get("pair", "unknown")), []).append(t)

    rows = []
    for pair, ptrades in by_pair.items():
        profits = [t.get("profit_abs") or 0.0 for t in ptrades]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]

        total_profit = sum(profits)
        win_ratio = len(wins) / len(ptrades) if ptrades else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        # Capital view (2026-06-24 UI redesign): how much was actually committed
        # to this pair, what came back, and the return on that capital.
        total_staked = sum(t.get("stake_amount") or 0.0 for t in ptrades)
        total_returned = total_staked + total_profit
        roi_pct = (total_profit / total_staked) if total_staked > 0 else None

        durations = []
        for t in ptrades:
            ct = t.get("close_timestamp") or 0
            ot = t.get("open_timestamp") or 0
            if ct > 0 and ot > 0:
                durations.append((ct - ot) / 1000 / 60)  # seconds→minutes
        duration_avg = sum(durations) / len(durations) if durations else None

        rows.append({
            "key": pair,
            "pair": pair,
            "count": len(ptrades),
            "win_ratio": win_ratio,
            "profit_factor": profit_factor,
            "profit_all_coin": total_profit,
            "profit_abs": total_profit,
            "duration_avg": duration_avg,  # minutes
            "invested": total_staked,
            "returned": total_returned,
            "roi_pct": roi_pct,
        })

    # Sort best P&L first
    rows.sort(key=lambda r: r["profit_all_coin"], reverse=True)
    return rows


@app.get("/api/profit")
async def profit_summary(_: dict = Depends(require_auth)):
    return await ft_get("/profit")


@app.get("/api/balance")
async def balance(_: dict = Depends(require_auth)):
    return await ft_get("/balance")


@app.get("/api/whitelist")
async def whitelist(_: dict = Depends(require_auth)):
    return await ft_get("/whitelist")


_ENV_FILE = REPO_ROOT / "freqtrade" / ".env"
_STRATEGY_FILE = REPO_ROOT / "freqtrade/user_data/strategies/CortexaAI_v23.py"


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE .env file, skip comments and blanks."""
    result: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    except OSError:
        pass
    return result


def _extract_startup_candles(path: Path) -> Optional[int]:
    """Grep strategy file for startup_candle_count = N."""
    try:
        m = re.search(r"startup_candle_count\s*[=:]\s*(\d+)", path.read_text())
        return int(m.group(1)) if m else None
    except OSError:
        return None


@app.get("/api/config")
async def get_config(_: dict = Depends(require_auth)):
    """Return live config with nested freqai/exchange/env_vars for the Settings tab."""
    if not CONFIG_JSON.exists():
        return {"available": False}
    try:
        with open(CONFIG_JSON) as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "error": "unreadable"}

    freqai = cfg.get("freqai", {}) or {}
    fp = freqai.get("feature_parameters", {}) or {}
    exchange_cfg = cfg.get("exchange", {}) or {}

    # Read live env vars from .env file (what's actually injected into the container)
    env_vars_raw = _read_env_file(_ENV_FILE)
    env_vars = {
        k: env_vars_raw.get(k)
        for k in (
            "FREQAI_LONG_THRESHOLD", "FREQAI_SHORT_THRESHOLD",
            "FREQAI_K_TP", "FREQAI_K_SL",
            "FREQAI_STABILITY_N", "FREQAI_DAILY_LOSS_LIMIT",
            "FREQAI_FEATURE_SET", "FREQAI_ML_THRESHOLD",
            "FREQAI_LEV_HIGH", "FREQAI_LEV_MED", "FREQAI_LEV_LOW",
        )
        if env_vars_raw.get(k) is not None
    }

    startup_cc = (
        fp.get("startup_candle_count")
        or cfg.get("startup_candle_count")
        or _extract_startup_candles(_STRATEGY_FILE)
    )

    return {
        # Flat fields (backwards compat)
        "strategy": cfg.get("strategy"),
        "max_open_trades": cfg.get("max_open_trades"),
        "stake_currency": cfg.get("stake_currency"),
        "stake_amount": cfg.get("stake_amount"),
        "dry_run": cfg.get("dry_run"),
        "dry_run_wallet": cfg.get("dry_run_wallet"),
        "timeframe": cfg.get("timeframe"),
        "stoploss": cfg.get("stoploss"),
        "trailing_stop": cfg.get("trailing_stop"),
        "freqai_identifier": freqai.get("identifier"),
        "live_retrain_hours": freqai.get("live_retrain_hours"),
        "startup_candle_count": startup_cc,
        "pair_whitelist": exchange_cfg.get("pair_whitelist", []),
        "pair_blacklist": exchange_cfg.get("pair_blacklist", []),
        # Nested structure for Settings.jsx
        "freqai": {
            "identifier": freqai.get("identifier"),
            "live_retrain_hours": freqai.get("live_retrain_hours"),
            "startup_candle_count": startup_cc,
        },
        "exchange": {
            "name": exchange_cfg.get("name"),
            "futures_mode": exchange_cfg.get("futures_mode", "isolated"),
        },
        "env_vars": env_vars,
    }


# ───────────────────── Timeframe switcher ─────────────────────
TIMEFRAME_PROFILES = REPO_ROOT / "finbuddy_memory/timeframe_profiles.json"
TIMEFRAME_STATUS = REPO_ROOT / "finbuddy_memory/timeframe_switch_status.json"
FEATURE_IC_FILE = REPO_ROOT / "finbuddy_memory/analytics/feature_ic.json"
FEATURE_IC_BY_TF = REPO_ROOT / "finbuddy_memory/analytics/feature_ic_by_tf.json"
APPLY_TF_SCRIPT = REPO_ROOT / "scripts/apply_timeframe.py"
MODELS_DIR = REPO_ROOT / "freqtrade/user_data/models"
TF_SWITCH_LOG = Path("/home/ubuntu/.finbuddy/logs/timeframe_switch.log")
DATA_FUTURES_DIR = REPO_ROOT / "freqtrade/user_data/data/binance/futures"

# ───────────────────── Funding farm ─────────────────────
FUNDING_PARQUET = REPO_ROOT / "finbuddy_memory/historical/funding_perpair.parquet"
FUNDING_FARM_STATE = REPO_ROOT / "finbuddy_memory/funding_farm/state.json"
FUNDING_FARM_SCANNER_LOG = Path("/home/ubuntu/.finbuddy/logs/funding_farm.log")
FUNDING_MIN_APR = 0.15   # same threshold as scanner.py


def _load_tf_profiles() -> dict:
    try:
        return json.loads(TIMEFRAME_PROFILES.read_text())
    except (OSError, json.JSONDecodeError):
        return {"active": None, "available": [], "profiles": {}, "history": []}


def _tf_status() -> dict:
    """Switch status + health: is the (new) model trained & present?"""
    prof = _load_tf_profiles()
    out: dict[str, Any] = {"active": prof.get("active"), "state": "idle"}
    if TIMEFRAME_STATUS.exists():
        try:
            out.update(json.loads(TIMEFRAME_STATUS.read_text()))
        except (OSError, json.JSONDecodeError):
            pass
    # health: does the live identifier's model dir exist + how fresh
    identifier = out.get("identifier")
    if not identifier and CONFIG_JSON.exists():
        try:
            identifier = json.loads(CONFIG_JSON.read_text()).get("freqai", {}).get("identifier")
        except (OSError, json.JSONDecodeError):
            identifier = None
    model_present, model_age_min = False, None
    if identifier:
        mdir = MODELS_DIR / identifier
        if mdir.is_dir():
            subs = [p for p in mdir.glob("sub-train*") if p.is_dir()] or [mdir]
            newest = max((p.stat().st_mtime for p in subs), default=mdir.stat().st_mtime)
            model_present = True
            model_age_min = round((time.time() - newest) / 60.0, 1)
    out["identifier"] = identifier
    out["model_present"] = model_present
    out["model_age_min"] = model_age_min
    # Self-healing: if model is present but status file is stuck in "training"
    # (apply_timeframe.py never writes "idle" after training completes), auto-flip to idle.
    # This prevents the dashboard from showing "Retraining..." for days after a switch.
    if out.get("state") == "training" and model_present:
        out["state"] = "idle"
        # Also patch the file so next read is correct without waiting for the streamer
        try:
            d = json.loads(TIMEFRAME_STATUS.read_text())
            d["state"] = "idle"
            d["ready"] = True
            TIMEFRAME_STATUS.write_text(json.dumps(d, indent=2))
        except Exception:
            pass
    out["ready"] = model_present
    return out


@app.get("/api/timeframe")
async def get_timeframe(_: dict = Depends(require_auth)):
    prof = _load_tf_profiles()
    ic = {}
    for f in (FEATURE_IC_BY_TF, FEATURE_IC_FILE):
        if f.exists():
            try:
                ic = json.loads(f.read_text()); break
            except (OSError, json.JSONDecodeError):
                pass
    # data_warnings: per-TF feather count so the confirm modal can warn if data is sparse
    available = prof.get("available", [])
    data_warnings: dict[str, str | None] = {}
    if DATA_FUTURES_DIR.is_dir():
        for tf in available:
            n = len(list(DATA_FUTURES_DIR.glob(f"*-{tf}-futures.feather")))
            data_warnings[tf] = None if n >= 10 else f"{n}/26 pairs have {tf} data"
    return {
        "active": prof.get("active"),
        "available": available,
        "profiles": prof.get("profiles", {}),
        "history": prof.get("history", [])[-10:],
        "status": _tf_status(),
        "ic_by_tf": ic,
        "data_warnings": data_warnings,
    }


@app.get("/api/timeframe/status")
async def get_timeframe_status(_: dict = Depends(require_auth)):
    return _tf_status()


@app.get("/api/feature-ic")
async def get_feature_ic(_: dict = Depends(require_auth)):
    for f in (FEATURE_IC_BY_TF, FEATURE_IC_FILE):
        if f.exists():
            try:
                return json.loads(f.read_text())
            except (OSError, json.JSONDecodeError):
                pass
    return {"available": False}


class TimeframeSwitchIn(BaseModel):
    timeframe: str


def _spawn_apply(args: list[str]) -> None:
    """Spawn apply_timeframe.py detached so the HTTP call returns immediately while the
    retrain proceeds in the background. Output → timeframe_switch.log."""
    TF_SWITCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = open(TF_SWITCH_LOG, "a")
    subprocess.Popen(
        [sys.executable, str(APPLY_TF_SCRIPT)] + args,
        cwd=str(REPO_ROOT), stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )


@app.post("/api/timeframe/switch")
async def switch_timeframe(body: TimeframeSwitchIn, _: dict = Depends(require_auth)):
    prof = _load_tf_profiles()
    allowed = prof.get("available", [])
    # STRICT allowlist — tf is passed as a single argv token; never accept anything else.
    if body.timeframe not in allowed:
        raise HTTPException(status_code=400, detail=f"timeframe must be one of {allowed}")
    if body.timeframe == prof.get("active"):
        return {"accepted": False, "reason": "already active", "active": prof.get("active")}
    _spawn_apply([body.timeframe])
    return {"accepted": True, "timeframe": body.timeframe,
            "note": "Switch started — retraining all pairs (~hours). Poll /api/timeframe/status."}


@app.post("/api/timeframe/rollback")
async def rollback_timeframe(_: dict = Depends(require_auth)):
    prof = _load_tf_profiles()
    if not prof.get("history"):
        raise HTTPException(status_code=400, detail="no history to roll back to")
    _spawn_apply(["--rollback"])
    return {"accepted": True, "note": "Rollback started — poll /api/timeframe/status."}


@app.get("/api/funding-farm")
async def funding_farm(_: dict = Depends(require_auth)):
    """Live funding-farm monitor: current APR per symbol vs the 15% entry threshold.
    Lets Gaurav see the gap to opportunity without SSH. Farm is correctly dormant in bear
    market (no symbol clears 15% APR); this makes the state visible in the dashboard."""
    def compute():
        import pandas as pd  # lazy import (not always installed in all envs)
        rows: list[dict] = []
        if FUNDING_PARQUET.exists():
            try:
                df = pd.read_parquet(FUNDING_PARQUET)
                # Latest row per symbol → annualize (8h rate × 3 events/day × 365 days)
                latest = df.sort_values("date").groupby("symbol").last().reset_index()
                # 2026-07-08: drop symbols whose funding history is stale (>48h).
                # A delisted contract (TON, SETTLING since 06-23) stops producing
                # funding events — its frozen last row (+387% APR) was shown as a
                # live QUALIFIES opportunity while the real current rate was 0.
                cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=48)
                latest = latest[pd.to_datetime(latest["date"], utc=True) >= cutoff]
                for _, r in latest.iterrows():
                    rate = float(r.get("funding_rate") or 0.0)
                    apr = rate * 3 * 365  # Binance 8h funding → APR
                    sym = str(r["symbol"])
                    rows.append({
                        "symbol": sym,
                        "apr": round(apr, 4),
                        "gap_to_threshold": round(max(0.0, FUNDING_MIN_APR - abs(apr)), 4),
                        "funding_rate": round(rate, 6),
                        "at_threshold": abs(apr) >= FUNDING_MIN_APR,
                    })
                rows.sort(key=lambda x: abs(x["apr"]), reverse=True)
            except Exception as e:
                rows = [{"error": str(e)}]

        # Farm state (open paper positions + realized PnL)
        state: dict = {}
        if FUNDING_FARM_STATE.exists():
            try:
                state = json.loads(FUNDING_FARM_STATE.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        # Last scanner run timestamp from log
        last_scan: str | None = None
        if FUNDING_FARM_SCANNER_LOG.exists():
            try:
                lines = FUNDING_FARM_SCANNER_LOG.read_text().splitlines()
                for ln in reversed(lines[-50:]):
                    if "scanner" in ln.lower() or "scan" in ln.lower() or "checking" in ln.lower():
                        last_scan = ln[:25].strip(); break
            except OSError:
                pass

        best = rows[0] if rows and "error" not in rows[0] else None
        return {
            "symbols": rows[:10],  # top 10 by |APR|
            "best_apr": best["apr"] if best else None,
            "best_symbol": best["symbol"] if best else None,
            "threshold": FUNDING_MIN_APR,
            "threshold_pct": round(FUNDING_MIN_APR * 100, 1),
            "positions": state.get("positions", {}),
            "realized_pnl": state.get("realized_pnl", 0.0),
            "last_accrual": state.get("last_accrual"),
            "last_scan": last_scan,
        }

    return await asyncio.get_event_loop().run_in_executor(None, compute)


# ───────────────────── Arbitrage (paper) ─────────────────────
ARBITRAGE_STATE = REPO_ROOT / "finbuddy_memory/arbitrage/state.json"
ARBITRAGE_LEDGER = REPO_ROOT / "finbuddy_memory/arbitrage/ledger.jsonl"
ARBITRAGE_PRICE_CACHE = REPO_ROOT / "finbuddy_memory/arbitrage/price_cache.json"
ARBITRAGE_FEED_STALE_S = 60.0  # feed daemon flushes every 5s — this stale means it's down


@app.get("/api/arbitrage")
async def arbitrage(_: dict = Depends(require_auth)):
    """Live arbitrage (paper) monitor: wallet/P&L, recent captures/observations,
    and whether the price-feed daemon is actually alive (a dead feed silently
    stops finding anything, so surface it explicitly rather than just showing
    zero opportunities indistinguishably from a healthy-but-quiet market)."""
    def compute():
        state: dict = {}
        if ARBITRAGE_STATE.exists():
            try:
                state = json.loads(ARBITRAGE_STATE.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        feed_alive = False
        feed_age_s: float | None = None
        exchanges_reporting = 0
        if ARBITRAGE_PRICE_CACHE.exists():
            try:
                cache = json.loads(ARBITRAGE_PRICE_CACHE.read_text())
                updated_at = cache.get("updated_at", 0.0)
                feed_age_s = round(time.time() - updated_at, 1)
                feed_alive = feed_age_s < ARBITRAGE_FEED_STALE_S
                exchanges_reporting = len({
                    v.get("exchange") for v in cache.get("prices", {}).values()
                })
            except (OSError, json.JSONDecodeError):
                pass

        # Last 20 ledger events (captures + observations), newest first
        recent: list[dict] = []
        if ARBITRAGE_LEDGER.exists():
            try:
                lines = ARBITRAGE_LEDGER.read_text().splitlines()
                for ln in reversed(lines[-100:]):
                    try:
                        recent.append(json.loads(ln))
                    except json.JSONDecodeError:
                        continue
                    if len(recent) >= 20:
                        break
            except OSError:
                pass

        return {
            "wallet_usdt": state.get("wallet_usdt"),
            "realized_pnl": state.get("realized_pnl", 0.0),
            "captures_total": state.get("captures", 0),
            "observations_total": state.get("observations", 0),
            "last_run": state.get("last_run"),
            "feed_alive": feed_alive,
            "feed_age_s": feed_age_s,
            "exchanges_reporting": exchanges_reporting,
            "recent_events": recent,
        }

    return await asyncio.get_event_loop().run_in_executor(None, compute)


@app.get("/api/signal-quality")
async def signal_quality(_: dict = Depends(require_auth)):
    """Live model health: do_predict ratio, entry rate, prediction distribution.
    Answers 'is the model healthy right now?' without digging through logs."""
    async def compute():
        # Sample BTC + ETH from pair_candles (last 200 candles = ~3d at 1h)
        cfg_tf = "1h"
        if CONFIG_JSON.exists():
            try:
                cfg_tf = json.loads(CONFIG_JSON.read_text()).get("timeframe", "1h")
            except (OSError, json.JSONDecodeError):
                pass

        agg = {"do_predict_total": 0, "do_predict_1": 0, "pred_values": [],
               "pairs_sampled": 0, "entry_long": 0, "entry_short": 0}
        for pair in ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]:
            try:
                cd = await ft_get("/pair_candles", params={"pair": pair, "timeframe": cfg_tf, "limit": 100})
                cols = cd.get("columns", [])
                data = cd.get("data", [])
                if not cols or not data:
                    continue
                dp_idx = cols.index("do_predict") if "do_predict" in cols else None
                pred_idx = cols.index("&-future_return") if "&-future_return" in cols else None
                el_idx = cols.index("enter_long") if "enter_long" in cols else None
                es_idx = cols.index("enter_short") if "enter_short" in cols else None
                for row in data[:-1]:  # skip forming candle
                    if dp_idx is not None:
                        agg["do_predict_total"] += 1
                        if (row[dp_idx] or 0) == 1:
                            agg["do_predict_1"] += 1
                    if pred_idx is not None and row[pred_idx] is not None:
                        agg["pred_values"].append(float(row[pred_idx]))
                    if el_idx is not None and (row[el_idx] or 0) == 1:
                        agg["entry_long"] += 1
                    if es_idx is not None and (row[es_idx] or 0) == 1:
                        agg["entry_short"] += 1
                agg["pairs_sampled"] += 1
            except Exception:
                continue

        import statistics
        preds = agg["pred_values"]
        return {
            "do_predict_ratio": round(agg["do_predict_1"] / agg["do_predict_total"], 3)
                                 if agg["do_predict_total"] else None,
            "do_predict_1": agg["do_predict_1"],
            "do_predict_total": agg["do_predict_total"],
            "entry_long_count": agg["entry_long"],
            "entry_short_count": agg["entry_short"],
            "pred_mean": round(statistics.mean(preds), 4) if preds else None,
            "pred_stdev": round(statistics.stdev(preds), 4) if len(preds) > 1 else None,
            "pairs_sampled": agg["pairs_sampled"],
            "timeframe": cfg_tf,
        }

    return await compute()


# ───────────────────── WF Coverage + Flatten + Params ─────────────────────

# Reverse-lookup: config_file basename → inferred TF
_CFG_TO_TF = {
    "v23_regression_15m_di_config.json": "15m",
    "v23_regression_15m_pruned_config.json": "15m",
    "v23_regression_15m_config.json": "15m",
    "v23_regression_30m_config.json": "30m",
    "v23_regression_1h_config.json": "1h",
    "v23_regression_4h_config.json": "4h",
}


@app.get("/api/wf/coverage")
async def wf_coverage(_: dict = Depends(require_auth)):
    """WF coverage heatmap: (TF × window) → {total, passed, best_profit}.
    Reads experiment log.jsonl and infers TF from config_file field."""
    coverage: dict[str, dict[str, dict]] = {}
    tfs_seen: set[str] = set()
    windows_seen: set[str] = set()
    total = 0
    try:
        for line in EXP_LOG_FILE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            status = e.get("status", "")
            if status not in ("completed", "scout_failed", "failed"):
                continue
            cfg_file = e.get("config_file") or e.get("hypothesis", {}).get("config_file", "")
            tf = _CFG_TO_TF.get(cfg_file.split("/")[-1] if cfg_file else "", "15m")
            window = e.get("window", "unknown")
            metrics = e.get("metrics") or {}
            profit = metrics.get("profit_pct") or metrics.get("profit") or 0.0
            passed = status == "completed" and (profit or 0) > 0
            tfs_seen.add(tf)
            windows_seen.add(window)
            total += 1
            cell = coverage.setdefault(tf, {}).setdefault(window, {"total": 0, "passed": 0, "best_profit": None})
            cell["total"] += 1
            if passed:
                cell["passed"] += 1
            if profit is not None:
                if cell["best_profit"] is None or profit > cell["best_profit"]:
                    cell["best_profit"] = round(profit, 4)
    except OSError:
        pass
    # Canonical window order (chronological)
    _WINDOW_ORDER = ["bull_2021", "crash_2022", "bull_2024Q1", "bear_2024Q2",
                     "bull_2024Q4", "bear_2025Q1", "bear_2025Q4", "bear_2026Q1"]
    ordered_windows = [w for w in _WINDOW_ORDER if w in windows_seen]
    ordered_windows += sorted(w for w in windows_seen if w not in _WINDOW_ORDER)
    return {
        "coverage": coverage,
        "tfs_seen": sorted(tfs_seen, key=lambda t: ["15m", "30m", "1h", "4h"].index(t) if t in ["15m","30m","1h","4h"] else 99),
        "windows_seen": ordered_windows,
        "total_experiments": total,
    }


@app.post("/api/timeframe/flatten")
async def flatten_trades(_: dict = Depends(require_auth)):
    """Close all open trades before a timeframe switch to avoid holding stale-model positions.

    Fixed 2026-07-14: this used to call DELETE /trades/{id} per trade, which
    cancels open orders and deletes the LOCAL DB ROW — it never fetches a price
    or places an exit order. Invisible in dry-run (a "trade" is just a DB row
    there); in live trading it would silently abandon a real exchange position
    while FreqTrade forgets it ever existed. Uses FreqTrade's native
    tradeid="all" support instead — one real forceexit call that atomically
    exits every open trade under the exchange's own exit lock, same mechanism
    as the new per-trade force_exit_trade() endpoint above.
    """
    try:
        open_trades = await ft_get("/status")
        n_before = len(open_trades) if isinstance(open_trades, list) else 0
    except HTTPException:
        n_before = 0

    if n_before == 0:
        return {"closed": 0, "errors": [], "message": "No open trades to close."}

    try:
        r = await ft_post("/forceexit", {"tradeid": "all", "ordertype": "market"})
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        _append_override_log({"action": "flatten_all", "channel": "dashboard",
                               "result": "error", "ft_response": str(e)})
        raise HTTPException(status_code=502, detail=f"FreqTrade API error: {e}") from e

    ok = r.status_code == 200
    body = r.json() if ok else {}
    _append_override_log({
        "action": "flatten_all", "channel": "dashboard",
        "result": "ok" if ok else "error",
        "trades_before": n_before,
        "ft_response": body or r.text[:300],
    })
    if not ok:
        return {"closed": 0, "errors": [r.text[:300]], "message": "Flatten failed — see errors."}
    return {"closed": n_before, "errors": [],
            "message": f"Closed {n_before} trade{'s' if n_before != 1 else ''} before timeframe switch."}


class ParamsIn(BaseModel):
    long_threshold: float | None = None
    short_threshold: float | None = None
    k_tp: float | None = None
    k_sl: float | None = None


@app.post("/api/params")
async def update_params(body: ParamsIn, _: dict = Depends(require_auth)):
    """Update live strategy params by writing to .env and restarting the container.
    Uses docker-compose restart (not up -d) — no model reload, just env reload."""
    _PARAM_MAP = {
        "long_threshold":  "FREQAI_LONG_THRESHOLD",
        "short_threshold": "FREQAI_SHORT_THRESHOLD",
        "k_tp":            "FREQAI_K_TP",
        "k_sl":            "FREQAI_K_SL",
    }
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No params provided")
    # Read and patch .env
    lines = _ENV_FILE.read_text().splitlines() if _ENV_FILE.exists() else []
    env_keys_to_update = {_PARAM_MAP[k]: str(v) for k, v in updates.items()}
    out = [ln for ln in lines if ln.split("=", 1)[0] not in env_keys_to_update]
    out += [f"{k}={v}" for k, v in env_keys_to_update.items()]
    _ENV_FILE.write_text("\n".join(out) + "\n")
    # Restart container (env-only change — no model reload needed)
    import subprocess as _sp
    try:
        _sp.run(
            ["docker-compose", "restart", "freqtrade"],
            cwd=str(REPO_ROOT / "freqtrade"),
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restart failed: {e}") from e
    return {"applied": updates, "message": f"Updated {list(updates.keys())} and restarted FreqTrade."}


# ───────────────────── Exit reasons + Recent trades ─────────────────────

@app.get("/api/stats/exit-reasons")
async def exit_reasons_stats(_: dict = Depends(require_auth)):
    """Aggregate closed trades by exit reason — diagnostic tool for stop-loss analysis."""
    async def compute():
        result = await ft_get("/trades", params={"limit": 1000, "offset": 0})
        all_trades = result.get("trades", []) if isinstance(result, dict) else []
        closed = [t for t in all_trades if t.get("exit_reason") and t.get("close_timestamp")]

        reasons: dict[str, dict] = {}
        for t in closed:
            r = t.get("exit_reason") or "unknown"
            if r not in reasons:
                reasons[r] = {"count": 0, "wins": 0, "losses": 0, "profit": 0.0}
            reasons[r]["count"] += 1
            p = float(t.get("profit_abs") or 0.0)
            reasons[r]["profit"] += p
            if p > 0:
                reasons[r]["wins"] += 1
            else:
                reasons[r]["losses"] += 1

        items = [
            {
                "reason": k,
                "count": v["count"],
                "wins": v["wins"],
                "losses": v["losses"],
                "profit": round(v["profit"], 4),
                "wr": round(v["wins"] / v["count"], 4) if v["count"] else 0.0,
            }
            for k, v in reasons.items()
        ]
        items.sort(key=lambda x: x["count"], reverse=True)
        return {"items": items}

    return await cached_async("exit_reasons", 60.0, compute)


@app.get("/api/performance/side-split")
async def performance_side_split(_: dict = Depends(require_auth)):
    """Split closed-trade performance into LONG-only vs SHORT-only.

    The directional strategy bleeds asymmetrically (longs vs shorts behave very
    differently in a given regime). This makes that split visible: per-side P&L,
    win-rate, trade count, avg P&L, plus a daily cumulative series per side for
    two equity curves.
    """
    async def compute():
        result = await ft_get("/trades", params={"limit": 1000, "offset": 0})
        all_trades = result.get("trades", []) if isinstance(result, dict) else []
        closed = [t for t in all_trades if t.get("close_timestamp")]

        def side_summary(trades: list) -> dict:
            n = len(trades)
            profits = [float(t.get("profit_abs") or 0.0) for t in trades]
            wins = sum(1 for p in profits if p > 0)
            total = sum(profits)
            return {
                "count": n,
                "wins": wins,
                "losses": n - wins,
                "wr": round(wins / n, 4) if n else None,
                "profit": round(total, 4),
                "avg_profit": round(total / n, 4) if n else None,
            }

        longs = [t for t in closed if not t.get("is_short")]
        shorts = [t for t in closed if t.get("is_short")]

        # Daily cumulative P&L per side (for two equity curves)
        def daily_series(trades: list) -> list:
            by_day: dict[str, float] = {}
            for t in trades:
                cd = str(t.get("close_date") or "")[:10]
                if not cd:
                    continue
                by_day[cd] = by_day.get(cd, 0.0) + float(t.get("profit_abs") or 0.0)
            cum = 0.0
            out = []
            for day in sorted(by_day):
                cum += by_day[day]
                out.append({"date": day, "value": round(cum, 4)})
            return out

        return {
            "long": side_summary(longs),
            "short": side_summary(shorts),
            "long_series": daily_series(longs),
            "short_series": daily_series(shorts),
        }

    return await cached_async("side_split", 60.0, compute)


@app.get("/api/pairs/scan")
async def pairs_scan(_: dict = Depends(require_auth)):
    """Live preview for the (not-yet-live) Pairs Trading module.

    Read-only cointegration-lite scanner over the whitelist's 1h closes: finds
    highly-correlated coin pairs whose price spread has drifted far from its mean
    (a mean-reversion candidate). Pure pandas/numpy — no statsmodels, no trading.

    For each correlated pair (corr>0.8): hedge ratio beta (OLS on log prices),
    current spread z-score, and a mean-reversion half-life (AR(1)). |z|>=2 is the
    classic entry zone. This sells the module's vision with real, current data.
    """
    LOOK = 720  # ~30 days of 1h candles

    def compute():
        import pandas as pd
        import numpy as np
        try:
            cfg = json.loads((REPO_ROOT / "freqtrade/user_data/config.json").read_text())
            wl = cfg.get("exchange", {}).get("pair_whitelist", [])
            closes: dict[str, "pd.Series"] = {}
            for p in wl:
                base = p.split("/")[0]
                f = DATA_FUTURES_DIR / f"{base}_USDT_USDT-1h-futures.feather"
                if not f.exists():
                    continue
                try:
                    s = pd.read_feather(f).set_index("date")["close"].tail(LOOK)
                except Exception:
                    continue
                if len(s) >= LOOK * 0.8:
                    closes[base] = s
            if len(closes) < 2:
                return {"pairs": [], "scanned": len(closes), "candidates": 0,
                        "lookback_h": LOOK, "note": "not enough price data"}

            px = pd.DataFrame(closes).dropna()
            logp = np.log(px)
            corr = logp.diff().dropna().corr()
            syms = list(px.columns)
            out = []
            for i in range(len(syms)):
                for j in range(i + 1, len(syms)):
                    a, b = syms[i], syms[j]
                    cc = float(corr.loc[a, b])
                    if cc < 0.8:
                        continue
                    beta = float(np.polyfit(logp[b].values, logp[a].values, 1)[0])
                    if beta <= 0:
                        continue
                    spread = logp[a] - beta * logp[b]
                    sd = float(spread.std())
                    if sd == 0:
                        continue
                    z = float((spread.iloc[-1] - float(spread.mean())) / sd)
                    # Mean-reversion half-life via AR(1): Δs = λ·s_{t-1} + c
                    sv = spread.values
                    lam = float(np.polyfit(sv[:-1], np.diff(sv), 1)[0])
                    hl = -np.log(2) / lam if lam < 0 else None
                    if z <= -2:
                        signal = f"long {a} / short {b}"
                    elif z >= 2:
                        signal = f"short {a} / long {b}"
                    else:
                        signal = "in range"
                    out.append({
                        "a": a, "b": b,
                        "corr": round(cc, 3),
                        "beta": round(beta, 3),
                        "z": round(z, 2),
                        "half_life_h": round(hl, 1) if (hl and 0 < hl < 2000) else None,
                        "signal": signal,
                    })
            out.sort(key=lambda r: abs(r["z"]), reverse=True)
            return {"pairs": out[:25], "scanned": len(closes),
                    "candidates": len(out), "lookback_h": LOOK}
        except Exception as e:  # never break the dashboard
            return {"error": str(e), "pairs": []}

    return await cached_async(
        "pairs_scan", 900.0,
        lambda: asyncio.get_event_loop().run_in_executor(None, compute),
    )


@app.get("/api/grid/scan")
async def grid_scan(_: dict = Depends(require_auth)):
    """Live preview for the (not-yet-live) Grid Trading module.

    Read-only scanner ranking whitelist coins by how grid-friendly they are right
    now: a grid earns from oscillation inside a range, so the ideal coin is
    RANGING (no strong trend) but still moving. Per coin over 14 days of 1h:
      - efficiency ratio (Kaufman): |net move| / total path. Low = choppy/ranging
        (good for grid), high = trending (bad — price walks out of the grid).
      - hourly volatility % (the swing a grid harvests).
      - range width % (how wide to set the grid).
    grid_score = volatility · (1 − efficiency_ratio). Pure pandas/numpy.
    """
    LOOK = 336  # ~14 days of 1h candles

    def compute():
        import pandas as pd
        import numpy as np
        try:
            cfg = json.loads((REPO_ROOT / "freqtrade/user_data/config.json").read_text())
            wl = cfg.get("exchange", {}).get("pair_whitelist", [])
            rows = []
            for p in wl:
                base = p.split("/")[0]
                f = DATA_FUTURES_DIR / f"{base}_USDT_USDT-1h-futures.feather"
                if not f.exists():
                    continue
                try:
                    close = pd.read_feather(f).set_index("date")["close"].tail(LOOK)
                except Exception:
                    continue
                if len(close) < LOOK * 0.8:
                    continue
                net = abs(float(close.iloc[-1]) - float(close.iloc[0]))
                path = float(close.diff().abs().sum())
                er = (net / path) if path > 0 else 1.0
                vol = float(close.pct_change().std() * 100)
                mean = float(close.mean())
                rng = float((close.max() - close.min()) / mean * 100) if mean else 0.0
                score = vol * (1 - er)
                if er < 0.3 and vol > 0.5:
                    verdict = "ranging — good"
                elif er > 0.5:
                    verdict = "trending — skip"
                else:
                    verdict = "mixed"
                rows.append({
                    "symbol": base,
                    "efficiency_ratio": round(er, 3),
                    "volatility_pct": round(vol, 2),
                    "range_pct": round(rng, 1),
                    "grid_score": round(score, 2),
                    "verdict": verdict,
                })
            rows.sort(key=lambda r: r["grid_score"], reverse=True)
            return {"coins": rows, "scanned": len(rows), "lookback_h": LOOK}
        except Exception as e:
            return {"error": str(e), "coins": []}

    return await cached_async(
        "grid_scan", 900.0,
        lambda: asyncio.get_event_loop().run_in_executor(None, compute),
    )


PAIRS_STATE = REPO_ROOT / "finbuddy_memory/pairs_trading/state.json"
GRID_STATE = REPO_ROOT / "finbuddy_memory/grid_trading/state.json"


@app.get("/api/pairs/portfolio")
async def pairs_portfolio(_: dict = Depends(require_auth)):
    """Paper Pairs Trading portfolio: open market-neutral positions with live
    mark-to-market, plus realized P&L. Read-only — mirrors the funding farm."""
    def compute():
        import pandas as pd
        if not PAIRS_STATE.exists():
            return {"positions": [], "realized_pnl": 0.0, "open_count": 0,
                    "last_update": None, "note": "no paper positions yet"}
        try:
            state = json.loads(PAIRS_STATE.read_text())
        except (OSError, json.JSONDecodeError):
            return {"positions": [], "realized_pnl": 0.0, "open_count": 0, "last_update": None}

        def last_close(sym: str):
            f = DATA_FUTURES_DIR / f"{sym}_USDT_USDT-1h-futures.feather"
            if not f.exists():
                return None
            try:
                return float(pd.read_feather(f)["close"].iloc[-1])
            except Exception:
                return None

        rows = []
        unreal_total = 0.0
        for key, p in (state.get("positions") or {}).items():
            pa, pb = last_close(p["a"]), last_close(p["b"])
            unreal = None
            if pa and pb:
                ret_a = pa / p["entry_price_a"] - 1.0
                ret_b = pb / p["entry_price_b"] - 1.0
                long_a = p["side"] == 1
                unreal = (p["notional_a"] * (ret_a if long_a else -ret_a)
                          + p["notional_b"] * (-ret_b if long_a else ret_b)
                          - p["fees_paid"])
                unreal_total += unreal
            rows.append({
                "pair": key, "a": p["a"], "b": p["b"], "side": p["side"],
                "trade": (f"long {p['a']} / short {p['b']}" if p["side"] == 1
                          else f"short {p['a']} / long {p['b']}"),
                "entry_z": p.get("entry_z"), "corr": p.get("corr"),
                "beta": p.get("beta"), "notional": round(p["notional_a"] + p["notional_b"], 1),
                "opened_at": p.get("opened_at"),
                "unrealized": round(unreal, 4) if unreal is not None else None,
            })
        rows.sort(key=lambda r: (r["unrealized"] is None, -(r["unrealized"] or 0)))
        return {
            "positions": rows,
            "open_count": len(rows),
            "realized_pnl": round(state.get("realized_pnl", 0.0), 4),
            "unrealized_pnl": round(unreal_total, 4),
            "last_update": state.get("last_update"),
        }

    return await cached_async(
        "pairs_portfolio", 30.0,
        lambda: asyncio.get_event_loop().run_in_executor(None, compute),
    )


@app.get("/api/grid/portfolio")
async def grid_portfolio(_: dict = Depends(require_auth)):
    """Paper Grid Trading portfolio: active virtual grids with accumulated P&L.

    Each grid is a ladder of orders on a ranging coin.  The paper executor
    tallies fill P&L each hourly scan based on how many grid levels price crossed.
    This endpoint returns live grid state + net P&L.  Read-only.
    """
    def compute():
        import pandas as pd
        if not GRID_STATE.exists():
            return {
                "grids": [], "open_count": 0,
                "realized_pnl": 0.0, "open_pnl": 0.0,
                "last_update": None,
                "note": "no paper grids yet — scanner runs hourly at :40",
            }
        try:
            state = json.loads(GRID_STATE.read_text())
        except (OSError, json.JSONDecodeError):
            return {"grids": [], "open_count": 0, "realized_pnl": 0.0,
                    "open_pnl": 0.0, "last_update": None}

        def last_close(sym: str):
            f = DATA_FUTURES_DIR / f"{sym}_USDT_USDT-1h-futures.feather"
            if not f.exists():
                return None
            try:
                return float(pd.read_feather(f)["close"].iloc[-1])
            except Exception:
                return None

        rows = []
        open_pnl = 0.0
        for sym, g in (state.get("grids") or {}).items():
            price = last_close(sym)
            net = round(g.get("accrued_pnl", 0.0) - g.get("fees_paid", 0.0), 4)
            open_pnl += net
            # Is price inside the range?
            in_range = None
            if price is not None:
                in_range = g["low"] <= price <= g["high"]
            rows.append({
                "symbol": sym,
                "low": g["low"],
                "high": g["high"],
                "spacing_pct": g.get("spacing_pct"),
                "er": g.get("er"),
                "vol_pct": g.get("vol_pct"),
                "total_crossings": g.get("total_crossings", 0),
                "accrued_pnl": round(g.get("accrued_pnl", 0.0), 4),
                "fees_paid": round(g.get("fees_paid", 0.0), 4),
                "net_pnl": net,
                "deployed_at": g.get("deployed_at"),
                "last_price": price,
                "in_range": in_range,
            })
        rows.sort(key=lambda r: (r["net_pnl"] is None, -(r["net_pnl"] or 0)))
        return {
            "grids": rows,
            "open_count": len(rows),
            "realized_pnl": round(state.get("realized_pnl", 0.0), 4),
            "open_pnl": round(open_pnl, 4),
            "last_update": state.get("last_update"),
        }

    return await cached_async(
        "grid_portfolio", 30.0,
        lambda: asyncio.get_event_loop().run_in_executor(None, compute),
    )


@app.get("/api/trades/recent")
async def trades_recent(
    limit: int = Query(10, ge=1, le=50), _: dict = Depends(require_auth)
):
    """Return last N closed trades — fast path for Overview recent-trades panel."""
    result = await ft_get("/trades", params={"limit": limit, "offset": 0, "order_by_id": "false"})
    trades = result.get("trades", []) if isinstance(result, dict) else []
    out = []
    for t in trades:
        if not t.get("close_timestamp"):
            continue
        ot = t.get("open_timestamp") or 0
        ct = t.get("close_timestamp") or 0
        out.append({
            "trade_id": t.get("trade_id"),
            "pair": t.get("pair"),
            "is_short": t.get("is_short"),
            "profit_abs": t.get("close_profit_abs") or t.get("profit_abs"),
            "profit_ratio": t.get("close_profit") or t.get("profit_ratio"),
            "close_reason": t.get("exit_reason"),  # FreqTrade uses exit_reason
            "open_date": t.get("open_date"),
            "close_date": t.get("close_date"),
            "duration_seconds": (ct - ot) / 1000 if ot and ct else None,
            # Enrichment (2026-06-24 UI redesign): show entry/exit price + invested amount
            "open_rate": t.get("open_rate"),
            "close_rate": t.get("close_rate"),
            "stake_amount": t.get("stake_amount"),
            "leverage": t.get("leverage"),
        })
    return out


# ───────────────────── WebSockets ─────────────────────
@app.websocket("/ws/brain")
async def websocket_brain(websocket: WebSocket, token: str = Query(None)):
    """Stream brain experiment log (brain_run.log) to the dashboard."""
    if not token or not verify_token(token):
        await websocket.close(code=1008)
        return
    await websocket.accept()

    # Send last 100 lines of brain_run.log as history
    if BRAIN_RUN_LOG.exists():
        try:
            hist = subprocess.check_output(
                ["tail", "-n", "100", str(BRAIN_RUN_LOG)], timeout=5
            ).decode("utf-8", errors="replace")
            for line in hist.splitlines():
                if line.strip():
                    await websocket.send_json({"type": "brain_log", "log": line.strip()})
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            print(f"WS brain history error: {e}", file=sys.stderr)

    # Tail for new lines
    log_path = BRAIN_RUN_LOG if BRAIN_RUN_LOG.exists() else LOG_FILE
    try:
        async with aiofiles.open(log_path, "r") as f:
            await f.seek(0, os.SEEK_END)
            while True:
                line = await f.readline()
                if not line:
                    await asyncio.sleep(1.0)
                    continue
                if line.strip():
                    await websocket.send_json({"type": "brain_log", "log": line.strip()})
    except Exception as e:
        print(f"WS brain stream error: {e}", file=sys.stderr)
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
