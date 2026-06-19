# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-06-19 UTC (meta-labeling NO-GO confirmed; brain window names made honest; dashboard pagination root-caused)
**Branch:** `master`

---

## ✅ Current Live State (verified 2026-06-19)

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, z-scored target) |
| FreqAI identifier | `finbuddy_v23_nosvm_1780729988` |
| Pairs | **26** |
| Leverage | Confidence-based tiers 1×/2×/3× (FALLBACK = 1×) |
| Regime | **BEAR (80% confidence)** — market genuinely falling (BTC ≈ −15% this month) |
| Wallet | **1000 USDT** dry-run | max_open_trades **8** |
| Bot status | ✅ Up, untouched all session — frozen baseline running clean |
| DI / SVM | **DI_threshold=0, SVM disabled** (do_predict bug fix 2026-06-06) |
| Daily circuit breaker | ✅ FREQAI_DAILY_LOSS_LIMIT=10 |

**Live env vars (`freqtrade/.env`) — current:**
```
FREQAI_LONG_THRESHOLD=0.7      # RAISED 2026-06-17 (was 0.3) — Phase-1 stop-the-bleed
FREQAI_SHORT_THRESHOLD=-0.6    # asymmetric: longs are the worse side
FREQAI_K_TP=3.0
FREQAI_K_SL=2.0
FREQAI_STABILITY_N=1
FREQAI_LABEL_CANDLES=12
FREQAI_DAILY_LOSS_LIMIT=10
FREQAI_REENTRY_COOLDOWN_CANDLES=8
FREQAI_DAILY_FLATTEN_MULT=1.5
FINBUDDY_RECENT_WR=0.4
```

⚠️ `docker-compose.yml` has an explicit `environment:` block — every new `.env` var MUST also be added there. `docker-compose restart` does NOT reload `.env` — always `docker-compose up -d freqtrade`.

⚠️ **DO NOT TUNE / PROMOTE LIVE** until the honest brain beats the frozen baseline.
Baseline recorded in `finbuddy_memory/FROZEN_BASELINE_2026-06-17.md`.

---

## 📊 Live Performance (2026-06-19)

| Metric | Value |
|---|---|
| Closed trades | **752** |
| Total P&L | **+17.6 USDT** (≈breakeven; all gains came from one week in May, every week since loses) |
| Win rate | **41%** |
| Currently short-only | Correct behavior — regime is BEAR; hard regime gate blocks longs in down-markets (NOT a bug) |

**The diagnosis that matters:** the EXIT is genuine alpha (exit_signal exits ~90% WR), the ENTRY
is a coin flip (IC≈0). Stop-loss exits almost exactly cancel the exit-signal gains. Per-trade
expectancy is negative; profit is monotonic in trade count. See [[FROZEN_BASELINE_2026-06-17]].

---

## 🧠 Brain State (2026-06-19)

| Item | Value |
|---|---|
| Log entries | **1,865** (534 completed, 1,156 scout_failed, 175 failed) |
| profit>0 runs | **101** (all noise — avg ~45 trades, PF~1.1; killed by honest-brain gates) |
| Queue depth | **0** |
| Promotions fired | **0** that survive (the 2026-05-28 LT=3.25 promotion was reverted; it manufactured the bleed) |
| Honest-brain gates (2026-06-17) | scout: trades≥40 & PF>1.0 ; promote: MIN_TRADES=150, MIN_PF=1.1, MIN_BULL=2, MIN_BEAR=1, BEAR_2026Q1 WR≥50% |
| Test windows (HONEST names 2026-06-19) | bull_2024Q1 (+68%), bull_2024Q4 (+47%), bull_2021, bear_2024Q2 (−11%), bear_2025Q1 (−12%), bear_2025Q4 (−23%), bear_2026Q1 (−22%), crash_2022 (stress) |
| PAIRED rotation | bull_2024Q1 → bear_2025Q1 → bull_2024Q4 → bear_2026Q1 (2:2, all genuine) |

⚠️ **Queue race:** the cron queue silently drops entries under concurrent rewrite (hit 3× on
2026-06-19). To run a specific config reliably, bypass the queue: `runner.run_hypothesis(h)` with
an explicit dict needing keys `config` + `window` + `timerange` (from `hypothesis_gen.WINDOWS[window]`),
holding `runner._acquire_lock()`. Run helper scripts from the repo dir, NOT /tmp (a stray
`/tmp/inspect.py` shadows the stdlib).

---

## 🎯 What's Next — the only remaining lever is ENTRY SIGNAL QUALITY

Every cheap fix is now exhausted and ALL point the same way (entry signal has no edge):
threshold tuning, quantile entry mode, feature pruning, sample weighting, **and meta-labeling
(NO-GO 2026-06-19 — tightening the meta filter made the stop-loss rate WORSE, not better)**.

**→ Phase 4: build genuinely NEW entry-time features** (order-flow imbalance, OI-delta/CVD,
funding/basis, cross-asset lead-lag — signals the model currently cannot see). Per Gaurav:
**research & scope first, bring a plan, get approval BEFORE writing code.** Not yet started.

Meta-labeling code stays in the tree, `FREQAI_META_LABEL=0` (live byte-identical).

### Open / deferred
- Historical experiment log has ~800 entries under the OLD window names (bull_2024Q2/bull_2025Q4)
  — promote.py substring-counts them as "bull". Left immutable (ledger). Low impact (strict gates,
  nothing promoted). Optional clean: old→new name-normalization in promote.py's log reader.
- Dashboard pagination: root cause was nginx serving `index.html` with no cache header (browser
  kept stale JS). Fixed (no-cache HTML, immutable assets). One hard-refresh needed once. See
  auto-memory `reference_dashboard_deploy.md`.

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[FROZEN_BASELINE_2026-06-17]] · [[CONTEXT]]*
