# FinBuddy — Scripts

All helper scripts for deployment, backtesting, and data collection.

---

## Task 1.3 — Backtest (Run this after Task 1.2 is deployed)

### Quick run
```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
chmod +x scripts/run_backtest.sh
./scripts/run_backtest.sh
```

### What it does
1. Pre-flight checks (verifies FinBuddyLLMModel.py and FinBuddyFreqAI.py exist)
2. Downloads historical data (BTC, ETH, SOL, BNB, XRP — 15m + 5m + 1h, Jan 2025 — Apr 2026)
3. Runs walk-forward backtest inside Docker
4. Calls `parse_backtest.py` to auto-grade PASS/FAIL

### Acceptance criteria (Task 1.3 definition of done)
| Metric | Must be |
|---|---|
| Win rate | > 50% |
| Sharpe ratio | > 0.5 |
| Max drawdown | < 20% |
| Profit factor | > 1.2 |

### Files
| File | Purpose |
|---|---|
| `run_backtest.sh` | One-command backtest runner |
| `backtest_config.json` | Isolated backtest config (no live keys, Telegram disabled) |
| `parse_backtest.py` | Reads result JSON, prints PASS/FAIL with color |

---

## Phase 2 — External Data Fetchers (Coming next)

| File | Data Source | Adds To Model |
|---|---|---|
| `fetch_fear_greed.py` | Alternative.me | Market sentiment (0–100) |
| `fetch_coingecko.py` | CoinGecko API | BTC dominance, global mcap |
| `fetch_cryptopanic.py` | CryptoPanic API | News sentiment score |
| `fetch_defillama.py` | DefiLlama API | Total DeFi TVL |
| `fetch_google_trends.py` | pytrends | Bitcoin search interest |

---

## Phase 4 — Memory Auto-Writer (Coming after Phase 2)

| File | Purpose |
|---|---|
| `memory_writer.py` | Auto-writes signal results + regime changes to Obsidian vault |
| `setup_cron.sh` | Sets up cron job for auto-commit of memory vault |

---

*All scripts run inside the FreqTrade Docker container via `docker exec`.*
*Never run scripts directly on host Python — always use docker exec.*
