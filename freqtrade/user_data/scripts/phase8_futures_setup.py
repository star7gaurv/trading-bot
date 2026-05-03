#!/usr/bin/env python3
"""
phase8_futures_setup.py — Verify Freqtrade config is correct for futures.

Reads user_data/config.json and reports:
  - current trading_mode / margin_mode / stake / exchange
  - JSON diff to fix mode/margin if wrong
  - capital warning if max_open_trades * stake_amount > 500 USDT
  - manual checklist for Binance side
"""
import json
from pathlib import Path

CONFIG = Path("/home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json")
CAPITAL_ESTIMATE = 500.0  # conservative USDT


def main():
    cfg = json.loads(CONFIG.read_text())

    trading_mode = cfg.get("trading_mode")
    margin_mode  = cfg.get("margin_mode")
    stake_ccy    = cfg.get("stake_currency")
    stake_amount = cfg.get("stake_amount", 0)
    max_open     = cfg.get("max_open_trades", 0)
    exchange     = cfg.get("exchange", {}).get("name", "?")

    print("=== Phase 8 — Futures Setup Check ===")
    print(f"trading_mode   : {trading_mode}")
    print(f"margin_mode    : {margin_mode}")
    print(f"stake_currency : {stake_ccy}")
    print(f"stake_amount   : {stake_amount}")
    print(f"max_open_trades: {max_open}")
    print(f"exchange       : {exchange}")
    print()

    diff = {}
    if trading_mode != "futures":
        diff["trading_mode"] = "futures"
    if margin_mode != "isolated":
        diff["margin_mode"] = "isolated"
    if diff:
        print("[!] Config mismatch — apply this JSON diff to user_data/config.json:")
        print(json.dumps(diff, indent=2))
    else:
        print("[OK] trading_mode=futures + margin_mode=isolated")
    print()

    exposure = (stake_amount or 0) * (max_open or 0)
    print(f"Total capital exposure (stake_amount * max_open_trades): {exposure} USDT")
    if exposure > CAPITAL_ESTIMATE:
        print(f"[WARN] exposure {exposure} > conservative capital estimate {CAPITAL_ESTIMATE} USDT")
        print("       Reduce max_open_trades or stake_amount before going live.")
    else:
        print(f"[OK] exposure within {CAPITAL_ESTIMATE} USDT estimate")
    print()

    print("=== Manual checklist (cannot be automated) ===")
    print("[ ] Binance account fully KYC-verified")
    print("[ ] USDT-M Futures activated on Binance account")
    print("[ ] Futures permission enabled on the API key")
    print("[ ] Withdrawal permission DISABLED on the API key (security)")
    print("[ ] IP whitelist set on API key to Oracle server (REDACTED-SERVER_IP)")
    print("[ ] Hedge mode OFF (one-way mode) — Freqtrade expects one-way")
    print("[ ] Initial isolated margin per pair set to a sane value")


if __name__ == "__main__":
    main()
