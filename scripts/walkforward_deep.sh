#!/bin/bash
# 4-day deep walk-forward — 18-month rolling window.
# Runs every 4 days at 18:30 UTC (30 18 */4 * *) = midnight IST.
# 18-month window · train=6mo · test=1mo · slide=2mo → 7 folds.
#
# 2026-05-26: Reduced from 27mo (11 folds) to 18mo (7 folds).
# Reason: 27mo × ~5h/fold = up to 55h — server was PERMANENTLY occupied
# every 4 days with 0 breathing room between runs. 18mo × ~5h = ~35h,
# giving the server ~1.5 days free between deep WF runs. Still covers
# 2024 bull + 2025 bear + 2025-26 recovery = full regime diversity.
# Statistically, 7 folds is sufficient for promotion gate decisions.
#
# --cpu-shares 256: Docker-native nice — yields CPU to live bot+brain under
#   contention, uses full CPU when system is idle. Replaces host nice (which
#   does NOT propagate into Docker containers).
# Purpose: DEEP PROMOTION GATE — regime coverage (bull+bear+chop)
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



# 18-month trailing window — covers bull (2024) + bear (2025) + recovery (2025-26)
START=$(date -u -d '18 months ago' +'%Y-%m-01')
END=$(date -u +'%Y-%m-01')

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === 4-day deep walk-forward starting: $START → $END (7 folds, 2 workers) ===" >> "$LOG"

# Follow the UI-selected timeframe (single source of truth), fallback 15m.
ACTIVE_TF=$(python3 -c "import json;print(json.load(open('/home/ubuntu/var/www/html/trade/finbuddy_memory/timeframe_profiles.json'))['active'])" 2>/dev/null || echo 15m)
python3 "$SCRIPT" \
    --start "$START" \
    --end "$END" \
    --train-months 6 \
    --test-months 1 \
    --slide-months 2 \
    --strategy CortexaAI_v23 \
    --timeframe "$ACTIVE_TF" \
    --config config.json \
    --skip-download \
    --reuse-models \
    --max-workers 2 \
    --lgbm-threads 2 >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === 4-day deep walk-forward done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
