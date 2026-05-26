#!/usr/bin/env python3
"""
FinBuddy Daily Telegram Summary

Sends a morning digest to Telegram every day at 8 AM (alongside pair_performance).
Covers what matters most at a glance:
  - Current HMM regime
  - Open trades (count, side breakdown, unrealised P&L)
  - Yesterday's closed-trade P&L
  - Last training age (from file log)
  - Bot uptime / container status

No external dependencies beyond what's already on the server.
Reads from:
  - config.json (Telegram credentials, API)
  - finbuddy_memory/regimes/current.json (regime)
  - FreqTrade REST API (open/closed trades)
  - freqtrade/user_data/logs/freqtrade.log (last training event)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_PATH = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json")
REGIME_PATH = Path("/home/ubuntu/var/www/html/trade/finbuddy_memory/regimes/current.json")
FILE_LOG    = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/logs/freqtrade.log")
API_BASE    = "http://localhost:8080/api/v1"
API_USER    = os.environ.get("FT_USER", "bot")
API_PASS    = os.environ.get("FT_API_PASS", "REDACTED-FREQTRADE__API_SERVER__PASSWORD")
LOG_TS_RE   = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


# ---------- helpers ----------

def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def api_get(path: str) -> dict | list | None:
    url = f"{API_BASE}{path}"
    creds = b64encode(f"{API_USER}:{API_PASS}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"WARN: API {path} failed: {e}", file=sys.stderr)
        return None


def telegram_send(token: str, chat_id: str, msg: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"ERR: telegram failed: {e}", file=sys.stderr)
        return False


def load_telegram_creds() -> tuple[str, str] | None:
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        tg = cfg.get("telegram") or {}
        return tg.get("token"), tg.get("chat_id")
    except Exception:
        return None, None


def current_regime() -> str:
    try:
        data = json.loads(REGIME_PATH.read_text())
        return data.get("regime", "UNKNOWN")
    except Exception:
        return "UNKNOWN"


def last_training_age() -> str:
    """Return human-readable age of most recent 'Done training' in file log."""
    try:
        lines = FILE_LOG.read_text(errors="replace").splitlines()
        last_ts = None
        for line in lines:
            if "Done training" not in line:
                continue
            m = LOG_TS_RE.match(line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            except ValueError:
                pass
        if last_ts is None:
            return "unknown"
        age = now_utc() - last_ts
        h = int(age.total_seconds() // 3600)
        m_ = int((age.total_seconds() % 3600) // 60)
        return f"{h}h {m_}m ago"
    except Exception:
        return "unknown"


def regime_emoji(regime: str) -> str:
    return {
        "BULL": "🟢", "EUPHORIA": "🚀",
        "NEUTRAL": "⚪", "BEAR": "🔴", "CRASH": "💥",
    }.get(regime, "❓")


# ---------- main ----------

def main() -> None:
    token, chat_id = load_telegram_creds()
    if not (token and chat_id):
        print("ERR: no Telegram credentials in config.json", file=sys.stderr)
        sys.exit(1)

    regime = current_regime()
    training_age = last_training_age()

    # Open trades
    open_data = api_get("/status") or []
    open_count = len(open_data)
    longs  = sum(1 for t in open_data if not t.get("is_short", False))
    shorts = open_count - longs
    unreal_pnl = sum(t.get("profit_abs", 0.0) for t in open_data)

    # Yesterday closed trades — fetch wide, sort descending by close_date so the
    # "yesterday" filter works regardless of API ordering.
    # Fix 10 (2026-05-22): use strftime not isoformat() — FreqTrade API returns
    # close_date as "2026-05-21 23:59:59" (space separator), but isoformat() produces
    # "2026-05-21T00:00:00" (T separator). String comparison would be False for all
    # trades since space (0x20) < 'T' (0x54) in ASCII, silently dropping all results.
    yesterday_start = (now_utc() - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%d %H:%M:%S")
    trades_data = api_get(f"/trades?limit=500") or {}
    all_trades = trades_data.get("trades", []) if isinstance(trades_data, dict) else []
    all_trades.sort(key=lambda t: t.get("close_date") or "", reverse=True)
    yesterday_closed = [
        t for t in all_trades
        if t.get("close_date") and t.get("close_date", "") >= yesterday_start
    ]
    yday_pnl = sum(t.get("profit_abs", 0.0) for t in yesterday_closed)
    yday_wins = sum(1 for t in yesterday_closed if t.get("profit_abs", 0) > 0)
    yday_count = len(yesterday_closed)

    # Performance scoped to the CURRENT FreqAI identifier (post-promotion only).
    # We infer the cutoff from the trailing unix timestamp in the identifier name
    # (format: finbuddy_v23_*_<ts>). Pre-promotion trades are reported separately
    # as "Lifetime" so v22's history doesn't mask v23's real P&L.
    cutoff_iso = None
    try:
        import re, json as _json
        cfg_path = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json")
        with cfg_path.open() as f:
            ident = _json.load(f).get("freqai", {}).get("identifier", "")
        m = re.search(r"_(\d{10})$", ident)
        if m:
            cutoff_iso = datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc).isoformat()
    except Exception:
        pass

    if cutoff_iso:
        scoped = [t for t in all_trades if (t.get("close_date") or "") >= cutoff_iso]
        scoped_count = len(scoped)
        scoped_pnl = sum(t.get("profit_abs", 0.0) for t in scoped)
        scoped_wins = sum(1 for t in scoped if t.get("profit_abs", 0) > 0)
        scoped_line = (
            f"{scoped_count} trades · WR {(scoped_wins/scoped_count*100):.0f}% · "
            f"{'%+.2f' % scoped_pnl} USDT (since {cutoff_iso[:10]})"
            if scoped_count else f"0 trades yet (since {cutoff_iso[:10]})"
        )
    else:
        scoped_line = None

    # Lifetime stats (kept for context — spans identifiers)
    profit_data = api_get("/profit") or {}
    total_trades = profit_data.get("trade_count", 0)
    total_pnl = profit_data.get("profit_closed_coin", 0.0)

    # Build message via unified template
    sys.path.insert(0, str(Path(__file__).parent / "lib"))
    from telegram_template import send as tg_send, Subsystem, Status

    yday_line = (
        f"{yday_count} closed · WR {(yday_wins/yday_count*100):.0f}% · {'%+.2f' % yday_pnl} USDT"
        if yday_count else "No closed trades"
    )

    fields = {
        "Regime":          f"{regime_emoji(regime)} {regime}",
        "Last Training":   training_age,
        "Open Trades":     f"{open_count} ({longs}L / {shorts}S) · unreal {'%+.2f' % unreal_pnl} USDT",
        "Yesterday":       yday_line,
    }
    if scoped_line:
        fields["Current Strategy"] = scoped_line
    fields["Lifetime"] = f"{total_trades} trades · {'%+.2f' % total_pnl} USDT"

    ok = tg_send(
        subsystem=Subsystem.DIGEST,
        status=Status.INFO,
        title=f"{now_utc().strftime('%Y-%m-%d')} morning report",
        fields=fields,
        context="Daily 8am digest · no action required",
    )
    print(f"Daily digest sent: {ok}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
