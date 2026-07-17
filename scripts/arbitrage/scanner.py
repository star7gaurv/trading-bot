#!/usr/bin/env python3
"""
arbitrage/scanner.py — reads the price cache feed_daemon.py maintains, detects gaps,
classifies them honestly, and drives the paper executor.

Cron: every 1 minute (not hourly like the other 3 paper modules — arbitrage gaps are
short-lived, sub-minute freshness matters here in a way it doesn't for funding/pairs/grid).
Never calls an exchange directly — that's the feed daemon's job; this script is a thin,
fast, restart-safe layer over its cache.

Three gap categories (see exchanges.json's comments and paper_executor.py's docstring
for the full reasoning):
  1. intra_exchange_basis     — spot vs perp, same exchange. -> capture (real P&L)
  2. cross_exchange_prefunded — cross-exchange, both venues in tier 1/2 (majors/mid).
                                  Modeled as if capital already sits on both sides.
                                  -> capture (real P&L)
  3. cross_exchange_transfer  — cross-exchange, involves a tier-3 (long-tail) venue.
                                  -> observe only, never counted as P&L (see caveat).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/arbitrage"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402
import paper_executor as px  # noqa: E402

PRICE_CACHE = ROOT / "finbuddy_memory/arbitrage/price_cache.json"
EXCHANGES_CONFIG = Path(__file__).parent / "exchanges.json"

MAX_CACHE_AGE_S = 60.0  # don't act on stale prices — the feed daemon flushes every 5s,
                         # so anything older than this means the daemon is unhealthy


def _load_config() -> dict:
    return json.loads(EXCHANGES_CONFIG.read_text())


def _exchange_tier_map(cfg: dict) -> dict[str, str]:
    """exchange_id -> tier number (as string, matching exchanges.json's keys)."""
    out = {}
    for tier_num, tier in cfg["tiers"].items():
        for ex in tier["exchanges"]:
            out[ex["id"]] = tier_num
    return out


def _classify_cross_exchange(tier_a: str, tier_b: str) -> str:
    """Both tier 1/2 (majors/mid-liquidity) -> plausible pre-funded capital.
    Either one tier 3 (long-tail) -> transfer-time gap, discovery only."""
    if tier_a == "3" or tier_b == "3":
        return "cross_exchange_transfer"
    return "cross_exchange_prefunded"


def load_prices() -> tuple[dict, float]:
    if not PRICE_CACHE.exists():
        return {}, 0.0
    try:
        d = json.loads(PRICE_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}, 0.0
    return d.get("prices", {}), d.get("updated_at", 0.0)


def find_opportunities(prices: dict, tier_map: dict, fee_pct: float,
                        min_gap_pct: float) -> tuple[list[dict], list[dict]]:
    """Returns (captures, observations) — pre-classified, not yet booked."""
    import time
    now = time.time()

    # Group live entries by their base symbol (spot AND perp of the same asset share
    # the base — "BTC/USDT" and "BTC/USDT:USDT" both start "BTC/USDT").
    by_base: dict[str, list[dict]] = {}
    for entry in prices.values():
        if now - entry["ts"] > MAX_CACHE_AGE_S:
            continue  # stale — feed daemon may be lagging on this exchange, skip it
        base = entry["symbol"].split(":")[0]
        by_base.setdefault(base, []).append(entry)

    captures: list[dict] = []
    observations: list[dict] = []
    fees_2leg = 2 * fee_pct

    for base, entries in by_base.items():
        # ── Category 1: intra-exchange basis (spot vs perp, same exchange) ──
        by_exchange: dict[str, list[dict]] = {}
        for e in entries:
            by_exchange.setdefault(e["exchange"], []).append(e)
        for exchange_id, ex_entries in by_exchange.items():
            spot = next((e for e in ex_entries if ":" not in e["symbol"]), None)
            perp = next((e for e in ex_entries if ":" in e["symbol"]), None)
            if not spot or not perp:
                continue
            # basis = perp bid vs spot ask (short perp / long spot) or the reverse
            gap_a = (perp["bid"] - spot["ask"]) / spot["ask"]
            gap_b = (spot["bid"] - perp["ask"]) / perp["ask"]
            gap_pct, buy_leg, sell_leg = (
                (gap_a, spot, perp) if gap_a > gap_b else (gap_b, perp, spot)
            )
            if gap_pct < min_gap_pct:
                continue
            opp = {
                "opportunity_type": "intra_exchange_basis",
                "symbol": base, "buy_exchange": exchange_id, "sell_exchange": exchange_id,
                "buy_price": buy_leg["ask"], "sell_price": sell_leg["bid"],
                "gap_pct": gap_pct, "fees_pct": fees_2leg,
            }
            (captures if gap_pct > fees_2leg else observations).append(opp)

        # ── Categories 2/3: cross-exchange (best bid vs best ask across venues) ──
        spot_entries = [e for e in entries if ":" not in e["symbol"]]
        if len(spot_entries) < 2:
            continue
        best_ask_entry = min(spot_entries, key=lambda e: e["ask"])
        best_bid_entry = max(spot_entries, key=lambda e: e["bid"])
        if best_ask_entry["exchange"] == best_bid_entry["exchange"]:
            continue  # no cross-exchange gap to speak of
        gap_pct = (best_bid_entry["bid"] - best_ask_entry["ask"]) / best_ask_entry["ask"]
        if gap_pct < min_gap_pct:
            continue
        opp_type = _classify_cross_exchange(
            tier_map.get(best_ask_entry["exchange"], "3"),
            tier_map.get(best_bid_entry["exchange"], "3"),
        )
        opp = {
            "opportunity_type": opp_type,
            "symbol": base,
            "buy_exchange": best_ask_entry["exchange"], "sell_exchange": best_bid_entry["exchange"],
            "buy_price": best_ask_entry["ask"], "sell_price": best_bid_entry["bid"],
            "gap_pct": gap_pct, "fees_pct": fees_2leg,
        }
        if opp_type == "cross_exchange_transfer":
            opp["caveat"] = "transfer time not modeled as capturable"
            observations.append(opp)
        elif gap_pct > fees_2leg:
            captures.append(opp)
        else:
            observations.append(opp)

    return captures, observations


def main() -> int:
    cfg = _load_config()
    tier_map = _exchange_tier_map(cfg)
    fee_pct = cfg.get("fees", {}).get("default_taker_pct", 0.001)
    min_gap_pct = cfg.get("min_gap_pct_to_log", 0.0005)

    prices, updated_at = load_prices()
    import time
    if not prices:
        print("[arbitrage] no price data yet (feed daemon still starting up?)")
        return 0
    if time.time() - updated_at > MAX_CACHE_AGE_S:
        print(f"[arbitrage] price cache is stale ({time.time() - updated_at:.0f}s old) — "
              f"feed daemon may be down, skipping this cycle")
        return 0

    captures, observations = find_opportunities(prices, tier_map, fee_pct, min_gap_pct)

    state = px.load_state()
    booked = 0
    # Cap how many of this cycle's captures actually get "taken" — mirrors a real
    # constraint (limited capital/attention), and keeps one noisy cycle from booking
    # an unrealistic number of trades.
    for opp in sorted(captures, key=lambda o: -o["gap_pct"])[:px.MAX_CAPTURES_PER_RUN]:
        net_pnl = px.capture(state, opp)
        booked += 1
        send(Subsystem.BRAIN_CYCLE, Status.OK,
             f"Arbitrage (paper): captured {opp['symbol']}",
             fields={
                 "Type": opp["opportunity_type"],
                 "Route": f"{opp['buy_exchange']} -> {opp['sell_exchange']}",
                 "Gross gap": f"{opp['gap_pct']*100:.3f}%",
                 "Net P&L": f"{net_pnl:+.2f} USDT (virtual)",
             },
             context="Paper only — no real capital, no real orders.",
             silent=True)

    for opp in observations:
        px.observe(state, opp)

    state["last_run"] = px._now()
    px.save_state(state)

    s = px.summary()
    print(f"[arbitrage] captures_this_run={booked} observations_this_run={len(observations)} "
          f"wallet={s['wallet_usdt']} realized_pnl={s['realized_pnl']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
