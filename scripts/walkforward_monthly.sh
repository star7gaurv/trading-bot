#!/bin/bash
# Monthly walk-forward auto-trigger.
# Runs on the 1st of each month at 03:00 UTC. Skips if a WF is already running.
# Uses --skip-download because daily download cron keeps data fresh.

set -e

LOCK=/tmp/finbuddy_walkforward.lock
LOG=/home/ubuntu/.finbuddy/logs/walk_forward.log
SCRIPT=/home/ubuntu/var/www/html/trade/scripts/walk_forward.py

mkdir -p "$(dirname "$LOG")"

# Single-instance lock — bail if a previous run is still going
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] another walk-forward already running, skipping" >> "$LOG"
    exit 0
fi

# Walk a 27-month outer window — full bull (12mo) + full bear (15mo) coverage
START=$(date -u -d '27 months ago' +'%Y-%m-01')
END=$(date -u +'%Y-%m-01')

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Monthly walk-forward starting: $START → $END ===" >> "$LOG"

python3 "$SCRIPT" \
    --start "$START" \
    --end "$END" \
    --train-months 6 \
    --test-months 1 \
    --slide-months 1 \
    --strategy CortexaAI_v23 \
    --timeframe 15m \
    --skip-download >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Monthly walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
