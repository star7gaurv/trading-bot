#!/usr/bin/env python3
"""
funding_farm/scanner.py — hourly funding-rate opportunity scanner (Phase D).

Pulls current funding for all whitelisted perps in ONE public API call
(GET /fapi/v1/premiumIndex — no key needed), checks 7-day stability against
the per-pair funding history parquet, and drives the paper executor:

  open : annualized funding >= MIN_APR (15%) AND 7d-mean same sign and >= 10% APR
  close: 7d-mean annualized < EXIT_APR (5%) — the carry has decayed

PAPER MODE ONLY. Cron: hourly. Telegram: only on open/close events (silent).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/funding_farm"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402
import paper_executor as px  # noqa: E402

CONFIG = ROOT / "freqtrade/user_data/config.json"
FUNDING_PARQUET = ROOT / "finbuddy_memory/historical/funding_perpair.parquet"

MIN_APR = 0.15        # open above 15% annualized
STABILITY_APR = 0.10  # 7d mean must also clear 10%
EXIT_APR = 0.05       # close below 5%
EVENTS_PER_YEAR = 3 * 365


def _whitelist_symbols() -> list[str]:
    cfg = json.load(open(CONFIG))
    return [p.replace("/", "").replace(":USDT", "")
            for p in cfg["exchange"]["pair_whitelist"]]


def fetch_current_funding() -> dict[str, float]:
    """symbol -> last funding rate (per 8h event), one bulk call."""
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    req = urllib.request.Request(url, headers={"User-Agent": "Cortexa/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return {d["symbol"]: float(d["lastFundingRate"]) for d in data}


def fetch_contract_status() -> dict[str, str]:
    """symbol -> contract status from exchangeInfo (TRADING / SETTLING / ...).

    2026-07-08: TONUSDT went SETTLING (delisting) the day after the farm opened
    it — funding stopped (rate pinned 0.0), the 7d-mean went None (no history
    rows), and the None-guarded decay rule could never close it. A non-TRADING
    contract pays no funding: close it, and never open one.
    On API failure returns {} — callers must treat missing status as TRADING
    (fail open) so a transient outage can't mass-close healthy positions.
    """
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Cortexa/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        return {s["symbol"]: s.get("status", "TRADING") for s in data.get("symbols", [])}
    except Exception:
        return {}


def seven_day_mean_rate(symbol: str) -> float | None:
    try:
        df = pd.read_parquet(FUNDING_PARQUET)
    except Exception:
        return None
    df = df[df["symbol"] == symbol] if "symbol" in df.columns else df
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"], utc=True)
    recent = df[df["date"] >= datetime.now(timezone.utc) - timedelta(days=7)]
    if len(recent) < 10:
        return None
    return float(recent["funding_rate"].mean())


def main() -> int:
    symbols = set(_whitelist_symbols())
    rates = {s: r for s, r in fetch_current_funding().items() if s in symbols}
    statuses = fetch_contract_status()
    state = px.load_state()

    # 1) accrue funding on open paper positions
    px.accrue(state, rates)

    # 2a) close positions on delisted/settling contracts (funding halted — the
    #     decay rule below can't fire for them: no history rows → mean7 is None)
    for symbol in list(state["positions"].keys()):
        status = statuses.get(symbol, "TRADING")
        if status != "TRADING":
            px.close_position(state, symbol, reason=f"contract {status} — funding halted")
            send(Subsystem.BRAIN_CYCLE, Status.WARN,
                 f"Funding farm (paper): closed {symbol}",
                 fields={"Reason": f"contract status {status} (delisting) — no funding accrues"},
                 silent=True)

    # 2b) close decayed positions
    for symbol in list(state["positions"].keys()):
        mean7 = seven_day_mean_rate(symbol)
        apr7 = (mean7 or 0.0) * px.FUNDING_EVENTS_PER_DAY * 365
        if mean7 is not None and apr7 < EXIT_APR:
            px.close_position(state, symbol, reason=f"7d APR decayed to {apr7:.1%}")
            send(Subsystem.BRAIN_CYCLE, Status.INFO,
                 f"Funding farm (paper): closed {symbol}",
                 fields={"Reason": f"7d APR {apr7:.1%} < {EXIT_APR:.0%}"},
                 silent=True)

    # 3) open new opportunities (positive funding only — cash-and-carry)
    candidates = sorted(
        ((s, r) for s, r in rates.items() if r > 0), key=lambda x: -x[1]
    )
    for symbol, rate in candidates:
        apr = rate * EVENTS_PER_YEAR
        if apr < MIN_APR:
            break  # sorted desc — nothing further qualifies
        if statuses.get(symbol, "TRADING") != "TRADING":
            continue  # delisting/settling contract — funding will stop
        mean7 = seven_day_mean_rate(symbol)
        if mean7 is None or mean7 <= 0:
            continue
        if mean7 * EVENTS_PER_YEAR < STABILITY_APR:
            continue
        if px.open_position(state, symbol, rate, apr):
            send(Subsystem.BRAIN_CYCLE, Status.OK,
                 f"Funding farm (paper): opened {symbol}",
                 fields={
                     "Current APR": f"{apr:.1%}",
                     "7d-mean APR": f"{mean7 * EVENTS_PER_YEAR:.1%}",
                     "Notional": f"{px.POSITION_NOTIONAL:.0f} USDT (virtual)",
                 },
                 context="Delta-neutral: short perp + long spot. Paper only.",
                 silent=True)

    px.save_state(state)
    s = px.summary()
    print(f"[funding_farm] open={s['open_positions']} 7d_net={s['net_7d']} "
          f"realized_total={s['realized_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
