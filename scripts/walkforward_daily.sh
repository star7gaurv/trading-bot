#!/bin/bash
# Daily walk-forward — short rolling window.
# Runs every day at 22:00 UTC. Skips if a daily WF is already running.
# 3-month trailing window · train=6mo · test=1mo · slide=1mo → 3 folds.
# With 3 parallel workers this completes in ~5-6h (well before next 22:00 trigger).
# Purpose: FAST REGRESSION DETECTOR — did today's live config break OOS performance?
# Deep 21-fold monthly validation is handled by walkforward_monthly.sh.

set -e

LOCK=/tmp/finbuddy_walkforward_daily.lock   # separate from monthly lock
LOG=/home/ubuntu/.finbuddy/logs/walk_forward.log
SCRIPT=/home/ubuntu/var/www/html/trade/scripts/walk_forward.py

mkdir -p "$(dirname "$LOG")"

# Single-instance lock — bail if a previous daily run is still going
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] daily WF already running, skipping" >> "$LOG"
    exit 0
fi

# Trailing 3 months — 3 folds, fast feedback
START=$(date -u -d '9 months ago' +'%Y-%m-01')   # 6mo train + 3mo test window
END=$(date -u +'%Y-%m-01')

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward starting: $START → $END ===" >> "$LOG"

python3 "$SCRIPT" \
    --start "$START" \
    --end "$END" \
    --train-months 6 \
    --test-months 1 \
    --slide-months 1 \
    --strategy FinBuddyFreqAI_v23 \
    --timeframe 15m \
    --config config.json \
    --skip-download \
    --max-workers 3 \
    --lgbm-threads 2 >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
