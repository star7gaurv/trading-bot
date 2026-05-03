#!/usr/bin/env bash
# Cron-safe wrapper. Exits 0 fast if results CSV missing or empty.
set -u
ROOT="/home/ubuntu/var/www/html/trade"
CSV="$ROOT/_autobacktest_results.csv"
LOG="/tmp/finbuddy_promotion_$(date -u +%Y%m%d).log"

[ -s "$CSV" ] || { echo "[promotion] no results yet" >> "$LOG"; exit 0; }
# Skip if grid still running
pgrep -f "scripts/autobacktest.py" >/dev/null && { echo "[promotion] grid running; skip" >> "$LOG"; exit 0; }

cd "$ROOT" || exit 0
BACKTEST_TIMERANGE="${BACKTEST_TIMERANGE:-20240101-20250101}" \
  python3 scripts/promote_best_config.py >> "$LOG" 2>&1
