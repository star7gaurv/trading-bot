#!/usr/bin/env bash
# run_prediction_bench.sh — generate clean OOS predictions over a long window
# for the cross-sectional / mean-reversion research bench.
#
# Runs a FreqAI backtest with FREQAI_DUMP_PREDICTIONS=1 so the strategy writes
# per-pair raw predictions (&-future_return, do_predict, close) to
# freqtrade/user_data/pred_dump/*.parquet over the whole window. SVM is off in
# the 1h config ⇒ do_predict==1 throughout ⇒ no leak, unlike the live pkl.
#
# Usage:  run_prediction_bench.sh <config_basename> <timerange> [timeframe]
#   e.g.  run_prediction_bench.sh v23_regression_1h_config.json 20260501-20260601 1h
#
# Heavy: trains rolling models across the window. Run when brain/WF aren't busy.
set -euo pipefail
cd /home/ubuntu/var/www/html/trade

CONFIG="${1:?config basename, e.g. v23_regression_1h_config.json}"
TIMERANGE="${2:?timerange, e.g. 20250601-20260601}"
TF="${3:-1h}"

echo "[bench] clearing old dump…"
rm -f freqtrade/user_data/pred_dump/*.parquet 2>/dev/null || true

echo "[bench] backtesting $CONFIG  $TIMERANGE  tf=$TF  (dump ON)…"
cd freqtrade   # docker-compose.yml lives here (matches brain runner COMPOSE_DIR)
FREQAI_DUMP_PREDICTIONS=1 docker-compose run --rm --no-deps \
  -e FREQAI_DUMP_PREDICTIONS=1 \
  freqtrade backtesting \
  --config "/freqtrade/user_data/${CONFIG}" \
  --strategy CortexaAI_v23 \
  --freqaimodel LightGBMRegressor \
  --timerange "$TIMERANGE" \
  --timeframe "$TF" \
  --cache none 2>&1 | tail -25

echo "[bench] dump files:"
ls -la user_data/pred_dump/ 2>/dev/null | tail -30
echo "[bench] done. Analyze with: python3 scripts/research/cross_sectional_backtest.py --dump"
