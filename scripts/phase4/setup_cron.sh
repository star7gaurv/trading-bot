#!/bin/bash
# =============================================================================
# FinBuddy Phase 4 — Cron Setup for Memory Auto-Writer
# =============================================================================
# Installs two cron jobs:
#   1. External data aggregator — every 15 min (Phase 2)
#   2. Memory writer — every 15 min (Phase 4)
#
# Run once from server:
#   chmod +x scripts/phase4/setup_cron.sh
#   ./scripts/phase4/setup_cron.sh
#
# Prerequisites:
#   - FreqTrade Docker container named 'freqtrade' is running
#   - gaurav branch is checked out in REPO_ROOT
#   - Git is configured with push access on the server
# =============================================================================

set -e

FREQTRADE_DIR="/home/ubuntu/var/www/html/trade/freqtrade"

echo "==========================================================="
echo " FinBuddy Phase 4 — Cron Setup"
echo "==========================================================="

# --- Verify prerequisites ---
echo ""
echo "[1/3] Checking prerequisites..."

if ! docker ps | grep -q freqtrade; then
  echo "  [×] FreqTrade container not running. Start it first."
  exit 1
fi
echo "  ✓ FreqTrade container running"

if [ ! -f "$FREQTRADE_DIR/scripts/phase4/memory_writer.py" ]; then
  echo "  [×] memory_writer.py not found. Run 'git pull origin gaurav' first."
  exit 1
fi
echo "  ✓ memory_writer.py found"

if [ ! -f "$FREQTRADE_DIR/scripts/phase2/external_data_aggregator.py" ]; then
  echo "  [×] external_data_aggregator.py not found. Run 'git pull origin gaurav' first."
  exit 1
fi
echo "  ✓ external_data_aggregator.py found"

# --- Build cron entries ---
echo ""
echo "[2/3] Installing cron jobs..."

CRON_EXT_DATA="*/15 * * * * docker exec freqtrade python /freqtrade/scripts/phase2/external_data_aggregator.py >> /tmp/finbuddy_ext_data.log 2>&1"
CRON_MEMORY="*/15 * * * * cd $FREQTRADE_DIR && python scripts/phase4/memory_writer.py >> /tmp/finbuddy_memory_writer.log 2>&1"

# Check if cron jobs already exist
(crontab -l 2>/dev/null || echo "") | {
  CURRENT=$(cat)
  UPDATED="$CURRENT"

  if echo "$CURRENT" | grep -q "external_data_aggregator"; then
    echo "  ✓ External data aggregator cron already installed (skipping)"
  else
    UPDATED="$UPDATED
$CRON_EXT_DATA"
    echo "  + Installing: external_data_aggregator (every 15 min)"
  fi

  if echo "$CURRENT" | grep -q "memory_writer"; then
    echo "  ✓ Memory writer cron already installed (skipping)"
  else
    UPDATED="$UPDATED
$CRON_MEMORY"
    echo "  + Installing: memory_writer (every 15 min)"
  fi

  echo "$UPDATED" | crontab -
}

# --- Verify ---
echo ""
echo "[3/3] Verifying cron jobs..."
crontab -l | grep -E "(external_data_aggregator|memory_writer)" | while read line; do
  echo "  ✓ $line"
done

# --- Test run ---
echo ""
echo "Running test run of external data aggregator..."
docker exec freqtrade python /freqtrade/scripts/phase2/external_data_aggregator.py 2>&1 | head -20

echo ""
echo "Running test run of memory writer..."
cd "$FREQTRADE_DIR"
python scripts/phase4/memory_writer.py 2>&1 | head -20

echo ""
echo "==========================================================="
echo " ✅ Cron setup complete!"
echo "   Logs: /tmp/finbuddy_ext_data.log"
echo "         /tmp/finbuddy_memory_writer.log"
echo "   Check: crontab -l"
echo "==========================================================="
