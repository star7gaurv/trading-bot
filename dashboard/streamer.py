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
COMBINED_CTX_FILE = REPO_ROOT / "freqtrade/user_data/data/external/combined_context.json"
FUNDING_CACHE_FILE = REPO_ROOT / "freqtrade/user_data/data/external/funding_rate_cache.json"
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
    allow_origins=["https://trade.star7gaurav.in", "http://localhost:5173", "http://localhost:8502", "http://REDACTED-SERVER_IP:5173"],
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
    replicates FinBuddyFreqAI_v23.populate_entry_trend gate order exactly, so the
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


@app.get("/api/signals")
async def signals(_: dict = Depends(require_auth)):
    """Live per-pair signal monitor: for every whitelisted pair, report the current
    entry signal and the EXACT reason it is / isn't entering. Answers 'why no trades'
    at a glance instead of digging through logs. Read-only (analysed dataframe only)."""
    async def compute():
        wl = await ft_get("/whitelist")
        pairs = wl.get("whitelist", []) if isinstance(wl, dict) else (wl or [])
        blocks = _load_pair_regime_blocks_map()

        async def one(pair: str) -> Optional[dict]:
            try:
                cd = await ft_get("/pair_candles", params={
                    "pair": pair, "timeframe": "15m", "limit": 3,
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
_STRATEGY_FILE = REPO_ROOT / "freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py"


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
