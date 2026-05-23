#!/bin/bash
# Daily walk-forward — short rolling window.
# Runs every day at 22:00 UTC. Skips if a daily WF is already running.
# 3-month trailing window · train=6mo · test=1mo · slide=1mo → 3 folds.
# With 2 parallel workers each fold takes ~6h; total wall clock ~12h (22:00→10:00 next morning).
# Fold timeout bumped to 6h (was 4.5h) — all folds were timing out mid-training on 37-pair config.
# Purpose: FAST REGRESSION DETECTOR — did today's live config break OOS performance?
# Deep 21-fold monthly validation is handled by walkforward_monthly.sh.

set -e

LOCK=/tmp/finbuddy_walkforward_daily.lock   # separate from deep lock
DEEP_LOCK=/tmp/finbuddy_walkforward_deep.lock
LOG=/home/ubuntu/.finbuddy/logs/walk_forward.log
SCRIPT=/home/ubuntu/var/www/html/trade/scripts/walk_forward.py

mkdir -p "$(dirname "$LOG")"

# Single-instance lock — bail if a previous daily run is still going
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] daily WF already running, skipping" >> "$LOG"
    exit 0
fi

# Fix 9 (2026-05-22): mutual exclusion — skip daily if deep WF is still running.
# Both spawn max-workers=2 × lgbm_threads=2 = 4 threads each. Running both in
# parallel = 8 threads on a 4-core server → OOM. Root cause of 03:26 and 09:27 UTC crashes.
if [ -f "$DEEP_LOCK" ] && flock -n "$DEEP_LOCK" true 2>/dev/null; then
    : # deep lock file exists but is not held — deep WF finished, safe to proceed
elif [ -f "$DEEP_LOCK" ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] deep WF still running — skipping daily WF to prevent OOM" >> "$LOG"
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
    --max-workers 2 \
    --lgbm-threads 2 >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
