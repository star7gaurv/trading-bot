#!/bin/bash
cd /home/ubuntu/var/www/html/trade
git add finbuddy_memory/ freqtrade/user_data/data/external/ 2>/dev/null
git diff --staged --quiet || git commit -m "chore: finbuddy memory update $(date '+%Y-%m-%d %H:%M')" --no-verify
git push origin master 2>/dev/null || true
