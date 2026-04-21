#!/bin/bash
# FinBuddy Memory — One-Time Server Setup
# Run this ONCE on the Oracle server after git pull.
# Sets up permissions and cron job for auto-commit.

REPO_ROOT="/home/ubuntu/var/www/html/trade"
SCRIPT_PATH="$REPO_ROOT/finbuddy_memory/scripts/auto_commit.sh"
LOG_FILE="/home/ubuntu/finbuddy_memory_cron.log"

echo "=== FinBuddy Memory Setup ==="

# 1. Make scripts executable
chmod +x "$SCRIPT_PATH"
chmod +x "$REPO_ROOT/finbuddy_memory/scripts/memory_writer.py"
echo "✅ Scripts made executable"

# 2. Configure git (needed for commits to work)
git -C "$REPO_ROOT" config user.email "finbuddy@trading-bot"
git -C "$REPO_ROOT" config user.name "FinBuddy"
echo "✅ Git user configured"

# 3. Add cron job: auto-commit every hour
CRON_JOB="0 * * * * $SCRIPT_PATH >> $LOG_FILE 2>&1"
# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "auto_commit.sh"; then
    echo "⏭️  Cron job already exists — skipping"
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Cron job added: auto-commit every hour"
fi

# 4. Quick test — write a test entry
python3 "$REPO_ROOT/finbuddy_memory/scripts/memory_writer.py" research \
  --theme "Server setup complete" \
  --insight "FinBuddy memory pipeline is live" \
  --risk "None" \
  --action "Monitoring started"
echo "✅ Test entry written to research log"

# 5. First commit
bash "$SCRIPT_PATH"

echo ""
echo "=== Setup Complete ==="
echo "Memory auto-commits every hour."
echo "Check logs at: $LOG_FILE"
echo ""
echo "Manual write example:"
echo "  python3 $REPO_ROOT/finbuddy_memory/scripts/memory_writer.py research \\"
echo "    --theme 'BTC breaking ATH' --insight 'Momentum strong' \\"
echo "    --risk 'Overextended' --action 'Hold current positions'"
