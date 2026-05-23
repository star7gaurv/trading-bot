# Pair Expansion Runbook

> Saved 2026-05-20. Use this every time we add pairs so it stays bug-free. Currently at 25 pairs; target +12 → 37.

## Why this runbook exists

Adding pairs to FinBuddy is mechanical but multi-step. Skip a step and you hit one of: pipeline schema mismatch, NaN training crash, brain↔live config drift, cluster-cap distortion, walk-forward timeout, or stale per-pair-regime stats. Each of those has cost us hours this week. This runbook captures the **9 required steps** in order.

---

## Pre-flight gate

🛑 **Do NOT add pairs while a walk-forward is running.** Wait for the in-flight WF to complete and its result to land so the baseline isn't muddied. Check via:
```bash
pgrep -af walk_forward.py
ls -t walkforward_results/*/summary.json | head -1 | xargs cat
```
If `summary.json` was written in the last 6h and shows the latest commit-stack's metrics, you're good.

---

## Per-pair data requirements (the answer to "why 5 timeframes")

Each pair needs ALL FIVE feather files downloaded back to **at least 2024-01-01** (so 6-month-train WF folds have room):

| TF | Used for | Required |
|---|---|---|
| `15m` | Base TF — model trains + predicts on this | ✅ mandatory |
| `30m` | Legacy / brain ablation TFs | ✅ mandatory (download script grabs it) |
| `1h` | `include_timeframes[0]` — multi-TF features | ✅ mandatory |
| `4h` | `include_timeframes[1]` — multi-TF features | ✅ mandatory |
| `1d` | `build_historical_macro.py` uses BTC/ETH 1d for `%-btc_strength` | ✅ mandatory |
| `mark` (1h) | Funding mark price — futures only | 🤖 auto-fetched at runtime |
| `funding_rate` (1h) | Per-pair funding stream — futures only | 🤖 auto-fetched at runtime |

Verify after download: `ls freqtrade/user_data/data/binance/futures/<PAIR_NO_SLASH>-{15m,30m,1h,4h,1d}-futures.feather`

---

## The 9 steps

### 1. Wait for current WF
Already gated above. ETA tonight's manual WF (PID 3095719 started 13:21 UTC) completes by ~07:00 UTC 2026-05-21.

### 2. Verify each candidate against Binance Futures
For every new pair: `curl https://fapi.binance.com/fapi/v1/exchangeInfo` and confirm:
- `status == "TRADING"`
- `quoteAsset == "USDT"`, `contractType == "PERPETUAL"`
- `onboardDate` earlier than 2024-07-01 (needs ≥10 months of history)
- Leverage tier supports our max planned `_LEV_HIGH=3`

Save the verified list to `freqtrade/user_data/pair_candidates_<date>.json`.

### 3. Download all 5 TFs per new pair back to 2024-01-01
```bash
cd freqtrade && docker-compose run --rm freqtrade download-data \
  --timeframe 15m 30m 1h 4h 1d \
  --timerange 20240101- \
  --pairs <PAIR1> <PAIR2> ... \
  --trading-mode futures
```
After each pair: verify all 5 files present AND each has ≥10,000 rows (15m). Reject any pair where any TF missing or short.

### 4. Assign every new pair to a cluster
Edit `freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py` `_PAIR_CLUSTER` dict.

Current clusters: `MEGA_CAP`, `L2`. Recommended new clusters to add for diversification:
- `MEME` — SHIB, PEPE, WIF, DOGE-moved-here
- `AI` — FET, RNDR (Render), TAO-moved-here
- `DEFI` — AAVE, MKR, UNI-moved-here
- `L1_ALT` — INJ, HBAR, ATOM-moved-here
- `INFRA` — FIL

Keep `_MAX_CLUSTER_POSITIONS = 2`. With more clusters, total concurrent caps to `2 × N_clusters` (currently 4 → up to 14 once new clusters land), which still fits inside `max_open_trades=8`.

### 5. Add new pairs to BOTH configs (live + brain) atomically
Use python — never `sed` on JSON.

```python
import json
new_pairs = ["BNB/USDT:USDT", "MATIC/USDT:USDT", ...]
for path in ("freqtrade/user_data/config.json",
             "freqtrade/user_data/v23_regression_15m_di_config.json"):
    c = json.load(open(path))
    c["exchange"]["pair_whitelist"] = sorted(set(c["exchange"]["pair_whitelist"] + new_pairs))
    json.dump(c, open(path,"w"), indent=4)
# Verify alignment:
a = json.load(open("freqtrade/user_data/config.json"))["exchange"]["pair_whitelist"]
b = json.load(open("freqtrade/user_data/v23_regression_15m_di_config.json"))["exchange"]["pair_whitelist"]
assert a == b, "BRAIN ↔ LIVE pair_whitelist DRIFT — do not proceed"
```

Both must match after `5f37ab8` (round-3 audit Bug I).

### 6. Bump identifier + flush root cache + recreate container
Schema-equivalent change (new pairs, same features) but FreqAI persists pair-set state at the model-dir root. Skip this step and live bot throws `Pipeline expected ... but got ...`.

```bash
# 6a. Bump identifier
python3 -c "import json, time, pathlib
p = pathlib.Path('freqtrade/user_data/config.json')
c = json.loads(p.read_text())
c['freqai']['identifier'] = f'finbuddy_v23_pairs{len(c[\"exchange\"][\"pair_whitelist\"])}_{int(time.time())}'
p.write_text(json.dumps(c, indent=4))
print(c['freqai']['identifier'])"

# 6b. Stop + flush + recreate
cd freqtrade && docker-compose stop freqtrade
sudo rm -f user_data/models/{historic_predictions,historic_predictions.backup}.pkl \
           user_data/models/{pair_dictionary,run_params,global_metadata}.json
sudo rm -rf user_data/models/sub-train-*
docker-compose up -d freqtrade   # NOT just restart — must recreate
```

Reference: `reference_feature_added_recovery.md` + `reference_compose_env_reload.md`.

### 7. Smoke-test new pairs over 30 min
Within 30 min of recreate, verify each new pair:
1. Training completes — `docker logs freqtrade --since 30m | grep "Done training <PAIR>"` shows the pair
2. Strategy evaluates it — `docker logs freqtrade --since 5m | grep "<PAIR>"` shows pair-regime gate or inference logs
3. No exceptions — `docker logs freqtrade --since 30m | grep -iE "ERROR |Exception|Pipeline expected" | wc -l` is 0 (uvicorn.error INFO is OK noise)

Poll script:
```bash
for i in $(seq 1 30); do
  N=$(docker logs freqtrade --since 30m 2>&1 | grep -c "Done training")
  echo "$(date -u +%H:%M:%S)  pairs trained so far: $N / <target>"
  sleep 60
done
```

Pairs failing (1) or (3) — likely insufficient/corrupt data — must be REMOVED from both configs, identifier re-bumped, and steps 5-7 redone.

### 8. Re-bump WF per-fold timeout (linear scaling)
Each new pair adds ~6 min/fold of WF training. 25 pairs → 3h/fold; 37 pairs → ~4.5h/fold (~27h total run).

Edit `scripts/walk_forward.py`: `timeout=10800` → `timeout=16200` (4.5h).

Then test ONE manual WF run before the 22:00 cron picks it up:
```bash
./scripts/walkforward_daily.sh
```
Watch fold 1 to make sure it doesn't time out at the new threshold.

### 9. Commit + memory note
Single atomic commit listing every pair + cluster assignment. Update:
- `CLAUDE.md` — Whitelist count + cluster table
- `finbuddy_memory/FINBUDDY_PROJECT_MEMORY.md` — new session entry "Pair expansion <date>"
- `finbuddy_memory/CLAUDE_HANDOFF.md` — current state

---

## Sample first batch (12 pairs across 5 new clusters)

| Pair | Cluster | Onboard date (Binance Futures) | Notes |
|---|---|---|---|
| BNB/USDT:USDT | MEGA_CAP | 2020-02-10 | Top-5 by mcap |
| MATIC/USDT:USDT (POL) | L2 | 2020-10-22 | Renamed POL Sep-2024 |
| SHIB/USDT:USDT | MEME (new) | 2021-05-10 | |
| PEPE/USDT:USDT | MEME | 2023-05-05 | ⚠️ check ≥18mo data |
| WIF/USDT:USDT | MEME | 2023-12-04 | ⚠️ borderline — verify 2024-01-01 onward data |
| FET/USDT:USDT | AI (new) | 2021-03-08 | Now ASI alliance |
| RNDR/USDT:USDT (RENDER) | AI | 2022-03-25 | |
| AAVE/USDT:USDT | DEFI (new) | 2020-12-15 | |
| MKR/USDT:USDT | DEFI | 2022-01-29 | |
| INJ/USDT:USDT | L1_ALT (new) | 2021-11-04 | Cosmos-app L1 |
| HBAR/USDT:USDT | L1_ALT | 2022-04-08 | |
| FIL/USDT:USDT | INFRA (new) | 2020-10-22 | Storage |

Brings whitelist to **37 pairs across 7 clusters**. Cluster cap=2 per cluster = up to 14 concurrent open vs `max_open_trades=8` → max_open_trades remains the binding limit.

---

## Rollback procedure if smoke-test (step 7) fails

```bash
# Remove the bad pair from both configs
python3 -c "import json
for p in ('freqtrade/user_data/config.json',
         'freqtrade/user_data/v23_regression_15m_di_config.json'):
    c = json.load(open(p))
    c['exchange']['pair_whitelist'] = [x for x in c['exchange']['pair_whitelist'] if x != 'BAD_PAIR/USDT:USDT']
    json.dump(c, open(p,'w'), indent=4)"

# Restore the cluster dict edit
git checkout freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py

# Re-do steps 6 (identifier + flush + recreate)
```

---

## What this runbook explicitly does NOT do

- **Does not modify** `max_open_trades`, `dry_run_wallet`, `freqai.feature_parameters` — those are tuning decisions, not pair-list mechanics.
- **Does not auto-update** the brain's analyst report — analyst will pick up new pairs over the next 6h cycle naturally.
- **Does not delete** the legacy 265 brain experiments from `log.jsonl` — they're marked via `live_baseline.json::config_aligned_at`.

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
