#!/usr/bin/env bash
# =============================================================================
# Phase 2 — External data fetchers cron installer
# Run once: bash scripts/phase2/setup_cron.sh
# =============================================================================
set -euo pipefail

TRADE_DIR="/home/ubuntu/var/www/html/trade"
PHASE2_DIR="${TRADE_DIR}/scripts/phase2"
LOG_DIR="${TRADE_DIR}/logs"
PYTHON="/usr/bin/python3"

mkdir -p "${LOG_DIR}"

chmod +x "${PHASE2_DIR}"/*.py 2>/dev/null || true

# Build cron block
CRON_BLOCK="
# FinBuddy Phase 2 — External Data Fetchers
# Fear & Greed — every 4 hours
0 */4 * * * ${PYTHON} ${PHASE2_DIR}/fetch_fear_greed.py >> ${LOG_DIR}/fetch_fear_greed.log 2>&1
# CoinGecko market data — every 1 hour
5 * * * * ${PYTHON} ${PHASE2_DIR}/fetch_coingecko.py >> ${LOG_DIR}/fetch_coingecko.log 2>&1
# CryptoPanic news — every 30 minutes
*/30 * * * * ${PYTHON} ${PHASE2_DIR}/fetch_cryptopanic.py >> ${LOG_DIR}/fetch_cryptopanic.log 2>&1
# DefiLlama TVL — every 6 hours
10 */6 * * * ${PYTHON} ${PHASE2_DIR}/fetch_defillama.py >> ${LOG_DIR}/fetch_defillama.log 2>&1
# Google Trends — once per day at 06:00
0 6 * * * ${PYTHON} ${PHASE2_DIR}/fetch_google_trends.py >> ${LOG_DIR}/fetch_google_trends.log 2>&1
# External data aggregator — every 1 hour (runs after coingecko)
15 * * * * ${PYTHON} ${PHASE2_DIR}/external_data_aggregator.py >> ${LOG_DIR}/external_aggregator.log 2>&1
"

# Append only if not already installed
CURRENT=$(crontab -l 2>/dev/null || echo "")
if echo "${CURRENT}" | grep -q "FinBuddy Phase 2"; then
    echo "Phase 2 crons already installed. Skipping."
else
    (echo "${CURRENT}"; echo "${CRON_BLOCK}") | crontab -
    echo "Phase 2 crons installed successfully."
fi

# Also install auto_experiment.sh cron
if echo "${CURRENT}" | grep -q "auto_experiment"; then
    echo "auto_experiment cron already installed. Skipping."
else
    chmod +x "${TRADE_DIR}/scripts/auto_experiment.sh"
    AUTO_CRON="\n# FinBuddy — Nightly walk-forward backtest\n0 2 * * * ${TRADE_DIR}/scripts/auto_experiment.sh >> ${LOG_DIR}/auto_experiment.log 2>&1"
    (crontab -l 2>/dev/null || echo ""; printf "${AUTO_CRON}") | crontab -
    echo "auto_experiment nightly cron installed."
fi

echo ""
echo "Active crontab:"
crontab -l
