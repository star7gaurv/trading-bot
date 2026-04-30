#!/usr/bin/env python3
"""
FinBuddy Phase 4 — Memory Auto-Writer

Automatically writes trade events, signal results, and regime changes
to the Obsidian memory vault and commits them to GitHub.

Runs every 15 minutes via cron (see setup_cron.sh).

What it does:
  1. Reads FreqTrade trade log from API or JSON export
  2. Reads latest external data (Phase 2 aggregator output)
  3. Appends signal results to finbuddy_memory/signals/log.md
  4. Updates finbuddy_memory/regimes/current.md with latest market state
  5. Writes daily summary to finbuddy_memory/research/YYYY-MM-DD-daily.md
  6. Git commits everything to gaurav branch

Status: Phase 4 — NEEDS REVIEW by Claude Code after Phase 2 external data is live
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# --- Paths ---
REPO_ROOT   = Path(os.getenv("REPO_ROOT",   "/home/ubuntu/var/www/html/trade/freqtrade"))
VAULT_ROOT  = REPO_ROOT / "finbuddy_memory"
SIGNAL_LOG  = VAULT_ROOT / "signals" / "log.md"
REGIME_FILE = VAULT_ROOT / "regimes" / "current.md"
RESEARCH_DIR = VAULT_ROOT / "research"

# FreqTrade API (local)
FT_API_BASE = os.getenv("FT_API_BASE", "http://localhost:8080")
FT_USER     = os.getenv("FT_API_USER", "bot")
FT_PASS     = os.getenv("FT_API_PASS", "bot123")

# External data file (Phase 2 output)
EXT_DATA    = Path("/tmp/finbuddy_ext_data.json")


# --------------------------------------------------------------------------- #
# FreqTrade API helpers
# --------------------------------------------------------------------------- #

def ft_get(endpoint: str) -> dict | list | None:
    """Call FreqTrade REST API. Returns None on any error."""
    try:
        import requests
        resp = requests.get(
            f"{FT_API_BASE}/api/v1{endpoint}",
            auth=(FT_USER, FT_PASS),
            timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [FT API] {endpoint} failed: {e}")
        return None


def get_recent_trades(limit: int = 20) -> list:
    """Fetch recent closed trades from FreqTrade API."""
    data = ft_get(f"/trades?limit={limit}&offset=0")
    if data and "trades" in data:
        return data["trades"]
    return []


def get_open_trades() -> list:
    """Fetch currently open trades."""
    data = ft_get("/status")
    return data if isinstance(data, list) else []


def get_performance() -> dict:
    """Fetch bot performance summary."""
    return ft_get("/performance") or {}


def get_profit() -> dict:
    """Fetch overall profit summary."""
    return ft_get("/profit") or {}


# --------------------------------------------------------------------------- #
# External data loader
# --------------------------------------------------------------------------- #

def load_external_data() -> dict:
    """Load latest external data from Phase 2 aggregator."""
    try:
        if EXT_DATA.exists():
            with open(EXT_DATA) as f:
                return json.load(f)
    except Exception:
        pass
    return {"composite_score": 0.0, "composite_label": "UNKNOWN", "features": {}}


# --------------------------------------------------------------------------- #
# Signal log writer
# --------------------------------------------------------------------------- #

def write_signal_log(trades: list, ext_data: dict):
    """Append new closed trades to the signal log."""
    SIGNAL_LOG.parent.mkdir(parents=True, exist_ok=True)

    if not trades:
        return

    composite = ext_data.get("composite_score", 0.0)
    label     = ext_data.get("composite_label", "UNKNOWN")

    lines = []
    for t in trades[-5:]:  # Last 5 trades
        pair        = t.get("pair", "?")
        profit_pct  = t.get("profit_ratio", 0) * 100
        profit_abs  = t.get("profit_abs", 0)
        enter_tag   = t.get("enter_tag", "unknown")
        exit_reason = t.get("exit_reason", "unknown")
        open_date   = t.get("open_date", "")[:16]
        close_date  = t.get("close_date", "")[:16]
        outcome     = "✅ WIN" if profit_pct > 0 else "❌ LOSS"

        lines.append(
            f"| {close_date} | {pair:<12} | {outcome} | "
            f"{profit_pct:+.2f}% | {profit_abs:+.4f} USDT | "
            f"{enter_tag} | {exit_reason} | {label} ({composite:+.2f}) |"
        )

    if not lines:
        return

    entry = "\n".join(lines) + "\n"

    # Create file with header if new
    if not SIGNAL_LOG.exists():
        header = (
            "# FinBuddy — Signal Audit Log\n\n"
            "| Date | Pair | Result | Profit% | Profit USDT | "
            "Enter Tag | Exit Reason | Market State |\n"
            "|---|---|---|---|---|---|---|---|\n"
        )
        SIGNAL_LOG.write_text(header)

    with open(SIGNAL_LOG, "a") as f:
        f.write(entry)

    print(f"  Signal log: appended {len(lines)} trade(s)")


# --------------------------------------------------------------------------- #
# Regime writer
# --------------------------------------------------------------------------- #

def write_regime(ext_data: dict, profit: dict):
    """Update the current regime file with latest market state."""
    REGIME_FILE.parent.mkdir(parents=True, exist_ok=True)

    now           = datetime.utcnow()
    composite     = ext_data.get("composite_score", 0.0)
    label         = ext_data.get("composite_label", "UNKNOWN")
    sources_ok    = ext_data.get("sources_ok", 0)
    sources_total = ext_data.get("sources_total", 5)
    features      = ext_data.get("features", {})

    fear_greed    = features.get("ext_fear_greed", 0.5) * 100
    btc_dom       = features.get("ext_btc_dominance", 0.5) * 100
    news_sent     = features.get("ext_news_sentiment", 0.0)
    defi_tvl      = features.get("ext_defi_tvl_billions", 0)
    defi_24h      = features.get("ext_defi_tvl_signal_24h", 0)

    total_profit  = profit.get("profit_all_percent", 0.0)
    total_trades  = profit.get("trade_count", 0)
    win_rate      = profit.get("winning_trades", 0) / max(total_trades, 1) * 100

    content = f"""# FinBuddy — Current Regime

**Last Updated:** {now.strftime('%Y-%m-%d %H:%M')} UTC  
**Data Sources:** {sources_ok}/{sources_total} OK

---

## 🌡️ Market Regime

```
Regime      : {label}
Composite   : {composite:+.3f}  (-1.0 = STRONG_BEAR, +1.0 = STRONG_BULL)
```

## 📈 Signal Breakdown

| Signal | Value | Interpretation |
|---|---|---|
| Fear & Greed | {fear_greed:.0f}/100 | {'Extreme Fear' if fear_greed < 25 else 'Fear' if fear_greed < 45 else 'Neutral' if fear_greed < 55 else 'Greed' if fear_greed < 75 else 'Extreme Greed'} |
| BTC Dominance | {btc_dom:.1f}% | {'BTC Season' if btc_dom > 55 else 'Altcoin Season' if btc_dom < 45 else 'Balanced'} |
| News Sentiment | {news_sent:+.3f} | {'Bullish' if news_sent > 0.1 else 'Bearish' if news_sent < -0.1 else 'Neutral'} |
| DeFi TVL | ${defi_tvl:.1f}B | {'Capital Inflow' if defi_24h > 0.2 else 'Capital Outflow' if defi_24h < -0.2 else 'Stable'} |

## 🤖 Bot Performance (All Time)

| Metric | Value |
|---|---|
| Total Trades | {total_trades} |
| Win Rate | {win_rate:.1f}% |
| Total P&L | {total_profit:+.2f}% |

---

*Auto-generated by memory_writer.py — do not edit manually*
"""

    REGIME_FILE.write_text(content)
    print(f"  Regime: updated — {label} ({composite:+.3f})")


# --------------------------------------------------------------------------- #
# Daily research note writer
# --------------------------------------------------------------------------- #

def write_daily_note(trades: list, ext_data: dict, profit: dict):
    """Write/update today's daily research note."""
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    today     = datetime.utcnow().strftime("%Y-%m-%d")
    note_path = RESEARCH_DIR / f"{today}-daily.md"

    # Only write if it doesn't exist yet today
    if note_path.exists():
        return

    composite     = ext_data.get("composite_score", 0.0)
    label         = ext_data.get("composite_label", "UNKNOWN")
    total_trades  = profit.get("trade_count", 0)
    total_profit  = profit.get("profit_all_percent", 0.0)
    winning       = profit.get("winning_trades", 0)
    losing        = profit.get("losing_trades", 0)

    recent_lines = []
    for t in trades[-10:]:
        pair       = t.get("pair", "?")
        profit_pct = t.get("profit_ratio", 0) * 100
        outcome    = "✅" if profit_pct > 0 else "❌"
        recent_lines.append(f"- {outcome} {pair}: {profit_pct:+.2f}%")

    content = f"""# FinBuddy — Daily Note {today}

**Generated:** {datetime.utcnow().strftime('%H:%M')} UTC  
**Market Regime:** {label} ({composite:+.3f})

---

## 📊 Today’s Context

- Composite market score: {composite:+.3f} ({label})
- Total bot trades (all time): {total_trades} ({winning}W / {losing}L)
- All-time P&L: {total_profit:+.2f}%

## 🔄 Recent Trades

{chr(10).join(recent_lines) if recent_lines else '- No closed trades yet'}

## 📝 Notes

<!-- Add manual observations here -->

---

*Auto-generated by memory_writer.py*
"""
    note_path.write_text(content)
    print(f"  Daily note: created {note_path.name}")


# --------------------------------------------------------------------------- #
# Git commit
# --------------------------------------------------------------------------- #

def git_commit_vault():
    """Commit and push memory vault changes to gaurav branch."""
    try:
        os.chdir(REPO_ROOT)
        subprocess.run(["git", "add", "finbuddy_memory/"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if result.returncode == 0:
            print("  Git: no changes to commit")
            return

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"auto: memory vault update {now} UTC"],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "push", "origin", "gaurav"],
            check=True, capture_output=True
        )
        print("  Git: committed and pushed vault changes")
    except subprocess.CalledProcessError as e:
        print(f"  Git: commit failed — {e.stderr.decode() if e.stderr else e}")
    except Exception as e:
        print(f"  Git: unexpected error — {e}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] FinBuddy Memory Writer running...")

    trades    = get_recent_trades(limit=20)
    profit    = get_profit()
    ext_data  = load_external_data()

    print(f"  Trades     : {len(trades)} recent")
    print(f"  Ext data   : {ext_data.get('composite_label', 'N/A')} ({ext_data.get('composite_score', 0):+.3f})")

    write_signal_log(trades, ext_data)
    write_regime(ext_data, profit)
    write_daily_note(trades, ext_data, profit)
    git_commit_vault()

    print(f"  Done.\n")


if __name__ == "__main__":
    main()
