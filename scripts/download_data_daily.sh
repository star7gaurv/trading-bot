#!/bin/bash
# Daily futures-data refresh.
# Downloads the last 3 days of OHLCV + funding + mark data so walk-forward
# always has up-to-date history without a 2h download stall before each run.

set -e

LOCK=/tmp/finbuddy_dl.lock
LOG=/home/ubuntu/.finbuddy/logs/download_data.log
COMPOSE_DIR=/home/ubuntu/var/www/html/trade/freqtrade

mkdir -p "$(dirname "$LOG")"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] download already running, skipping" >> "$LOG"
    exit 0
fi

cd "$COMPOSE_DIR"

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === daily data refresh ===" >> "$LOG"

# E4 (2026-06-11): full backfill for NEW pairs. The 3-day incremental gives a
# freshly whitelisted pair only 3 days of history → 4h NaN crash (2026-05-19
# known gap). Detect pairs with no local 15m feather and backfill those first.
NEW_PAIRS=$(python3 - <<'PYEOF'
import json
from pathlib import Path
cfg = json.load(open("user_data/config.json"))
data_dir = Path("user_data/data/binance/futures")
missing = []
for p in cfg["exchange"]["pair_whitelist"]:
    fname = p.replace("/", "_").replace(":", "_") + "-15m-futures.feather"
    if not (data_dir / fname).exists():
        missing.append(p)
print(" ".join(missing))
PYEOF
)
if [ -n "$NEW_PAIRS" ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] NEW pairs detected, full backfill: $NEW_PAIRS" >> "$LOG"
    docker-compose run --rm freqtrade download-data \
        --timeframe 15m 30m 1h 4h 1d \
        --days 1200 \
        --pairs $NEW_PAIRS \
        --trading-mode futures >> "$LOG" 2>&1
fi

docker-compose run --rm freqtrade download-data \
    --timeframe 15m 30m 1h 4h 1d \
    --days 3 \
    --trading-mode futures >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === daily download done (exit=$EXIT) ===" >> "$LOG"
# Also print to stdout so the cron redirect file (download_data_daily.log) gets its mtime
# updated — cron_status.py uses that mtime for the staleness check.
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] daily download done (exit=$EXIT)"
exit $EXIT
