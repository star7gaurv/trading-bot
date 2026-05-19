#!/bin/bash
# Daily walk-forward — short rolling window (added 2026-05-19).
# Runs every day at 22:00 UTC. Skips if a WF is already running.
# Trailing 12 months · train=6mo · test=1mo · slide=1mo → ~7 folds, ~80–90 min.
# Heavy 27-month run still happens monthly on the 1st (walkforward_monthly.sh).

set -e

LOCK=/tmp/finbuddy_walkforward.lock
LOG=/home/ubuntu/.finbuddy/logs/walk_forward.log
SCRIPT=/home/ubuntu/var/www/html/trade/scripts/walk_forward.py

mkdir -p "$(dirname "$LOG")"

# Single-instance lock — shared with monthly run, prevents overlap
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] another walk-forward already running, skipping daily" >> "$LOG"
    exit 0
fi

# Trailing 12 months
START=$(date -u -d '12 months ago' +'%Y-%m-01')
END=$(date -u +'%Y-%m-01')

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward starting: $START → $END ===" >> "$LOG"

python3 "$SCRIPT" \
    --start "$START" \
    --end "$END" \
    --train-months 6 \
    --test-months 1 \
    --slide-months 1 \
    --strategy FinBuddyFreqAI \
    --timeframe 1h \
    --skip-download >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
