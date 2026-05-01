#!/usr/bin/env bash
# Simple stoploss tuning helper for FinBuddyFreqAI (Task 1.3 robustness)
#
# Runs the backtest multiple times with different stoploss values and prints
# a compact summary table so Gaurav + Perplexity can pick the best one.
#
# This script is designed to be run by Claude Code on the server:
#   cd /home/ubuntu/var/www/html/trade/freqtrade
#   chmod +x scripts/tune_stoploss.sh
#   ./scripts/tune_stoploss.sh
#
# It assumes:
# - Repo is on the `gaurav` branch
# - Freqtrade Docker container is named `freqtrade`
# - `scripts/run_backtest.sh` and `scripts/parse_backtest.py` already work

set -euo pipefail

ROOT_DIR="/home/ubuntu/var/www/html/trade/freqtrade"
SCRIPT_DIR="$ROOT_DIR/scripts"
STRATEGY_FILE="$ROOT_DIR/freqtrade/user_data/strategies/FinBuddyFreqAI.py"

STOPLOSSES=("-0.03" "-0.035" "-0.04")

cd "$ROOT_DIR"

if [ ! -f "$STRATEGY_FILE" ]; then
  echo "[ERROR] Strategy file not found: $STRATEGY_FILE" >&2
  exit 1
fi

if [ ! -x "$SCRIPT_DIR/run_backtest.sh" ]; then
  chmod +x "$SCRIPT_DIR/run_backtest.sh" || true
fi

RESULTS_CSV="$SCRIPT_DIR/_tune_stoploss_results.csv"
> "$RESULTS_CSV"

echo "stoploss,winrate,sharpe,drawdown,profit_factor" >> "$RESULTS_CSV"

for SL in "${STOPLOSSES[@]}"; do
  echo "\n[INFO] Testing stoploss=$SL" | tee /dev/stderr

  # Update stoploss in strategy file (in-place, matching `stoploss = -0.0X` pattern)
  sed -i "s/^    stoploss = -.*/    stoploss = $SL/" "$STRATEGY_FILE"

  # Commit change only locally inside container (backtest uses mounted volume)
  # Run the existing backtest script
  if ! "$SCRIPT_DIR/run_backtest.sh" > "$SCRIPT_DIR/_backtest_tmp.log" 2>&1; then
    echo "[WARN] Backtest failed for stoploss $SL (see _backtest_tmp.log). Recording NA metrics." >&2
    echo "$SL,NA,NA,NA,NA" >> "$RESULTS_CSV"
    continue
  fi

  # Let parse_backtest.py extract metrics in a machine-readable form
  # We assume parse_backtest.py supports `--csv` to print a single CSV line;
  # if not, Claude Code / Perplexity will extend it accordingly.
  if python3 "$SCRIPT_DIR/parse_backtest.py" --csv "$SCRIPT_DIR/_backtest_tmp.log" \
      >> "$RESULTS_CSV" 2>> "$SCRIPT_DIR/_tune_stoploss_errors.log"; then
    echo "[OK] Metrics recorded for stoploss $SL" | tee /dev/stderr
  else
    echo "[WARN] parse_backtest.py --csv failed for stoploss $SL. Check _tune_stoploss_errors.log." >&2
    echo "$SL,NA,NA,NA,NA" >> "$RESULTS_CSV"
  fi

done

echo "\n[SUMMARY] Stoploss tuning results (from $RESULTS_CSV):"
column -s, -t "$RESULTS_CSV" || cat "$RESULTS_CSV"
