#!/bin/bash
# FinBuddy Memory Auto-Commit
# Commits and pushes any changes in finbuddy_memory/ to GitHub.
# Run by cron every hour (or call directly after memory_writer.py).

REPO_ROOT="/home/ubuntu/var/www/html/trade"
MEMORY_DIR="$REPO_ROOT/finbuddy_memory"

cd "$REPO_ROOT" || exit 1

# Check if there are any changes to commit
if git diff --quiet HEAD -- finbuddy_memory/ && git diff --cached --quiet -- finbuddy_memory/; then
    echo "$(date): No changes in finbuddy_memory/ — skipping commit"
    exit 0
fi

git add finbuddy_memory/
git commit -m "chore: finbuddy memory update $(date +%Y-%m-%d\ %H:%M)"
git push origin master

echo "$(date): ✅ finbuddy_memory pushed to GitHub"
