#!/usr/bin/env python3
"""
pairs_trading/scanner.py — hourly market-neutral stat-arb scanner (paper).

Cointegration-lite over the whitelist's 1h closes (same maths as the dashboard
/api/pairs/scan): correlation on log-returns, OLS hedge ratio, current spread
z-score, AR(1) mean-reversion half-life. Drives the paper executor:

  open : |z| >= 2.0 AND corr >= 0.85 AND 2h <= half-life <= 20d AND capacity
  close: |z| <= 0.5 (reverted → win)  | |z| >= 4.0 (diverged → stop)
         | held > 14 days (time stop)

PAPER MODE ONLY. Cron: hourly. Telegram: only on open/close (silent).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/pairs_trading"))
import paper_executor as px  # noqa: E402
try:
    from lib.telegram_template import Subsystem, Status, send  # noqa: E402
    _TG = True
except Exception:
    _TG = False

CONFIG = ROOT / "freqtrade/user_data/config.json"
DATA_DIR = ROOT / "freqtrade/user_data/data/binance/futures"

LOOKBACK = 720          # ~30d of 1h candles
ENTRY_Z = 2.0
EXIT_Z = 0.5
STOP_Z = 4.0
MIN_CORR = 0.85
MIN_HALFLIFE_H = 2
MAX_HALFLIFE_H = 72      # 3 days — reject slow-reverting pairs that won't mean-revert in a
                        # tradeable window (e.g. the 213h SOL/XRP pick that sat open for days).
                        # Half-life must be << MAX_HOLD_DAYS or the position can't resolve.
MAX_HOLD_DAYS = 14


def load_closes() -> pd.DataFrame:
    cfg = json.load(open(CONFIG))
    wl = cfg["exchange"]["pair_whitelist"]
    closes = {}
    for p in wl:
        base = p.split("/")[0]
        f = DATA_DIR / f"{base}_USDT_USDT-1h-futures.feather"
        if not f.exists():
            continue
        try:
            s = pd.read_feather(f).set_index("date")["close"].tail(LOOKBACK)
        except Exception:
            continue
        if len(s) >= LOOKBACK * 0.8:
            closes[base] = s
    return pd.DataFrame(closes).dropna()


def pair_stats(a: str, b: str, logp: pd.DataFrame):
    """Return (corr, beta, z, half_life_h) for one pair, or None if undefined."""
    if a not in logp.columns or b not in logp.columns:
        return None
    corr = float(logp[a].diff().corr(logp[b].diff()))
    beta = float(np.polyfit(logp[b].values, logp[a].values, 1)[0])
    if beta <= 0:
        return None
    spread = logp[a] - beta * logp[b]
    sd = float(spread.std())
    if sd == 0:
        return None
    z = float((spread.iloc[-1] - float(spread.mean())) / sd)
    sv = spread.values
    lam = float(np.polyfit(sv[:-1], np.diff(sv), 1)[0])
    hl = (-np.log(2) / lam) if lam < 0 else None
    hl = round(hl, 1) if (hl and 0 < hl < 5000) else None
    return corr, beta, z, hl


def main() -> int:
    px_df = load_closes()
    if px_df.shape[1] < 2:
        print("[pairs] not enough price data")
        return 0
    logp = np.log(px_df)
    latest = {s: float(px_df[s].iloc[-1]) for s in px_df.columns}
    state = px.load_state()
    now = datetime.now(timezone.utc)

    # 1) manage open positions
    for key in list(state["positions"].keys()):
        pos = state["positions"][key]
        a, b = pos["a"], pos["b"]
        if a not in latest or b not in latest:
            continue
        st = pair_stats(a, b, logp)
        cur_z = st[2] if st else None
        held_days = (now - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 86400
        reason = None
        if cur_z is not None and abs(cur_z) <= EXIT_Z:
            reason = f"reverted (z {cur_z:+.2f})"
        elif cur_z is not None and abs(cur_z) >= STOP_Z:
            reason = f"diverged (z {cur_z:+.2f})"
        elif held_days > MAX_HOLD_DAYS:
            reason = f"time stop ({held_days:.0f}d)"
        if reason:
            px.close_position(state, key, latest[a], latest[b], reason, cur_z)
            if _TG:
                send(Subsystem.BRAIN_CYCLE, Status.INFO,
                     f"Pairs (paper): closed {key}",
                     fields={"Reason": reason}, silent=True)

    # 2) scan for new opportunities
    syms = list(px_df.columns)
    cands = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            st = pair_stats(a, b, logp)
            if not st:
                continue
            corr, beta, z, hl = st
            cands.append({"a": a, "b": b, "corr": corr, "beta": beta, "z": z, "hl": hl})
    cands.sort(key=lambda c: abs(c["z"]), reverse=True)

    for c in cands:
        if len(state["positions"]) >= px.MAX_POSITIONS:
            break
        if abs(c["z"]) < ENTRY_Z or c["corr"] < MIN_CORR:
            continue
        if c["hl"] is None or not (MIN_HALFLIFE_H <= c["hl"] <= MAX_HALFLIFE_H):
            continue
        a, b = c["a"], c["b"]
        if px._key(a, b) in state["positions"] or px._key(b, a) in state["positions"]:
            continue
        # already exposed to either leg? skip to keep positions independent
        legs_open = {s for p in state["positions"].values() for s in (p["a"], p["b"])}
        if a in legs_open or b in legs_open:
            continue
        side = 1 if c["z"] <= -ENTRY_Z else -1  # z<0 → A cheap → long A/short B
        if px.open_position(state, a, b, side, c["beta"], c["z"],
                            latest[a], latest[b], c["corr"], c["hl"]):
            if _TG:
                trade = f"long {a} / short {b}" if side == 1 else f"short {a} / long {b}"
                send(Subsystem.BRAIN_CYCLE, Status.OK,
                     f"Pairs (paper): opened {a}/{b}",
                     fields={"Trade": trade, "Stretch": f"{c['z']:+.2f}σ",
                             "Correlation": f"{c['corr']:.2f}",
                             "Revert ~": f"{c['hl']:.0f}h"},
                     context="Market-neutral stat-arb. Paper only.", silent=True)

    state["last_update"] = px._now()
    px.save_state(state)
    s = px.summary()
    print(f"[pairs] open={s['open_positions']} 7d_net={s['net_7d']} "
          f"realized_total={s['realized_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
