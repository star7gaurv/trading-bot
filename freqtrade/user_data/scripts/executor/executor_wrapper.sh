#!/usr/bin/env bash
# Runs bridge first (pulls FreqTrade open trades → executor_signals.json),
# then executor (dedup audit log).
set -e
ROOT="/home/ubuntu/var/www/html/trade"
python3 "$ROOT/freqtrade/user_data/scripts/executor/freqtrade_bridge.py"
python3 "$ROOT/freqtrade/user_data/scripts/executor/executor.py"
