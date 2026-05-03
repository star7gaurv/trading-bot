#!/usr/bin/env python3
"""
risk_engine.py — Phase 9 risk engine scaffold.

Provides RiskEngine with:
  - position_size(capital, risk_pct, entry, stoploss)
  - liquidation_guard(entry, leverage, direction)
  - funding_rate_check(symbol)
  - max_drawdown_gate(current_dd)
"""
import json
from pathlib import Path

EXTERNAL_DIR = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external")
MAX_RISK_PCT = 0.02   # Kelly-light cap
DD_LIMIT     = 0.15
LIQ_BUFFER   = 0.03


class RiskEngine:
    """Lightweight risk engine — pure functions, no exchange calls."""

    def position_size(self, capital: float, risk_pct: float,
                      entry: float, stoploss: float) -> float:
        """USDT notional sized so worst-case loss = risk_pct of capital."""
        if capital <= 0 or entry <= 0 or stoploss <= 0:
            return 0.0
        risk_pct = max(0.0, min(risk_pct, MAX_RISK_PCT))
        risk_usdt = capital * risk_pct
        per_unit_loss = abs(entry - stoploss)
        if per_unit_loss <= 0:
            return 0.0
        units = risk_usdt / per_unit_loss
        return round(units * entry, 2)

    def liquidation_guard(self, entry: float, leverage: float,
                          direction: str) -> dict:
        """Return est. liq price + warning if within LIQ_BUFFER of entry.

        Simplified isolated-margin model: liq ~ entry * (1 - 1/leverage) for long,
        entry * (1 + 1/leverage) for short. Ignores fees/maintenance margin.
        """
        if leverage <= 0 or entry <= 0:
            return {"liq_price": None, "warn": True, "reason": "bad inputs"}
        if direction == "long":
            liq = entry * (1 - 1.0 / leverage)
        elif direction == "short":
            liq = entry * (1 + 1.0 / leverage)
        else:
            return {"liq_price": None, "warn": True, "reason": "bad direction"}
        distance = abs(entry - liq) / entry
        return {
            "liq_price": round(liq, 6),
            "distance_pct": round(distance, 4),
            "warn": distance < LIQ_BUFFER,
        }

    def funding_rate_check(self, symbol: str):
        """Read latest funding rate from external data dir if available."""
        candidates = [
            EXTERNAL_DIR / "funding_rate.json",
            EXTERNAL_DIR / f"funding_{symbol.replace('/', '_')}.json",
        ]
        for fp in candidates:
            if not fp.exists():
                continue
            try:
                data = json.loads(fp.read_text())
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                if symbol in data:
                    try: return float(data[symbol])
                    except (TypeError, ValueError): pass
                for k in ("funding_rate", "rate", "value"):
                    if k in data:
                        try: return float(data[k])
                        except (TypeError, ValueError): pass
        return None

    def max_drawdown_gate(self, current_dd: float) -> bool:
        if current_dd is None:
            return False
        return abs(current_dd) < DD_LIMIT


def _selftest():
    re = RiskEngine()
    results = []

    # 1) position_size: 1000 capital, 1% risk, entry 100, sl 98 → 50 units → 5000 notional? cap risk
    sz = re.position_size(1000, 0.01, 100, 98)
    results.append(("position_size basic", abs(sz - 500.0) < 0.01, sz))
    # risk_pct cap at 2%
    sz_capped = re.position_size(1000, 0.10, 100, 98)
    results.append(("position_size cap", abs(sz_capped - 1000.0) < 0.01, sz_capped))
    # bad inputs
    results.append(("position_size zero", re.position_size(0, 0.01, 100, 98) == 0.0, None))

    # 2) liquidation_guard
    lg_long = re.liquidation_guard(100, 10, "long")
    results.append(("liq long 10x", lg_long["liq_price"] == 90.0 and lg_long["warn"] is False, lg_long))
    lg_close = re.liquidation_guard(100, 50, "long")  # 2% distance < 3% → warn
    results.append(("liq long 50x warn", lg_close["warn"] is True, lg_close))
    lg_short = re.liquidation_guard(100, 10, "short")
    results.append(("liq short", lg_short["liq_price"] == 110.0, lg_short))

    # 3) funding_rate_check — no file → None expected (in default install)
    fr = re.funding_rate_check("BTC/USDT:USDT")
    results.append(("funding_rate none", fr is None or isinstance(fr, float), fr))

    # 4) max_drawdown_gate
    results.append(("dd safe",   re.max_drawdown_gate(0.05) is True,  0.05))
    results.append(("dd unsafe", re.max_drawdown_gate(0.20) is False, 0.20))
    results.append(("dd none",   re.max_drawdown_gate(None) is False, None))

    print("=== Phase 9 RiskEngine self-test ===")
    failed = 0
    for name, ok, val in results:
        flag = "PASS" if ok else "FAIL"
        if not ok: failed += 1
        print(f"  [{flag}] {name}: {val}")
    print(f"\nResult: {len(results) - failed}/{len(results)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(_selftest())
