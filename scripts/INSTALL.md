# One-Command Setup — Run This on Server After git pull

```bash
cd /home/ubuntu/var/www/html/trade
git pull origin gaurav

# Install ALL crons (Phase 2 fetchers + nightly walk-forward)
bash scripts/phase2/setup_cron.sh

# Install Phase 4 memory writer
bash scripts/phase4/setup_cron.sh

# Make scripts executable
chmod +x scripts/auto_experiment.sh
chmod +x scripts/phase2/*.py

# Verify crons active
crontab -l
```

## What runs automatically after install

| Schedule | Script | Purpose |
|---|---|---|
| Daily 02:00 | `auto_experiment.sh` | Walk-forward backtest → parse → commit results to GitHub |
| Every 4h | `fetch_fear_greed.py` | Fear & Greed index |
| Every 1h | `fetch_coingecko.py` | Market cap / dominance |
| Every 30m | `fetch_cryptopanic.py` | Crypto news sentiment |
| Every 6h | `fetch_defillama.py` | DeFi TVL |
| Daily 06:00 | `fetch_google_trends.py` | BTC search trends |
| Every 1h | `external_data_aggregator.py` | Aggregate all external signals |
| Phase 4 schedule | `memory_writer.py` | Auto-update project memory files |

## Results Location

- Latest WF JSON : `experiments/wf_latest.json`
- Historical CSV : `experiments/results_log.csv`
- All run logs   : `logs/auto_experiment.log`
