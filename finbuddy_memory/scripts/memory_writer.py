#!/usr/bin/env python3
"""
FinBuddy Memory Writer — runs every 15 min.
Reads bot state from all sources and writes Obsidian vault files.
"""
import json, os, requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
VAULT = ROOT / "finbuddy_memory"
FT_API = "http://localhost:8080/api/v1"

def _read_ft_auth() -> tuple[str, str]:
    """Read FreqTrade API credentials from config.json (same as sync_context.py)."""
    try:
        cfg = json.loads((ROOT / "freqtrade/user_data/config.json").read_text())
        api = cfg.get("api_server", {})
        return (api.get("username", "bot"), api.get("password", "REDACTED-FREQTRADE__API_SERVER__PASSWORD"))
    except Exception:
        return ("bot", "REDACTED-FREQTRADE__API_SERVER__PASSWORD")

FT_AUTH = _read_ft_auth()

def ft_get(endpoint, default=None):
    try:
        r = requests.get(f"{FT_API}/{endpoint}", auth=FT_AUTH, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return default or []

def load_json_safe(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default or {}

def write_context():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    regime = load_json_safe(VAULT / "regimes/current.json", {"regime": "UNKNOWN", "confidence": 0})
    combined = load_json_safe(ROOT / "freqtrade/user_data/data/external/combined_context.json", {})

    open_trades = ft_get("status", []) or []
    profit_info = ft_get("profit", {}) or {}

    open_trades_md = ""
    for t in open_trades[:10]:
        pair   = t.get("pair", "?")
        entry  = t.get("open_rate", 0)
        current= t.get("current_rate", 0)
        pnl    = t.get("profit_pct", 0)
        open_trades_md += f"- {pair}: Entry {entry:.2f} | Current {current:.2f} | P&L: {pnl:.2f}%\n"
    if not open_trades_md:
        open_trades_md = "- No open trades\n"

    profit_pct = profit_info.get("profit_all_percent", 0)
    total_trades = profit_info.get("trade_count", 0)
    win_rate = profit_info.get("winning_trades", 0) / max(total_trades, 1) * 100

    context_md = f"""# FinBuddy — Master Context
Last updated: {now}

## Current Regime
Regime: **{regime.get('regime','?')}** | Confidence: {round(regime.get('confidence',0)*100,1)}% | Since: {regime.get('since','?')}

## Market Sentiment
Fear & Greed: {combined.get('fear_greed', '?')} ({combined.get('fear_greed_label', '?')})
BTC Dominance: {combined.get('btc_dominance', '?')}%
News Sentiment: {round(combined.get('news_sentiment_ratio', 0.5) * 100, 1)}% bullish

## Bot Performance
Total Trades: {total_trades} | Win Rate: {round(win_rate, 1)}% | Total P&L: {round(profit_pct, 2)}%

## Open Trades ({len(open_trades)})
{open_trades_md}## Risk Flags
{'- CRASH REGIME — NO NEW ENTRIES' if regime.get('regime') == 'CRASH' else '- None'}
"""

    (VAULT / "CONTEXT.md").write_text(context_md)
    print(f"CONTEXT.md written: {now}")

if __name__ == "__main__":
    write_context()
