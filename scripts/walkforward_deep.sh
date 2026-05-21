#!/bin/bash
# 4-day deep walk-forward — full 27-month rolling window.
# Runs every 4 days at 03:00 UTC (0 3 */4 * *).
# 27-month window · train=6mo · test=1mo · slide=1mo → 21 folds.
# With 3 parallel workers: ceil(21/3)=7 rounds × ~5.5h ≈ 38.5h.
# Finishes well within the 96h (4-day) window before next trigger.
# Purpose: DEEP PROMOTION GATE — full regime coverage (bull+bear+chop)
#          for Phase 10 live migration decisions.
# Separate lock from daily so daily regression checks still fire independently.

set -e

LOCK=/tmp/finbuddy_walkforward_deep.lock
LOG=/home/ubuntu/.finbuddy/logs/walk_forward_deep.log
SCRIPT=/home/ubuntu/var/www/html/trade/scripts/walk_forward.py

mkdir -p "$(dirname "$LOG")"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] deep WF already running, skipping" >> "$LOG"
    exit 0
fi

# Full 27-month trailing window — covers bull + bear + chop regimes
START=$(date -u -d '27 months ago' +'%Y-%m-01')
END=$(date -u +'%Y-%m-01')

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === 4-day deep walk-forward starting: $START → $END (21 folds, 3 workers) ===" >> "$LOG"

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
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === 4-day deep walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
