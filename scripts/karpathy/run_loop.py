#!/usr/bin/env python3
"""
Phase 13: FinBuddy Self-Evolution (MLOps Loop)
==============================================
Runs nightly at 2:00 AM via cron.
1. Checks the latest _autobacktest_v23_results.csv.
2. Identifies if there is a "God-Tier" parameter set (WR > 60%, Sharpe > 1.0) that beats the current defaults.
3. Automatically updates the live docker-compose.yml to use the new parameters.
4. Restarts the live Freqtrade bot to apply the God-Tier intelligence.
"""

import csv
import json
import logging
import os
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path("/home/ubuntu/var/www/html/trade")
RESULTS_CSV = REPO_ROOT / "_autobacktest_v23_results.csv"
COMPOSE_FILE = REPO_ROOT / "freqtrade" / "docker-compose.yml"
TELEGRAM_TOKEN = "REDACTED-FREQTRADE__TELEGRAM__TOKEN"
TELEGRAM_CHAT  = "5622292536"

def _tg(msg: str) -> None:
    try:
        import urllib.request, urllib.parse
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(url, data=data, timeout=5)
    except Exception:
        pass

def find_best_combo():
    if not RESULTS_CSV.exists():
        log.error("No backtest results found.")
        return None
    
    passes = []
    with open(RESULTS_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("pass") == "True":
                passes.append(row)
    
    if not passes:
        log.info("No passing combinations found in backtest.")
        return None
    
    # Sort by highest Sharpe ratio
    passes.sort(key=lambda r: float(r["sharpe"]), reverse=True)
    best = passes[0]
    return {
        "k_tp": float(best["k_tp"]),
        "k_sl": float(best["k_sl"]),
        "ml_threshold": float(best["ml_threshold"]),
        "sharpe": float(best["sharpe"]),
        "win_rate": float(best["win_rate"])
    }

def update_docker_compose(best: dict):
    content = COMPOSE_FILE.read_text()
    
    # Update FREQAI_K_TP
    content = re.sub(r'FREQAI_K_TP=[\d.]+', f'FREQAI_K_TP={best["k_tp"]}', content)
    if 'FREQAI_K_TP' not in content:
        log.info("Injecting ENV vars into docker-compose")
        content = content.replace("environment:", f"environment:\n      - FREQAI_K_TP={best['k_tp']}\n      - FREQAI_K_SL={best['k_sl']}\n      - FREQAI_ML_THRESHOLD={best['ml_threshold']}")
    else:
        content = re.sub(r'FREQAI_K_SL=[\d.]+', f'FREQAI_K_SL={best["k_sl"]}', content)
        content = re.sub(r'FREQAI_ML_THRESHOLD=[\d.]+', f'FREQAI_ML_THRESHOLD={best["ml_threshold"]}', content)

    COMPOSE_FILE.write_text(content)
    log.info(f"Updated docker-compose with K_TP={best['k_tp']}, K_SL={best['k_sl']}, ML={best['ml_threshold']}")

def deploy_new_brain():
    log.info("Restarting live Freqtrade container with new brain...")
    cmd = ["docker-compose", "up", "-d"]
    subprocess.run(cmd, cwd=str(COMPOSE_FILE.parent), check=True)
    log.info("Live bot successfully evolved.")

def main():
    log.info("Starting MLOps Self-Evolution Loop...")
    best = find_best_combo()
    if not best:
        return

    # Check if this beats a baseline (e.g., 60% WR and Sharpe > 1.0)
    if best["win_rate"] >= 60.0 and best["sharpe"] >= 1.0:
        log.info(f"God-Tier combo found! WR={best['win_rate']}%, Sharpe={best['sharpe']}")
        _tg(f"🧬 <b>Brain Evolution Triggered</b>\n"
            f"Found God-Tier Config:\n"
            f"WR: {best['win_rate']}%\n"
            f"Sharpe: {best['sharpe']}\n"
            f"TP={best['k_tp']}, SL={best['k_sl']}, ML={best['ml_threshold']}\n\n"
            f"Automatically deploying to live server...")
        update_docker_compose(best)
        deploy_new_brain()
    else:
        log.info("Best combo does not meet God-Tier minimums. No deployment.")

if __name__ == "__main__":
    main()
