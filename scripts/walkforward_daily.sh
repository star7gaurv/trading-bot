#!/bin/bash
# Daily walk-forward — single-fold regression detector.
# Runs every day at 22:00 UTC. Skips if a daily WF is already running.
# 2026-05-24 (CPU starvation fix): reduced to 1 fold (train=6mo · test=1mo · slide=1mo).
# Deep WF every 4 days remains the source of truth for promotion decisions; this is a daily
# pulse-check that today's live config still works on the last month of data.
# Solo fold training ~5h with ~536 features × 37 pairs → finishes by ~03:00 UTC.
# SEQUENTIAL (max-workers=1) — must stay this way: parallel folds caused OOM crashes that
# restarted the live bot at 03:26 and 09:27 UTC (15-bug session Fix 9, commit 3deeafc).

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

# Trailing 1 month — single fold, fast regression detector
# 7mo window = 6mo train + 1mo test → (7-6-1)/1 + 1 = 1 fold
START=$(date -u -d '7 months ago' +'%Y-%m-01')
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
    --max-workers 1 \
    --lgbm-threads 2 \
    --cpu-shares 512 >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
