#!/bin/bash
# =============================================================================
# FinBuddy — Task 1.3 Backtest Runner
# =============================================================================
# Usage:
#   chmod +x scripts/run_backtest.sh
#   ./scripts/run_backtest.sh
#
# Runs walk-forward backtest for FinBuddyFreqAI + FinBuddyLLMModel
# then calls parse_backtest.py to auto-grade the results.
#
# Run from: /home/ubuntu/var/www/html/trade/freqtrade
# =============================================================================

set -e

FREQTRADE_DIR="/home/ubuntu/var/www/html/trade/freqtrade"
SCRIPTS_DIR="$FREQTRADE_DIR/scripts"
RESULTS_DIR="$FREQTRADE_DIR/user_data/backtest_results"
CONFIG="$SCRIPTS_DIR/backtest_config.json"
LOG_FILE="$RESULTS_DIR/backtest_$(date +%Y%m%d_%H%M%S).log"

echo "==========================================================="
echo " FinBuddy — Task 1.3 Walk-Forward Backtest"
echo " $(date '+%Y-%m-%d %H:%M:%S IST')"
echo "==========================================================="

# --- Pre-flight checks ---
echo ""
echo "[✓] Checking freqaimodels directory..."
if [ ! -f "$FREQTRADE_DIR/user_data/freqaimodels/FinBuddyLLMModel.py" ]; then
  echo "[×] ERROR: FinBuddyLLMModel.py not found in user_data/freqaimodels/"
  echo "    Run 'git pull origin gaurav' first, then retry."
  exit 1
fi
echo "    FinBuddyLLMModel.py ✓"

echo "[✓] Checking strategy file..."
if [ ! -f "$FREQTRADE_DIR/user_data/strategies/FinBuddyFreqAI.py" ]; then
  echo "[×] ERROR: FinBuddyFreqAI.py not found in user_data/strategies/"
  exit 1
fi
echo "    FinBuddyFreqAI.py ✓"

mkdir -p "$RESULTS_DIR"

# --- Step 1: Download historical data ---
echo ""
echo "[1/3] Downloading historical data (BTC/USDT, ETH/USDT, 15m, 5m, 1h)..."
docker exec freqtrade freqtrade download-data \
  --config /freqtrade/scripts/backtest_config.json \
  --timerange 20250101-20260401 \
  --timeframes 5m 15m 1h \
  --pairs BTC/USDT ETH/USDT SOL/USDT BNB/USDT XRP/USDT \
  2>&1 | tee -a "$LOG_FILE"

echo ""
echo "[2/3] Running walk-forward backtest..."
echo "    Strategy   : FinBuddyFreqAI"
echo "    FreqAI Model: FinBuddyLLMModel"
echo "    Timerange  : 20250101-20260401"
echo "    Timeframe  : 15m"
echo ""

docker exec \
  -e GROQ_API_KEY="${GROQ_API_KEY:-disabled_for_backtest}" \
  freqtrade freqtrade backtesting \
    --config /freqtrade/scripts/backtest_config.json \
    --strategy FinBuddyFreqAI \
    --freqaimodel FinBuddyLLMModel \
    --timerange 20250101-20260401 \
    --timeframe 15m \
    --export trades \
    --export-filename /freqtrade/user_data/backtest_results/backtest_finbuddy_$(date +%Y%m%d).json \
    2>&1 | tee -a "$LOG_FILE"

BACKTEST_EXIT=$?

if [ $BACKTEST_EXIT -ne 0 ]; then
  echo ""
  echo "[×] Backtest command failed (exit code $BACKTEST_EXIT)"
  echo "    Check log: $LOG_FILE"
  echo ""
  echo "    Common fixes:"
  echo "    1. Import error → check FinBuddyLLMModel.py base class import"
  echo "    2. No data → re-run Step 1 download manually"
  echo "    3. Strategy error → check FinBuddyFreqAI.py"
  exit 1
fi

# --- Step 3: Parse and grade results ---
echo ""
echo "[3/3] Parsing results..."

docker exec freqtrade python /freqtrade/scripts/parse_backtest.py \
  --results-dir /freqtrade/user_data/backtest_results \
  2>&1 | tee -a "$LOG_FILE"

echo ""
echo "Full log saved to: $LOG_FILE"
echo "==========================================================="
