# Phase 14 — Path to 10 USDT/Day

**Goal:** Earn 10 USDT/day on the existing 1000 USDT dry-run wallet — NOT by adding capital.  
**Why 10 USDT/day:** = 1%/day = 365%/year. Once proven in dry-run, deploy ~$700 real capital → ~7 USDT/day real.  
**Current rate:** ~3.3 USDT/day (38.6% WR, 334 trades, +97 USDT since ~2026-04-04)  
**Status:** 🟢 P0–P2 shipped (commit `8bede56` + `aba9e4d`, 2026-05-23). P3–P4 pending.  
**Last Updated:** 2026-05-23

---

## The Math

| Scenario | WR | Trades/Day | Daily P&L | vs Target |
|---|---|---|---|---|
| **Current** | 38.6% | ~10 | ~3.3 USDT | 33% |
| WR → 50% | 50.0% | ~10 | ~6.0 USDT | 60% |
| WR → 55% | 55.0% | ~10 | ~8.5 USDT | 85% |
| WR 55% + avg leverage 2.5× | 55.0% | ~10 | **~10.6 USDT** | **✅ TARGET** |

---

## Task Status

### P0 — Unblock Brain + Walk-Forward ✅ DONE

| Task | File | Status | Commit |
|---|---|---|---|
| P0.1 Brain parallel pair-group split | `scripts/brain/runner.py` | ✅ Done | `8bede56` |
| P0.2 WF fold timeout 4.5h → 6h | `scripts/walk_forward.py` | ✅ Done | `8bede56` |

**P0.1 detail:** 37-pair sequential experiment = ~74 min > 65-min timeout = 100% failure rate.  
Fix: split into 2 groups of ~18-19, run via `ThreadPoolExecutor(max_workers=2)`. Each group ~38 min.  
All 37 pairs still evaluated per experiment. Helpers: `_load_brain_pairs`, `_create_pair_group_config`, `_parse_raw_trades_from_zip`, `_compute_metrics_from_raw_trades`, `_build_env_args`, `_run_hypothesis_group`.  
Partial-success path: if one group fails, single-group result logged instead of FAILED.

**P0.2 detail:** fold_03 was actively backtesting (training done) when killed at 4.5h — only 30 min from finishing.  
Fix: `timeout=16200` → `21600`. Daily WF now 22:00 → ~08:00 UTC. First real results tonight 2026-05-23.

---

### P1 — Daily Circuit Breaker ✅ DONE

| Task | File | Status | Commit |
|---|---|---|---|
| P1 Daily loss limit 10 USDT | `FinBuddyFreqAI_v23.py`, `.env`, `docker-compose.yml` | ✅ Done | `8bede56` + `aba9e4d` |

**Detail:** May 14 was -26.53 USDT, May 21 was -14.44 USDT. Both would have been capped at -10.  
`custom_stake_amount()` reads `FREQAI_DAILY_LOSS_LIMIT=10` from env (default 10 USDT).  
Blocks new entries when today's UTC closed P&L < -10 USDT.  
`.env` updated. `docker-compose.yml` `environment:` block updated (vars must be explicitly listed — not auto-picked from `.env`). Verified: `docker exec freqtrade env | grep FREQAI_DAILY_LOSS_LIMIT` = `10`.

---

### P2 — Brain Quality Improvements ✅ DONE

| Task | File | Status | Commit |
|---|---|---|---|
| P2.1 Brain WR gate ≥50% | `scripts/brain/promote.py` | ✅ Done | `8bede56` |
| P2.2 Asymmetric SEED short=-0.8 | `scripts/brain/hypothesis_gen.py` | ✅ Done | `8bede56` |
| P2.3 Cap combined multiplier at 2.0× | `FinBuddyFreqAI_v23.py` | ✅ Done | `8bede56` |

**P2.1 detail:** `find_candidates()` now requires ≥1 bull run AND ≥1 bear run with WR ≥ 50%.  
**P2.2 detail:** `SEED_CONFIG_V23["short_threshold"]` -1.5 → -0.8. LONG WR=57%, SHORT WR=34% — brain explores tighter shorts first.  
**P2.3 detail:** BEAR(×1.3) × WR_adj(×1.26 at 42% WR) was compounding to ×1.638 → long threshold = 0.819. EMA-50 filter also fails in confirmed BEAR → 0 trades. Fix: `(long_mult_series * wr_adj).clip(upper=2.0)`.

---

### P3 — Signal Quality Improvements ⬜ NEXT

#### P3.1 — Open Interest Delta Feature
**Why:** Second-best published signal for futures direction after funding rate. Adds model edge.  
**Files to create/edit:**
- **New:** `scripts/build_historical_oi.py` — mirrors `build_historical_funding.py` structure
  - Binance endpoint: `/fapi/v1/openInterestHist` (public, no key needed)
  - 3 features: `%-oi_delta` (5-candle % change), `%-oi_z30d` (30-day z-score), `%-oi_chg` (1-candle % change)
  - Output: `freqtrade/user_data/data/oi_history.parquet`
  - Add cron: `30 1 * * *` (5 min after funding rate refresh at 01:25)
- **Edit:** `freqtrade/user_data/strategies/FinBuddyFreqAI_v23.py`
  - In `feature_engineering_standard_v23()` near funding rate features
  - Load `oi_history.parquet`, merge on timestamp, forward-fill
  - Add 3 OI features to feature set

**After adding OI — REQUIRED STEPS:**
1. Bump FreqAI identifier: `finbuddy_v23_oi_{int(time.time())}`
2. Flush `freqtrade/user_data/models/finbuddy_v23*/historic_predictions.pkl` (see `reference_feature_added_recovery.md`)
3. `docker-compose up -d freqtrade`

#### P3.2 — Leverage Tier Tuning
**Why:** Avg leverage ~2.0×. Increasing to ~2.5× on conviction trades adds ~25% to per-trade size without changing WR.  
**File:** `freqtrade/.env` — update two vars, then `docker-compose up -d freqtrade`:
```
FREQAI_LEV_MED_CONF_RATIO=1.7    # was 1.5 — slightly tighter bar for 2× leverage
FREQAI_LEV_HIGH_CONF_RATIO=2.5   # was 2.0 — higher bar for 3× leverage
```
Also update `docker-compose.yml` environment block defaults to match.

---

### P4 — Phase 10 Prep ⬜ DEFERRED (when WR ≥ 50% sustained)

| Task | File | Status |
|---|---|---|
| P4.1 Pass/fail dry-run report | `scripts/dry_run_report.py` | ⬜ Not started |
| P4.2 Kill switch | `scripts/kill_switch.sh` | ⬜ Not started |
| P4.3 Live config | `freqtrade/user_data/futures_live_config.json` | ⬜ Not started |

**Phase 10 gate criteria current status:**

| Criterion | Required | Current | Status |
|---|---|---|---|
| Win Rate | > 50% | 38.6% | ❌ main target |
| Profit Factor | > 1.1 | 1.37 | ✅ |
| Max Drawdown | < 15% | ~3.2% | ✅ |
| 60-day track record | needed | ~49 days | ⚠️ close |

---

## Milestones

| When | Milestone |
|---|---|
| **Tonight 22:00 UTC** | WF fold timeout fix → first valid WF results (fold_03 was 30 min from done) |
| **Tomorrow** | Brain parallel split → first completed z-scored experiments (not FAILED) |
| **3 days** | Brain accumulates 30+ z-scored experiments with correct timeout |
| **1 week** | Brain promotes first z-scored config with WR ≥ 50% → live threshold improves |
| **2 weeks** | OI feature adds edge. Daily P&L averaging ≥ 6 USDT/day |
| **4 weeks** | WR → 55%. Daily P&L ≥ 10 USDT/day |
| **After target** | Real capital: ~$700 → ~$7/day real money |

---

## Implementation Constraints (non-negotiable)

- Keep `dry_run_wallet: 1000 USDT` — do NOT change
- Do NOT manually change live `LONG_THRESHOLD`/`SHORT_THRESHOLD` in `.env` — brain promotes them
- Never use `sed` on JSON — always `python3 -c "import json; ..."`
- Always bump FreqAI identifier + flush `historic_predictions.pkl` when changing feature set
- Always `docker-compose up -d` (not `restart`) after `.env` or `docker-compose.yml` changes
- Never hardcode secrets — all credentials via `config.json` lookup
- Brain config (`v23_regression_15m_di_config.json`) and live config (`config.json`) are SEPARATE

---

## Daily Check Commands

```bash
# P&L + WR + trades
curl -s -u bot:REDACTED-FREQTRADE__API_SERVER__PASSWORD http://localhost:8080/api/v1/profit | python3 -c "
import json,sys; d=json.load(sys.stdin); tc=max(d.get('trade_count') or 1,1)
print(f'P&L: +{d[\"profit_closed_coin\"]:.2f} USDT | WR: {d[\"winning_trades\"]*100/tc:.0f}% | PF: {d[\"profit_factor\"]:.2f} | Trades: {tc}')
"

# Brain: check if any experiments completed (not FAILED)
tail -20 /home/ubuntu/.finbuddy/logs/brain_run.log | grep -E "completed|FAILED|running"

# WF: check if tonight's fold results arrived
ls -lt /home/ubuntu/var/www/html/trade/walkforward_results/ | head -3
cat /home/ubuntu/var/www/html/trade/walkforward_results/$(ls -t /home/ubuntu/var/www/html/trade/walkforward_results/ | head -1)/summary.json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('PASS' if d.get('pass') else 'FAIL', d.get('verdict',''))"
```
