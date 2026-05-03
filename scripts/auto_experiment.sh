#!/usr/bin/env bash
# =============================================================================
# auto_experiment.sh — Nightly walk-forward backtest runner
# Runs unattended. Cron: 0 2 * * * /home/ubuntu/var/www/html/trade/scripts/auto_experiment.sh
# Log:            /home/ubuntu/var/www/html/trade/logs/auto_experiment.log
# =============================================================================
set -euo pipefail

TRADE_DIR="/home/ubuntu/var/www/html/trade"
FT_CONTAINER="freqtrade"
MODEL_CACHE="${TRADE_DIR}/freqtrade/user_data/models/finbuddy_walkforward_v1"
LOG_DIR="${TRADE_DIR}/logs"
EXP_DIR="${TRADE_DIR}/experiments"

mkdir -p "${LOG_DIR}" "${EXP_DIR}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_DIR}/auto_experiment.log"; }

log "========== auto_experiment START =========="

# 1. Pull latest strategy code
cd "${TRADE_DIR}"
log "git pull origin gaurav"
git pull origin gaurav 2>&1 | tail -3 | while read l; do log "  git: $l"; done

# 2. Purge old walk-forward model cache (force fresh training each run)
if [ -d "${MODEL_CACHE}" ]; then
    log "Purging model cache: ${MODEL_CACHE}"
    rm -rf "${MODEL_CACHE}"
fi

# 3. Run walk-forward backtest inside the freqtrade container
log "Starting walk-forward backtest (20240315-20260415) — this will take 30-90 min"
docker exec "${FT_CONTAINER}" freqtrade backtesting \
    --config /freqtrade/user_data/backtest_config.json \
    --strategy FinBuddyFreqAI \
    --timerange 20240315-20260415 \
    --export trades \
    --cache none \
    2>&1 | tee -a "${LOG_DIR}/auto_experiment.log"

log "Backtest complete. Parsing results..."

# 4. Parse results — writes experiments/wf_latest.json + appends to results_log.csv
python3 "${TRADE_DIR}/scripts/walkforward_parse.py" \
    2>&1 | tee -a "${LOG_DIR}/auto_experiment.log"

# 5. Commit and push results to GitHub
cd "${TRADE_DIR}"
git add -A
COMMIT_MSG="auto: walk-forward results $(date +%Y-%m-%d)"
if git diff --cached --quiet; then
    log "Nothing new to commit."
else
    git commit -m "${COMMIT_MSG}"
    git push origin gaurav
    log "Pushed: ${COMMIT_MSG}"
fi

log "========== auto_experiment END =========="
