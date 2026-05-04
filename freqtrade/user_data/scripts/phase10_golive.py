#!/usr/bin/env python3
"""
phase10_golive.py — Final go-live readiness check and instruction printer.

This script:
  1. Runs golive_checklist.py — aborts if any check FAILS.
  2. Prints a confirmation table of current live config.
  3. Prints go-live instructions.

It does NOT flip dry_run. Only print instructions.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
CONFIG = ROOT / "freqtrade/user_data/config.json"
WF_MD  = ROOT / "finbuddy_memory/research/best_bull_2024_walkforward.md"
CHECKLIST = ROOT / "freqtrade/user_data/scripts/golive_checklist.py"

BOLD  = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED   = "\033[91m"
RESET = "\033[0m"


def run_checklist() -> int:
    print(f"{BOLD}=== Step 1: Running go-live checklist ==={RESET}\n")
    result = subprocess.run([sys.executable, str(CHECKLIST)])
    return result.returncode


def read_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except Exception as e:
        print(f"{RED}Cannot read config.json: {e}{RESET}")
        sys.exit(1)


def read_wf_sharpe() -> str:
    if not WF_MD.exists():
        return "NOT RUN — grid still running"
    text = WF_MD.read_text()
    m = re.search(r"sharpe:\s*([-\d.]+)", text)
    verdict_line = ""
    for line in text.splitlines():
        if "Verdict" in line:
            verdict_line = line.strip("# ").strip()
            break
    sharpe = m.group(1) if m else "N/A"
    return f"{sharpe} ({verdict_line})" if verdict_line else sharpe


def print_table(cfg: dict, wf_sharpe: str):
    pairs = cfg.get("exchange", {}).get("pair_whitelist", [])
    if not pairs:
        pairs = cfg.get("pairlists", [{}])[0].get("pairs", ["(from StaticPairList)"])

    rows = [
        ("Current mode",       "DRY RUN" if cfg.get("dry_run") else f"{RED}LIVE{RESET}"),
        ("Exchange",           "Binance USDⓈ-M Futures"),
        ("Trading mode",       cfg.get("trading_mode", "?")),
        ("Margin mode",        cfg.get("margin_mode", "?")),
        ("Pairs",              ", ".join(pairs) if pairs else "?"),
        ("Stake per trade",    f"{cfg.get('stake_amount', '?')} USDT"),
        ("Max open trades",    str(cfg.get("max_open_trades", "?"))),
        ("Risk per trade",     "2% (RiskEngine MAX_RISK_PCT)"),
        ("Walk-forward Sharpe", wf_sharpe),
    ]

    print(f"\n{BOLD}=== Step 2: Current Configuration ==={RESET}\n")
    width = max(len(k) for k, _ in rows) + 2
    for key, val in rows:
        print(f"  {key:<{width}}: {val}")


def print_instructions():
    print(f"\n{BOLD}=== Step 3: Go-Live Instructions ==={RESET}\n")
    print(f"  {YELLOW}TO GO LIVE: set dry_run=false in config.json and restart docker{RESET}")
    print()
    print("  1. Edit config:  nano /home/ubuntu/var/www/html/trade/freqtrade/user_data/config.json")
    print('     Change:      "dry_run": true  →  "dry_run": false')
    print()
    print("  2. Restart bot:  cd /home/ubuntu/var/www/html/trade/freqtrade && docker-compose up -d")
    print()
    print("  3. Confirm live: curl -s -u bot:bot123 http://localhost:8080/api/v1/status | grep dry_run")
    print()
    print(f"  {RED}{BOLD}NEVER run with real capital until walk-forward PROMOTES.{RESET}")
    print(f"  {RED}Current walk-forward must show Verdict: PROMOTE before going live.{RESET}")


def main():
    rc = run_checklist()
    if rc != 0:
        print(f"\n{RED}{BOLD}CHECKLIST FAILED — fix blockers before proceeding.{RESET}")
        sys.exit(1)

    cfg = read_config()
    wf_sharpe = read_wf_sharpe()
    print_table(cfg, wf_sharpe)
    print_instructions()


if __name__ == "__main__":
    main()
