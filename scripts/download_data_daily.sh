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

docker-compose run --rm freqtrade download-data \
    --timeframe 15m 30m 1h 4h 1d \
    --days 3 \
    --trading-mode futures >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === daily download done (exit=$EXIT) ===" >> "$LOG"
exit $EXIT
