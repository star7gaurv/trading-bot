# FinBuddy — Scripts

All helper scripts for backtesting, tuning, and data collection.

> **Core rule:** Any loop or repetitive task that can be automated by a script must be a script.
> AI (Perplexity / Claude) is for design, debugging, and analysis — not for running the same task manually over and over.

---

## Quick Reference

| Script | What it does | Who runs it | When |
|---|---|---|---|
| `run_backtest.sh` | Single backtest run | Claude Code | On demand / after strategy change |
| `autobacktest.py` | Automated parameter grid search | Claude Code | When strategy needs tuning |
| `parse_backtest.py` | Parse result JSON, print PASS/FAIL | auto (called by above) | Never run manually |
| `tune_stoploss.sh` | Multi-stoploss sweep (one-off) | Claude Code | Rarely — only if stoploss is specifically in question |
| `phase2/*.py` | External data fetchers | cron (not AI) | Every 15 min automatically |
| `phase4/setup_cron.sh` | Install Phase 4 cron job | Claude Code | Once only |
| `phase4/memory_writer.py` | Write vault entries + git commit | cron (not AI) | Every 15 min automatically |

---

## Task 1.3 — Automated Parameter Grid Search

### Background

Manual backtest iteration (run → fail → tweak → repeat) wastes AI tokens and time.
The `autobacktest.py` script encodes that loop as code, which is always cheaper and faster.

### How it works

1. Reads `autobacktest_grid.json` for the parameter grid and acceptance criteria.
2. For each combination:
   - Patches `FinBuddyFreqAI.py` with the test params.
   - Clears the FreqAI prediction cache (critical — avoids stale-cache false results).
   - Runs `run_backtest.sh`.
   - Parses metrics via `parse_backtest.py --json`.
   - Logs result to `_autobacktest_results.csv`.
3. Stops on the first combination that passes ALL acceptance criteria.
4. Restores `FinBuddyFreqAI.py` to its original state after every run.

### Acceptance criteria

| Metric | Must be |
|---|---|
| Win rate | > 50% |
| Sharpe ratio | > 0.5 |
| Max drawdown | < 20% |
| Profit factor | > 1.2 |

### Usage (Claude Code)

```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
git pull origin gaurav
python3 scripts/autobacktest.py
```

> ⚠️ This runs multiple backtests sequentially. Each takes ~5–15 minutes.
> Total runtime for a 12-combo grid: up to 3 hours. Run in a `tmux` session:
```bash
tmux new -s autobacktest
python3 scripts/autobacktest.py
# Ctrl+B then D to detach. Come back later with: tmux attach -t autobacktest
```

### Output

- `_autobacktest_results.csv` — all runs with full metrics (commit this)
- Stdout summary: PASS/FAIL per combo + winner if found

### After the run (Claude Code)

1. Commit `_autobacktest_results.csv` to `gaurav` branch.
2. If a winner was found: update `finbuddy_memory/strategies/winners.md` with params + metrics.
3. If no winner: update `finbuddy_memory/strategies/graveyard.md` and leave Task 1.3 as ⚠️.
4. Update `CLAUDE_HANDOFF.md` with outcome.

### After the run (Perplexity)

1. Read `_autobacktest_results.csv`.
2. If winner: apply those params permanently to `FinBuddyFreqAI.py` and mark Task 1.3 ✅.
3. If no winner: expand the grid in `autobacktest_grid.json` or redesign the approach.

### Modifying the parameter grid

Edit `autobacktest_grid.json` — never edit `autobacktest.py` to change params.

```json
"grid": {
  "ml_threshold": [0.009, 0.010, 0.011],
  "trend_ema_period_1h": [20, 35],
  "rsi_entry_ceiling": [68, 72]
}
```

Add or remove values freely. Perplexity is responsible for setting this grid
based on backtest analysis.

---

## Task 1.3 — Single Backtest Run

### Usage

```bash
cd /home/ubuntu/var/www/html/trade/freqtrade
chmod +x scripts/run_backtest.sh
./scripts/run_backtest.sh
```

### What it does

1. Pre-flight checks (verifies required strategy + model files exist).
2. Downloads historical data (BTC, ETH, SOL, BNB, XRP — 15m + 5m + 1h, Jan 2025–Apr 2026).
3. Runs walk-forward backtest inside Docker.
4. Calls `parse_backtest.py` and prints PASS/FAIL.

> Use `autobacktest.py` for tuning. Use `run_backtest.sh` only for a single
> one-off validation run (e.g., after applying a winner from the grid search).

---

## Phase 2 — External Data Fetchers

> These run via cron every 15 min. Claude Code installs the cron once.
> Never call these manually in a loop — that is the cron’s job.

| File | Data Source | Features Added to FreqAI |
|---|---|---|
| `fetch_fear_greed.py` | Alternative.me | `ext_fear_greed`, regime, 7d trend |
| `fetch_coingecko.py` | CoinGecko | BTC dominance, mcap signal |
| `fetch_cryptopanic.py` | CryptoPanic | News sentiment, bull/bear ratio |
| `fetch_defillama.py` | DefiLlama | DeFi TVL, 24h/7d signal |
| `fetch_google_trends.py` | pytrends | BTC search interest, contrarian |
| `external_data_aggregator.py` | All 5 combined | `ext_composite_score` |

---

## Phase 4 — Memory Auto-Writer

> Runs via cron every 15 min after `setup_cron.sh` is installed once.

| File | Purpose |
|---|---|
| `memory_writer.py` | Reads FreqTrade API, writes vault entries, git commits |
| `setup_cron.sh` | One-time install of cron jobs |

---

*All scripts that interact with FreqTrade run inside the Docker container via `docker exec`.*
*Never run strategy-adjacent scripts directly on host Python.*

---
*← [[FINBUDDY_PROJECT_MEMORY]]*
