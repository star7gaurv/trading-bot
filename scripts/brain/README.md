# FinBuddy Brain — Operator Cheatsheet

The autonomous hypothesis engine. Runs by itself on cron. You only intervene to **approve promotions**.

## TL;DR

```bash
cd /home/ubuntu/var/www/html/trade
python3 scripts/brain/brain_cli.py status     # see queue + best so far
python3 scripts/brain/brain_cli.py best       # show the current winner
python3 scripts/brain/brain_cli.py scan       # check for promotion candidates now
```

## Autonomous Cron (already installed)

```
*/30 * * * *   brain_cli.py run --max 1        # run 1 experiment every 30 min (~48/day)
0    */6 * * *  brain_cli.py generate          # generate 4 safe + 6 aggressive variants × 3 windows = ~30 new hypotheses, 4× daily
0    7 * * *    brain_cli.py scan              # daily candidate scan + Telegram alert
```

Logs at `~/.finbuddy/logs/brain_{run,gen,scan}.log`. Lock file at `~/.finbuddy/state/brain_runner.lock` prevents overlap.

## What the brain does on its own

1. **Generates hypotheses** in two bands:
   - **SAFE**: small perturbations around the current best (±0.25 on thresholds, ±1 on stability, etc.)
   - **AGGRESSIVE**: random sample from full param space (timeframe × thresholds × K_SL × K_TP × stability × label period × DI filter × SVM filter)
2. **Queues** them in `finbuddy_memory/experiments/queue.jsonl`
3. **Runs** one per 30 min: spawns isolated docker-compose backtest with env var overrides, parses metrics
4. **Logs** every result to `finbuddy_memory/experiments/log.jsonl` (queryable)
5. **Telegrams** each result with profit/WR/Sharpe/L+S counts
6. **Scans daily** for configs that beat baseline on bull+bear → Telegram alert with `--apply` command

## What YOU do (the only human intervention)

When Telegram fires `🧠 Brain Promotion Candidate`:

```bash
# Read the proposal
cat finbuddy_memory/promotions/pending.json

# If you like it
python3 scripts/brain/promote.py --apply <config_hash>
```

The `--apply` command currently prints instructions (manual config edit + restart) for safety. Once the brain has 3+ successful promotions you trust, this can be flipped to fully automated.

## Useful Queries

```bash
# Best by profit (most promising configs)
python3 scripts/brain/brain_cli.py best

# Count completed by band
python3 -c "import sys; sys.path.insert(0, 'scripts/brain'); from experiment_log import read_log; \
  d={}; [d.update({r['band']:d.get(r['band'],0)+1}) for r in read_log() if r['status']=='completed']; print(d)"

# Top 5 configs by profit on bear window
python3 -c "
import sys, json
sys.path.insert(0, 'scripts/brain')
from experiment_log import read_log
log = [r for r in read_log() if r.get('status')=='completed' and r.get('metrics') and 'bear' in r.get('window','')]
log.sort(key=lambda r: r['metrics']['profit_pct'], reverse=True)
for r in log[:5]:
    m=r['metrics']; print(f\"{r['hypothesis_id']} profit={m['profit_pct']}% WR={m['wr']*100:.1f}% L/S={m['long_count']}/{m['short_count']} | {r['rationale']}\")
"

# Force a generate cycle (if queue is depleted)
python3 scripts/brain/brain_cli.py generate --safe 8 --aggr 12

# Force a candidate scan (Telegram if found)
python3 scripts/brain/brain_cli.py scan
```

## Profit Targets (at $800 wallet)

| Net %/mo | $/mo | Verdict |
|---|---|---|
| < 0.5% | < $4 | strategy broken — investigate, don't deploy |
| 0.5–1.5% | $4–$12 | barely viable |
| 1.5–3% | $12–$24 | acceptable / matches live v22 today |
| 3–5% | $24–$40 | strong — Phase 10 candidate |
| > 5% | > $40 | suspicious — backtest overfit? walk-forward gate next |

## Promotion Criteria (hardcoded in `promote.py`)

A candidate must pass ALL:
- ✅ Completed on ≥1 bull window AND ≥1 bear window
- ✅ profit_pct > 0 on BOTH bull AND bear
- ✅ sharpe > 0 on BOTH (averaged across runs)
- ✅ total trades ≥ 30 across all evaluated windows
- ✅ avg_profit ≥ LIVE_BASELINE_PROFIT_PCT + 1.0pp

Raise these thresholds in `promote.py` as the brain matures.

## Files

| Path | Contents |
|---|---|
| `finbuddy_memory/experiments/log.jsonl` | every completed/failed experiment (append-only) |
| `finbuddy_memory/experiments/queue.jsonl` | pending hypotheses (FIFO) |
| `finbuddy_memory/promotions/pending.json` | candidate awaiting your approval |
| `finbuddy_memory/promotions/applied_*.json` | promotion history (archived after `--apply`) |
| `backtests/brain_<id>.log` | per-experiment FreqTrade log |
| `~/.finbuddy/logs/brain_*.log` | cron output |

## Kill Switch

If the brain misbehaves:

```bash
# Disable cron (still keeps the queue intact)
crontab -e   # comment out the brain_cli.py lines

# Or kill any in-flight backtest
docker ps --filter "name=freqtrade-freqtrade-run" --format "{{.Names}}" | xargs -r docker stop

# Force-release lock if stale
rm /home/ubuntu/.finbuddy/state/brain_runner.lock
```

The live v22 bot is in a separate container (`freqtrade`) and is NEVER touched by the brain.
