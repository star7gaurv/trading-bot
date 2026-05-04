#!/usr/bin/env python3
"""
golive_checklist.py — 11 automated pre-live checks for FinBuddy.
Exit 0 if all pass (or only WARNs). Exit 1 if any FAIL.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
CONFIG = ROOT / "freqtrade/user_data/config.json"
ENV_FILE = ROOT / "freqtrade/.env"
WF_MD = ROOT / "finbuddy_memory/research/best_bull_2024_walkforward.md"
SCRIPTS_DIR = ROOT / "freqtrade/user_data/scripts"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

results = []


def record(label, status, detail=""):
    results.append((label, status, detail))
    icon = {"PASS": f"{GREEN}PASS{RESET}", "FAIL": f"{RED}FAIL{RESET}", "WARN": f"{YELLOW}WARN{RESET}"}[status]
    print(f"  [{icon}] {label}" + (f" — {detail}" if detail else ""))


# 1. Walk-forward verdict = PROMOTE
def check_walkforward():
    if not WF_MD.exists():
        record("Walk-forward verdict", "FAIL", f"file missing: {WF_MD}")
        return
    text = WF_MD.read_text()
    if "**PROMOTE**" in text:
        record("Walk-forward verdict", "PASS", "PROMOTE found in walkforward.md")
    else:
        verdict = "DO NOT PROMOTE" if "DO NOT PROMOTE" in text else "unknown"
        record("Walk-forward verdict", "FAIL", f"verdict is '{verdict}' — re-run backtest grid")


# 2. trading_mode = futures
def check_trading_mode():
    try:
        cfg = json.loads(CONFIG.read_text())
        mode = cfg.get("trading_mode", "")
        if mode == "futures":
            record("trading_mode = futures", "PASS")
        else:
            record("trading_mode = futures", "FAIL", f"got '{mode}'")
    except Exception as e:
        record("trading_mode = futures", "FAIL", str(e))


# 3. margin_mode = isolated
def check_margin_mode():
    try:
        cfg = json.loads(CONFIG.read_text())
        mode = cfg.get("margin_mode", "")
        if mode == "isolated":
            record("margin_mode = isolated", "PASS")
        else:
            record("margin_mode = isolated", "FAIL", f"got '{mode}'")
    except Exception as e:
        record("margin_mode = isolated", "FAIL", str(e))


# 4. config.json exchange.key == "" (env var handles it)
def check_config_key_empty():
    try:
        cfg = json.loads(CONFIG.read_text())
        key = cfg.get("exchange", {}).get("key", "NOT_SET")
        if key == "":
            record("config.json exchange.key is empty", "PASS", "credentials via env var only")
        else:
            record("config.json exchange.key is empty", "FAIL", f"key='{key[:12]}...' — remove from config")
    except Exception as e:
        record("config.json exchange.key is empty", "FAIL", str(e))


# 5. .env FREQTRADE__EXCHANGE__SECRET not empty/placeholder
def check_env_secret():
    if not ENV_FILE.exists():
        record(".env secret set", "FAIL", f"{ENV_FILE} not found")
        return
    secret = ""
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("FREQTRADE__EXCHANGE__SECRET="):
            secret = line.split("=", 1)[1].strip()
    placeholders = {"", "PASTE_YOUR_BINANCE_SECRET_HERE", "your_secret_here"}
    if secret and secret not in placeholders:
        record(".env FREQTRADE__EXCHANGE__SECRET set", "PASS")
    else:
        record(".env FREQTRADE__EXCHANGE__SECRET set", "FAIL",
               "secret is empty or placeholder — paste real secret into freqtrade/.env")


# 6. pairlists[0] = StaticPairList
def check_pairlist():
    try:
        cfg = json.loads(CONFIG.read_text())
        first = cfg.get("pairlists", [{}])[0].get("method", "")
        if first == "StaticPairList":
            record("pairlists[0] = StaticPairList", "PASS")
        else:
            record("pairlists[0] = StaticPairList", "FAIL", f"got '{first}'")
    except Exception as e:
        record("pairlists[0] = StaticPairList", "FAIL", str(e))


# 7. label_period_candles = 12
def check_label_period():
    try:
        cfg = json.loads(CONFIG.read_text())
        val = cfg.get("freqai", {}).get("feature_parameters", {}).get("label_period_candles")
        if val == 12:
            record("label_period_candles = 12", "PASS")
        else:
            record("label_period_candles = 12", "FAIL", f"got {val}")
    except Exception as e:
        record("label_period_candles = 12", "FAIL", str(e))


# 8. RiskEngine importable
def check_risk_engine():
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import importlib
        re_mod = importlib.import_module("risk_engine")
        engine = re_mod.RiskEngine()
        mult = engine.stake_multiplier("NEUTRAL")
        record("RiskEngine importable", "PASS", f"stake_multiplier(NEUTRAL)={mult}")
    except Exception as e:
        record("RiskEngine importable", "FAIL", str(e))


# 9. docker freqtrade container running
def check_docker():
    try:
        out = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", "freqtrade"],
            capture_output=True, text=True, timeout=10
        )
        status = out.stdout.strip()
        if status == "running":
            record("docker freqtrade running", "PASS")
        else:
            record("docker freqtrade running", "FAIL", f"container status: '{status}'")
    except Exception as e:
        record("docker freqtrade running", "FAIL", str(e))


# 10. dry_run = True
def check_dry_run():
    try:
        cfg = json.loads(CONFIG.read_text())
        dry = cfg.get("dry_run", False)
        if dry is True:
            record("dry_run = True (safety check)", "PASS")
        else:
            record("dry_run = True (safety check)", "FAIL",
                   "dry_run is False — only flip after walk-forward PROMOTES")
    except Exception as e:
        record("dry_run = True (safety check)", "FAIL", str(e))


# 11. Manual warning — Binance futures permission
def check_binance_futures_warn():
    record("Binance API has Futures permission", "WARN",
           "manually verify on binance.com → API Management → key permissions → Enable Futures")


def main():
    print("\n=== FinBuddy Go-Live Checklist ===\n")
    check_walkforward()
    check_trading_mode()
    check_margin_mode()
    check_config_key_empty()
    check_env_secret()
    check_pairlist()
    check_label_period()
    check_risk_engine()
    check_docker()
    check_dry_run()
    check_binance_futures_warn()

    passes = sum(1 for _, s, _ in results if s == "PASS")
    fails = [label for label, s, _ in results if s == "FAIL"]
    warns = sum(1 for _, s, _ in results if s == "WARN")

    print(f"\n=== Summary: {passes}/11 PASS | {len(fails)} FAIL | {warns} WARN ===")
    if fails:
        print("Blockers:")
        for f in fails:
            print(f"  • {f}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
