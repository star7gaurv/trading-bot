#!/usr/bin/env python3
"""
arbitrage/feed_daemon.py — long-running async price-feed poller across many exchanges.

Reads exchanges.json for a tiered exchange/symbol/interval config (majors polled fastest,
long-tail slowest — see that file's comments for the reasoning), polls each exchange's
best bid/ask via ccxt, and writes a snapshot to finbuddy_memory/arbitrage/price_cache.json
every few seconds. scanner.py reads that cache; it never calls exchanges directly.

Each exchange runs its own independent poll loop (one asyncio task) so one exchange being
slow, rate-limited, or down never blocks or corrupts any other exchange's data. ccxt's own
enableRateLimit=True self-throttles per exchange — this daemon does not need to coordinate
rate limits globally, only per-client.

Not a cron job — arbitrage needs sub-minute freshness, so this runs as a persistent
process (systemd unit: finbuddy-arb-feed.service). scanner.py, by contrast, IS a cron job
(runs every minute, reads the cache this daemon maintains).

Usage:
  /home/ubuntu/.finbuddy/venvs/arbitrage/bin/python3 scripts/arbitrage/feed_daemon.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path

import ccxt.async_support as ccxt

ROOT = Path("/home/ubuntu/var/www/html/trade")
EXCHANGES_CONFIG = Path(__file__).parent / "exchanges.json"
PRICE_CACHE = ROOT / "finbuddy_memory/arbitrage/price_cache.json"
FLUSH_INTERVAL_S = 5.0
STALE_AFTER_S = 300.0  # drop cache entries this old from the flushed snapshot — a symbol
                        # an exchange stopped returning data for shouldn't silently look "current"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("arb_feed")

_cache: dict[str, dict] = {}  # f"{exchange_id}:{symbol}" -> {exchange, symbol, bid, ask, ts}
_shutdown = asyncio.Event()


def _load_config() -> dict:
    return json.loads(EXCHANGES_CONFIG.read_text())


def _flush_cache() -> None:
    now = time.time()
    fresh = {k: v for k, v in _cache.items() if now - v["ts"] < STALE_AFTER_S}
    PRICE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PRICE_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"updated_at": now, "prices": fresh}, indent=2))
    tmp.replace(PRICE_CACHE)  # atomic — scanner.py never reads a half-written file


async def _sleep_or_shutdown(seconds: float) -> None:
    try:
        await asyncio.wait_for(_shutdown.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def _valid_bid_ask(ticker: dict | None) -> bool:
    if not ticker:
        return False
    bid, ask = ticker.get("bid"), ticker.get("ask")
    return bid is not None and ask is not None and bid > 0 and ask > 0


def _missing_symbols(group: list[str], tickers: dict) -> list[str]:
    return [s for s in group if not _valid_bid_ask(tickers.get(s))]


async def _poll_group(client, exchange_id: str, group: list[str], now: float) -> None:
    """Fetch one symbol group (all-spot or all-perp) and write results into _cache.

    Different exchanges' ccxt implementations are inconsistent about which call
    actually populates bid/ask (confirmed by hand: Binance USDⓈ-M futures tickers
    carry no bid/ask at all; Coinbase/Whitebit's batch fetchTickers omits it but
    their singular fetchTicker has it; Coinex/Lbank's ticker endpoints never carry
    it and only their order book does). Layered fallback, cheapest first, only for
    symbols still missing after each layer — not a blanket retry of the whole group:
      1. batch fetchTickers (1 call for the whole group)
      2. fetchBidsAsks for whatever's still missing (1 call for all of them)
      3. singular fetchTicker per still-missing symbol
      4. fetchOrderBook per still-missing symbol (top-of-book bid/ask) — the
         closest thing to a universally-supported primitive across ccxt exchanges
    """
    tickers: dict = {}
    try:
        tickers = await client.fetch_tickers(group)
    except Exception as e:
        log.debug(f"{exchange_id}: batch fetch_tickers failed - {e}")

    missing = _missing_symbols(group, tickers)
    if missing and client.has.get("fetchBidsAsks"):
        try:
            bids_asks = await client.fetch_bids_asks(missing)
            for sym, ba in bids_asks.items():
                tickers.setdefault(sym, {})
                tickers[sym]["bid"] = ba.get("bid")
                tickers[sym]["ask"] = ba.get("ask")
        except Exception as e:
            log.debug(f"{exchange_id}: fetch_bids_asks fallback failed - {e}")

    missing = _missing_symbols(group, tickers)
    for sym in missing:
        try:
            t = await client.fetch_ticker(sym)
            tickers.setdefault(sym, {})
            tickers[sym]["bid"] = t.get("bid")
            tickers[sym]["ask"] = t.get("ask")
        except Exception as e:
            log.debug(f"{exchange_id} {sym}: fetch_ticker fallback failed - {e}")

    missing = _missing_symbols(group, tickers)
    for sym in missing:
        try:
            ob = await client.fetch_order_book(sym, limit=5)
            tickers.setdefault(sym, {})
            tickers[sym]["bid"] = ob["bids"][0][0] if ob.get("bids") else None
            tickers[sym]["ask"] = ob["asks"][0][0] if ob.get("asks") else None
        except Exception as e:
            # A symbol this exchange genuinely doesn't list (e.g. no SOL/USDT
            # market) ends up here too — expected, not every exchange has every
            # symbol. Debug-level: this is routine, not something to page on.
            log.debug(f"{exchange_id} {sym}: fetch_order_book fallback failed - {e}")

    for sym, ticker in tickers.items():
        if not _valid_bid_ask(ticker):
            continue
        _cache[f"{exchange_id}:{sym}"] = {
            "exchange": exchange_id, "symbol": sym,
            "bid": ticker["bid"], "ask": ticker["ask"], "ts": now,
        }


async def _poll_exchange(exchange_id: str, symbols: list[str], perp_symbols: list[str],
                          interval_s: float) -> None:
    client_cls = getattr(ccxt, exchange_id, None)
    if client_cls is None:
        log.error(f"{exchange_id}: not a valid ccxt exchange id, skipping")
        return

    # Separate client PER market type, not just a separate call on one shared
    # client. Some exchanges' ccxt implementations (Binance confirmed) carry
    # internal state across calls that silently makes bid/ask come back None
    # on the second market type queried by an already-used client — a
    # dedicated client per type sidesteps that regardless of root cause.
    spot_client = client_cls({"enableRateLimit": True, "timeout": 15000}) if symbols else None
    perp_client = client_cls({"enableRateLimit": True, "timeout": 15000}) if perp_symbols else None

    try:
        while not _shutdown.is_set():
            now = time.time()
            if spot_client is not None:
                await _poll_group(spot_client, exchange_id, symbols, now)
            if perp_client is not None:
                await _poll_group(perp_client, exchange_id, perp_symbols, now)
            await _sleep_or_shutdown(interval_s)
    except Exception as e:
        # Something outside the per-group handling above (e.g. client construction
        # or a totally dead exchange) — log and let this exchange's task end; every
        # other exchange's task is independent and keeps running.
        log.warning(f"{exchange_id}: poll loop aborted - {e}")
    finally:
        # A hung close() on one exchange must not block every other exchange's
        # shutdown or the daemon's own exit — bound it.
        for c in (spot_client, perp_client):
            if c is None:
                continue
            try:
                await asyncio.wait_for(c.close(), timeout=5.0)
            except Exception as e:
                log.debug(f"{exchange_id}: close() failed/timed out - {e}")


async def _flush_loop() -> None:
    while not _shutdown.is_set():
        _flush_cache()
        await _sleep_or_shutdown(FLUSH_INTERVAL_S)
    _flush_cache()  # final flush so shutdown doesn't lose the last few seconds of data


def _handle_signal(*_args) -> None:
    log.info("Shutdown signal received, draining...")
    _shutdown.set()


async def main() -> int:
    cfg = _load_config()
    tasks = []
    total_exchanges = 0
    for tier_num, tier in sorted(cfg["tiers"].items()):
        interval = tier["poll_interval_s"]
        symbols = tier["symbols"]
        for ex in tier["exchanges"]:
            if not ex.get("enabled", True):
                continue
            tasks.append(asyncio.create_task(
                _poll_exchange(ex["id"], symbols, ex.get("perp_symbols", []), interval)
            ))
            total_exchanges += 1
    tasks.append(asyncio.create_task(_flush_loop()))
    log.info(f"Polling {total_exchanges} exchanges across {len(cfg['tiers'])} tiers "
             f"-> {PRICE_CACHE}")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("Shut down cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
