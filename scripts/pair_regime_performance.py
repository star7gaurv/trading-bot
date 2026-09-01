#!/usr/bin/env python3
"""
pair_regime_performance.py — Per-pair-per-regime performance tracker.

The missing intelligence layer: instead of statically blacklisting pairs,
the bot reads this script's output to dynamically block pair-regime combos
that have lost money over the rolling lookback window.

A pair that loses in NEUTRAL but wins in BEAR gets blocked in NEUTRAL only.
A blocked pair that recovers gets unblocked automatically.

Inputs
------
- finbuddy_memory/trades/closed.md  (auto-written by trade_postmortem.py)

Outputs
-------
- finbuddy_memory/regimes/pair_regime_stats.json
- STDOUT: human-readable table sorted by worst pair-regime combo

Block rule (data-driven, confirmed by user 2026-05-19):
  n_trades >= 5  AND  WR < 40%  AND  PF < 0.7
  over a 30-day rolling lookback

Wire-in: CortexaAI_v23.py populate_entry_trend() loads the JSON and
zeros out enter_long / enter_short for any (pair, current_regime) that
appears in the `blocked[]` list.

Cron: */30 * * * * — runs every 30 min (matches postmortem cadence).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
CLOSED_MD = ROOT / "finbuddy_memory" / "trades" / "closed.md"
OUT_JSON  = ROOT / "finbuddy_memory" / "regimes" / "pair_regime_stats.json"

# Block thresholds (confirmed by user)
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MIN_TRADES    = 5
DEFAULT_MAX_WR        = 0.40   # block if WR strictly below this
DEFAULT_MAX_PF        = 0.70   # block if PF strictly below this


# ── Parsing ────────────────────────────────────────────────────────────────

# Match a markdown table row like:
# | 2026-05-19 02:21:09 | OP/USDT:USDT | SHORT | 0h16m | -1.02% | -1.04 | stop_loss | NEUTRAL | freqai_lgbm_v22_short |
ROW_RE = re.compile(
    r"^\|\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*"
    r"\|\s*([^\|]+?)\s*"     # pair
    r"\|\s*(LONG|SHORT)\s*"
    r"\|\s*[^\|]+?\s*"        # hold
    r"\|\s*([\-\+]?[\d\.]+)%\s*"   # P&L %
    r"\|\s*([\-\+]?[\d\.]+)\s*"    # P&L $
    r"\|\s*([^\|]+?)\s*"     # exit reason
    r"\|\s*([A-Z]+)\s*"      # regime
    r"\|\s*([^\|]+?)\s*\|$"  # tag
)


def parse_closed_md(path: Path = CLOSED_MD) -> list[dict]:
    """Parse closed.md markdown table → list of trade dicts."""
    if not path.exists():
        return []
    trades = []
    with path.open() as f:
        for line in f:
            line = line.rstrip()
            m = ROW_RE.match(line)
            if not m:
                continue
            date_s, pair, side, pct_s, abs_s, exit_r, regime, tag = m.groups()
            try:
                # closed.md timestamps are naive UTC
                ts = datetime.fromisoformat(date_s).replace(tzinfo=timezone.utc)
                trades.append({
                    "closed_at": ts,
                    "pair":      pair,
                    "side":      side,
                    "profit_pct": float(pct_s),
                    "profit_usdt": float(abs_s),
                    "exit_reason": exit_r,
                    "regime":      regime,
                    "tag":         tag,
                })
            except ValueError:
                continue
    return trades


# ── Aggregation ────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict], lookback_days: int) -> dict:
    """
    Group trades by (pair, regime), compute aggregates over the lookback window.
    Returns nested dict: stats[pair][regime] = {n, wins, losses, wr, pf, profit_usdt, ...}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    recent = [t for t in trades if t["closed_at"] >= cutoff]

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in recent:
        buckets[(t["pair"], t["regime"])].append(t)

    stats: dict[str, dict[str, dict]] = defaultdict(dict)
    for (pair, regime), group in buckets.items():
        n = len(group)
        wins   = [t for t in group if t["profit_usdt"] > 0]
        losses = [t for t in group if t["profit_usdt"] <= 0]
        gw = sum(t["profit_usdt"] for t in wins)
        gl = abs(sum(t["profit_usdt"] for t in losses))
        wr = len(wins) / n if n else 0.0
        pf = (gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
        stats[pair][regime] = {
            "n":           n,
            "wins":        len(wins),
            "losses":      len(losses),
            "wr":          round(wr, 4),
            "pf":          round(pf, 3) if pf != float("inf") else None,
            "profit_usdt": round(sum(t["profit_usdt"] for t in group), 2),
            "avg_profit_pct": round(sum(t["profit_pct"] for t in group) / n, 3),
        }
    return dict(stats)


def find_blocked(stats: dict, min_trades: int, max_wr: float, max_pf: float,
                  mode: str = "and") -> list[dict]:
    """Apply the block rule to find pair-regime combos that should be blocked.

    mode="and" (default, current live behaviour): block only if WR<max_wr AND PF<max_pf.
    mode="or": block if EITHER WR<max_wr OR PF<max_pf — catches combos that fail on
    just one axis (e.g. WR=42%/PF=0.5, which the AND rule lets through). Untested
    live; see finbuddy_memory/reports/pair_regime_gate_comparison.md before flipping
    the cron's --mode default.
    """
    assert mode in ("and", "or"), f"unknown mode: {mode}"
    blocked = []
    for pair, by_regime in stats.items():
        for regime, s in by_regime.items():
            if s["n"] < min_trades:
                continue
            # PF=None means infinite (all wins) — never block infinite-PF combos
            if s["pf"] is None:
                continue
            wr_fail = s["wr"] < max_wr
            pf_fail = s["pf"] < max_pf
            should_block = (wr_fail and pf_fail) if mode == "and" else (wr_fail or pf_fail)
            if should_block:
                blocked.append({
                    "pair":   pair,
                    "regime": regime,
                    "reason": f"WR={s['wr']*100:.0f}% PF={s['pf']:.2f} n={s['n']} profit={s['profit_usdt']:+.2f}",
                    "n":      s["n"],
                    "wr":     s["wr"],
                    "pf":     s["pf"],
                })
    blocked.sort(key=lambda b: (b["wr"], b["pf"]))
    return blocked


# ── Output ─────────────────────────────────────────────────────────────────

def write_json(stats: dict, blocked: list[dict], lookback_days: int,
               min_trades: int, max_wr: float, max_pf: float,
               mode: str = "and", out_path: Path = OUT_JSON) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joiner = "AND" if mode == "and" else "OR"
    payload = {
        "updated":       datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "block_rule": {
            "min_trades": min_trades,
            "max_wr":     max_wr,
            "max_pf":     max_pf,
            "mode":       mode,
            "description": f"Block pair-regime if n>={min_trades} AND (WR<{max_wr*100:.0f}% {joiner} PF<{max_pf})",
        },
        "stats":   stats,
        "blocked": blocked,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))


def print_table(stats: dict, blocked: list[dict]) -> None:
    rows = []
    for pair, by_regime in stats.items():
        for regime, s in by_regime.items():
            pf_str = f"{s['pf']:.2f}" if s['pf'] is not None else "  ∞"
            blocked_flag = "🛑" if any(b["pair"] == pair and b["regime"] == regime for b in blocked) else "  "
            rows.append((pair, regime, s["n"], s["wins"], s["losses"],
                         s["wr"]*100, pf_str, s["profit_usdt"], blocked_flag))

    # Sort by profit ascending (worst first)
    rows.sort(key=lambda r: r[7])

    header = f"{'Pair':18} {'Regime':8} {'n':>4} {'W':>3} {'L':>3} {'WR':>6} {'PF':>6} {'Profit':>9} Blocked?"
    sep = "-" * len(header)
    print(f"\n{'Per-Pair-Per-Regime Performance (rolling)':^{len(header)}}")
    print(header)
    print(sep)
    for pair, regime, n, w, l, wr, pf_str, profit, flag in rows:
        print(f"{pair:18} {regime:8} {n:>4} {w:>3} {l:>3} {wr:>5.1f}% {pf_str:>6} {profit:>+9.2f} {flag}")
    print(sep)
    print(f"\nBlocked pair-regime combos: {len(blocked)}")
    for b in blocked:
        print(f"  🛑 {b['pair']:18} in {b['regime']:8} — {b['reason']}")
    print()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--lookback-days", type=int,   default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--min-trades",    type=int,   default=DEFAULT_MIN_TRADES)
    p.add_argument("--max-wr",        type=float, default=DEFAULT_MAX_WR)
    p.add_argument("--max-pf",        type=float, default=DEFAULT_MAX_PF)
    p.add_argument("--mode",          choices=["and", "or"], default="and",
                   help="'and' = current live rule (block only if WR AND PF both fail). "
                        "'or' = tightened rule, untested live (block if EITHER fails).")
    p.add_argument("--out",           type=Path, default=OUT_JSON,
                   help="output path — override for dry-run comparisons without touching the live file")
    p.add_argument("--quiet",         action="store_true", help="suppress table, just write JSON")
    args = p.parse_args()

    trades = parse_closed_md()
    if not trades:
        print(f"No trades found in {CLOSED_MD}", file=sys.stderr)
        return 1

    stats   = compute_stats(trades, args.lookback_days)
    blocked = find_blocked(stats, args.min_trades, args.max_wr, args.max_pf, mode=args.mode)

    write_json(stats, blocked, args.lookback_days, args.min_trades, args.max_wr, args.max_pf,
               mode=args.mode, out_path=args.out)

    if not args.quiet:
        joiner = "AND" if args.mode == "and" else "OR"
        print(f"Parsed {len(trades)} closed trades. "
              f"Lookback: {args.lookback_days}d. "
              f"Block rule: n>={args.min_trades} AND (WR<{args.max_wr*100:.0f}% {joiner} PF<{args.max_pf})")
        print_table(stats, blocked)

    print(f"→ wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
