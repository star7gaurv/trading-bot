#!/bin/bash
# One-time DEEP historical backfill (2026-06-08).
#
# Purpose: extend the brain's perspective backward in time. Existing data starts
# ~2023-09; Binance BTC/ETH USDT-M perpetuals go back to ~2019-2020. This backfills
# the gap so the brain gains exposure to market regimes it has NEVER seen:
#   • 2020-03 COVID crash       (black-swan liquidation cascade)
#   • 2021      parabolic euphoria + the May-2021 -50% flush
#   • 2022      sustained bear + LUNA (May) and FTX (Nov) collapses
#
# Non-destructive: uses --prepend, which ONLY adds candles BEFORE the existing
# start date. It never overwrites or re-downloads existing data. Safe to run while
# the live bot trades — download is network-bound (not CPU-bound), so it does not
# starve the live bot. Pairs that listed after the start date simply backfill to
# their own listing date.
#
# NOTE: `docker-compose run` does NOT accept --cpu-shares (it errors — this caused
# the 2026-06-01 WF crash). Do not add it here. Download I/O is naturally polite.
#
# Run once:  bash scripts/backfill_historical_data.sh
# Re-runnable: yes (prepend skips already-present ranges).

set -euo pipefail

START_DATE=20200101          # floor; per-pair clamps to its listing date automatically
LOCK=/tmp/finbuddy_backfill.lock
LOG=/home/ubuntu/.finbuddy/logs/backfill_historical.log
COMPOSE_DIR=/home/ubuntu/var/www/html/trade/freqtrade

mkdir -p "$(dirname "$LOG")"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] backfill already running, skipping" | tee -a "$LOG"
    exit 0
fi

cd "$COMPOSE_DIR"

echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === DEEP BACKFILL start (from ${START_DATE}, --prepend) ===" | tee -a "$LOG"

docker-compose run --rm freqtrade download-data \
    --timeframe 15m 30m 1h 4h 1d \
    --timerange "${START_DATE}-" \
    --prepend \
    --trading-mode futures >> "$LOG" 2>&1

EXIT=$?
echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] === DEEP BACKFILL done (exit=$EXIT) ===" | tee -a "$LOG"
exit $EXIT
