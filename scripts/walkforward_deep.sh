#!/bin/bash
# 4-day deep walk-forward — full 27-month rolling window.
# Runs every 4 days at 18:30 UTC (30 18 */4 * *) = midnight IST.
# Finishes ~6-8h later → report ready by morning IST on day 2.
# 27-month window · train=6mo · test=1mo · slide=2mo → 11 folds.
# --cpu-shares 256: Docker-native nice — yields CPU to live bot+brain under
#   contention, uses full CPU when system is idle. Replaces host nice (which
#   does NOT propagate into Docker containers).
# Purpose: DEEP PROMOTION GATE — full regime coverage (bull+bear+chop)
#          for Phase 10 live migration decisions.
# Separate lock from daily so daily regression checks still fire independently.

set -e

LOCK=/tmp/finbuddy_walkforward_deep.lock
DAILY_LOCK=/tmp/finbuddy_walkforward_daily.lock
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

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === 4-day deep walk-forward starting: $START → $END (11 folds, 2 workers) ===" >> "$LOG"

python3 "$SCRIPT" \
    --start "$START" \
    --end "$END" \
    --train-months 6 \
    --test-months 1 \
    --slide-months 2 \
    --strategy FinBuddyFreqAI_v23 \
    --timeframe 15m \
    --config config.json \
    --skip-download \
    --max-workers 2 \
    --lgbm-threads 2 \
    --cpu-shares 256 >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === 4-day deep walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
