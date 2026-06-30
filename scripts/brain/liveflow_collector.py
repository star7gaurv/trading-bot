#!/usr/bin/env python3
"""liveflow_collector.py — Phase 4c: forward order-flow + liquidation collector.

WHY: the kline-derived taker-buy order flow (15m aggregated) is measured NOISE at our
3h horizon (scripts/brain/feature_ic.py, IC -0.01..-0.028, nothing graduates). The two
signals NOT in our data and worth collecting FORWARD are:
  1. LIQUIDATIONS — forced sells/buys (!forceOrder). Event-driven, not latency-bound,
     create multi-hour dislocations retail CAN trade. The genuinely untested signal.
  2. Live taker aggression (aggTrade) at per-minute granularity — cheap ride-along; lets
     us later test it at the per-minute level the 15m kline aggregation washed out.

DESIGN (infra-light, free-tier safe):
  - one async process, Binance USDT-M futures combined websocket
  - per-minute aggregation in memory; flush completed minutes to append-only JSONL
    (restart-safe, matches the project's ledger.jsonl convention)
  - daily roll JSONL -> per-pair parquet via liveflow_roll.py (separate cron)
  - auto-reconnect; heartbeat status.json for the watchdog/dashboard

⚠️ BLOCKED FROM THIS SERVER (2026-06-30): Binance futures WS (fstream.binance.com)
accepts the handshake but delivers ZERO data frames from this IP/region (spot WS works,
futures REST works — verified). So this collector cannot run here. Kept because it works
from a non-blocked region/proxy. The active liquidation path is fetch_liquidations.py
(Coinalyze REST). If futures WS access is ever restored, deploy this as a systemd service
(finbuddy-liveflow.service).

Output (when runnable):
  finbuddy_memory/historical/liveflow/YYYY-MM-DD.jsonl
  finbuddy_memory/historical/liveflow/status.json
"""
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "finbuddy_memory" / "historical" / "liveflow"
WS_BASE = "wss://fstream.binance.com/stream?streams="


def _symbols() -> list[str]:
    cfg = json.loads((ROOT / "freqtrade" / "user_data" / "config.json").read_text())
    return [p.split("/")[0] + "USDT" for p in cfg["exchange"]["pair_whitelist"]]


def _stream_url(symbols: list[str]) -> str:
    # per-symbol aggTrade + one all-market forceOrder stream
    streams = [f"{s.lower()}@aggTrade" for s in symbols] + ["!forceOrder@arr"]
    return WS_BASE + "/".join(streams)


def _minute_key(ms: int) -> str:
    return datetime.fromtimestamp((ms // 60000) * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")


class Aggregator:
    """Accumulate per-(minute, symbol) order-flow + liquidation stats; flush on minute rollover."""

    def __init__(self) -> None:
        self.cur_minute: str | None = None
        self.buf: dict[str, dict] = defaultdict(self._blank)
        self.msgs = 0
        self.last_msg_ts = 0.0

    @staticmethod
    def _blank() -> dict:
        return {"taker_buy": 0.0, "taker_sell": 0.0, "n": 0,
                "liq_long_usd": 0.0, "liq_short_usd": 0.0, "liq_long_n": 0, "liq_short_n": 0}

    def _roll_if_needed(self, minute: str) -> None:
        if self.cur_minute is None:
            self.cur_minute = minute
            return
        if minute != self.cur_minute:
            self._flush(self.cur_minute)
            self.cur_minute = minute
            self.buf = defaultdict(self._blank)

    def on_aggtrade(self, d: dict) -> None:
        sym = d["s"]
        minute = _minute_key(int(d["E"]))
        self._roll_if_needed(minute)
        qty = float(d["q"])
        # m=True -> buyer is maker -> aggressor SOLD (taker sell). m=False -> taker BUY.
        if d.get("m"):
            self.buf[sym]["taker_sell"] += qty
        else:
            self.buf[sym]["taker_buy"] += qty
        self.buf[sym]["n"] += 1

    def on_forceorder(self, o: dict) -> None:
        sym = o["s"]
        minute = _minute_key(int(o["T"]))
        self._roll_if_needed(minute)
        price = float(o.get("ap") or o.get("p") or 0.0)
        notional = price * float(o["q"])
        # S=SELL -> a LONG was force-closed (forced sell); S=BUY -> a SHORT was force-closed.
        if o["S"] == "SELL":
            self.buf[sym]["liq_long_usd"] += notional
            self.buf[sym]["liq_long_n"] += 1
        else:
            self.buf[sym]["liq_short_usd"] += notional
            self.buf[sym]["liq_short_n"] += 1

    def _flush(self, minute: str) -> None:
        path = OUT / f"{minute[:10]}.jsonl"
        with path.open("a") as f:
            for sym, v in self.buf.items():
                if v["n"] == 0 and v["liq_long_n"] == 0 and v["liq_short_n"] == 0:
                    continue
                row = {"minute": minute, "symbol": sym}
                row.update({k: round(x, 6) if isinstance(x, float) else x for k, x in v.items()})
                f.write(json.dumps(row) + "\n")
        self._write_status(minute)

    def _write_status(self, minute: str) -> None:
        (OUT / "status.json").write_text(json.dumps({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_flushed_minute": minute,
            "msgs_total": self.msgs,
            "last_msg_age_s": round(time.time() - self.last_msg_ts, 1) if self.last_msg_ts else None,
        }, indent=2))


async def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = _symbols()
    url = _stream_url(symbols)
    agg = Aggregator()
    print(f"[liveflow] {len(symbols)} symbols + forceOrder; connecting…", flush=True)
    while True:
        try:
            async with websockets.connect(url, ping_interval=180, ping_timeout=60,
                                           max_queue=4096) as ws:
                print(f"[liveflow] connected {datetime.now(timezone.utc).isoformat()}", flush=True)
                async for raw in ws:
                    agg.msgs += 1
                    agg.last_msg_ts = time.time()
                    msg = json.loads(raw)
                    data = msg.get("data", {})
                    et = data.get("e")
                    if et == "aggTrade":
                        agg.on_aggtrade(data)
                    elif et == "forceOrder":
                        agg.on_forceorder(data["o"])
        except Exception as e:  # reconnect on any drop
            print(f"[liveflow] disconnect: {type(e).__name__}: {e} — reconnecting in 5s", flush=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
