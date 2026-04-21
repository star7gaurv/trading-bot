# Server Setup Instructions
> Back to hub → [[CONTEXT]]

## Step 1 — Pull the vault onto the server
SSH into the Oracle server and run:
```bash
cd /home/ubuntu/var/www/html/trade
git pull origin main
ls finbuddy_memory/
# Should show: CONTEXT.md  SERVER_SETUP.md  regimes/  research/  scripts/  signals/  strategies/
```

## Step 2 — Run the one-time setup script
```bash
bash /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/setup.sh
```

This will:
- Make scripts executable
- Configure git user for commits
- Add an hourly cron job that auto-pushes memory changes to GitHub
- Write a test research entry and push it

## Step 3 — Verify it worked
On your local machine, run `git pull` in `C:\laragon\www\trading-bot\` and check if a new file appeared in `finbuddy_memory/research/`. If yes — the pipeline is live. ✅

---

## Manual Usage (any time)

**Write a research entry:**
```bash
python3 /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/memory_writer.py research \
  --theme "BTC consolidating post-halving" \
  --insight "RSI divergence reliable in BULL regime" \
  --risk "Altcoin liquidation risk elevated" \
  --action "Tighten SL on small caps"
```

**Log a signal:**
```bash
python3 /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/memory_writer.py signal \
  --signal BUY --regime BULL --rsi 58.2 --macd 0.003 \
  --reason "Bullish crossover with volume confirmation"
```

**Update regime:**
```bash
python3 /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/memory_writer.py regime \
  --from NEUTRAL --to BULL --confidence 0.78
```

---
*Winning strategies → [[strategies/winners]]*
*Cron logs at: `/home/ubuntu/finbuddy_memory_cron.log`*
