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

# Always emit one stdout line so the crontab redirect (walk_forward_daily.log)
# gets its mtime updated every day — prevents dashboard showing STALE when
# deep WF flock blocks the run and all internal echoes go only to $LOG.
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] daily WF cron fired"

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
# 2026-05-26: Reduced training window 6mo → 4mo.
# Reason: With 26 pairs × 530+ features, 6mo training was taking 5-6h and
# occasionally exceeding the 10h timeout. 4mo training ≈ 3-4h → completes
# reliably by 02:00 UTC. Daily WF is a pulse-check, not a promotion gate —
# 4 months of training data is sufficient to confirm today's live config
# still generates valid signals. Deep WF (7 folds × 6mo) remains the
# authoritative promotion gate with full historical coverage.
# 7mo window = 5mo train + 2mo test → 1 fold.
# 2026-06-04: Extended from 5mo (4mo+1mo) to 7mo (5mo+2mo).
# Reason: 1-month test window (May 2026) was deep BEAR market with effective
# threshold ~2.5σ → 0 trades every night. 2-month test covers Apr+May 2026,
# giving more trade opportunities while the bear persists. 5-month train
# includes Q4-2025 bull data, giving the model richer context.
# --cpu-shares removed: walk_forward.py accepts but silently ignores this flag
# (docker-compose run does not support it — same class as --tmpfs bug).
START=$(date -u -d '7 months ago' +'%Y-%m-01')
END=$(date -u +'%Y-%m-01')

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward starting: $START → $END ===" >> "$LOG"

# Follow the UI-selected timeframe (single source of truth), fallback 15m.
ACTIVE_TF=$(python3 -c "import json;print(json.load(open('/home/ubuntu/var/www/html/trade/finbuddy_memory/timeframe_profiles.json'))['active'])" 2>/dev/null || echo 15m)
python3 "$SCRIPT" \
    --start "$START" \
    --end "$END" \
    --train-months 5 \
    --test-months 2 \
    --slide-months 2 \
    --strategy CortexaAI_v23 \
    --timeframe "$ACTIVE_TF" \
    --config config.json \
    --skip-download \
    --max-workers 1 \
    --lgbm-threads 2 >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === Daily walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
