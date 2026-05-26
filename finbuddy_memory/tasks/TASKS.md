# FinBuddy — Master Task Index

> Execution roadmap for the FinBuddy autonomous AI brain.
> Each phase has its own file. Read `FINBUDDY_PROJECT_MEMORY.md` first for live state.
> Tasks within each phase are ordered — top to bottom unless marked [PARALLEL].

---

## Phase Overview

| Phase | File | Status | Description |
|---|---|---|---|
| 0 | [phase-0-foundation.md](phase-0-foundation.md) | ✅ Complete (2026-04-27) | Foundation — Docker, FreqTrade, Telegram |
| 1 | [phase-1-freqai-brain.md](phase-1-freqai-brain.md) | 🟢 LIVE — v23 dry-run, LT=1.2/ST=-0.8, 26 pairs, 339 exps, 0 promotions | FreqAI brain — `FinBuddyFreqAI_v23.py`, 15m TF, 26 pairs, LightGBMRegressor |
| 2 | [phase-2-data-enrichment.md](phase-2-data-enrichment.md) | ✅ Live (cron 15m) | Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends |
| 3 | [phase-3-hmm-regime.md](phase-3-hmm-regime.md) | ✅ Live (cron 4h) | 5-regime HMM engine |
| 4 | [phase-4-obsidian-memory.md](phase-4-obsidian-memory.md) | ✅ Live (cron 15m) | Auto-write + git auto-commit |
| 5 | [phase-5-karpathy-loop.md](phase-5-karpathy-loop.md) | ✅ Live (cron 02:00) | Nightly research loop — Gemini + DeepSeek |
| 6 | _phase-6 deleted_ | 🔴 Abandoned (2026-05-04) | TradingView dropped (paid plan required) |
| 7 | [phase-7-executor.md](phase-7-executor.md) | 🔴 Retired 2026-05-24 | executor_wrapper.sh deleted — dead Phase 7 prototype, consumed CPU for nothing |
| 8 | [phase-8-futures-setup.md](phase-8-futures-setup.md) | ✅ Complete (2026-05-05) | Binance USDT-M, isolated margin |
| 9 | [phase-9-futures-risk.md](phase-9-futures-risk.md) | ✅ Complete (2026-05-09) | Regime-aware sizing, cluster cap, funding guard |
| 10 | [phase-10-live-migration.md](phase-10-live-migration.md) | ⛔ BLOCKED | Real-capital migration — needs WF PASS or 60-day track record |
| 11 | [phase-11-self-evolution.md](phase-11-self-evolution.md) | ✅ Live | RS metrics + dynamic regime sizing in strategy |
| 12 | [phase-12-brain-dashboard.md](phase-12-brain-dashboard.md) | ✅ v1 Complete · 🟡 v2 IN PROGRESS | React SPA dashboard |
| 12b | [phase-12b-dashboard-v2.md](phase-12b-dashboard-v2.md) | 🟡 IN PROGRESS (started 2026-05-24) | Dashboard v2 — professional trading console: 7 tabs, FreqTrade UI mirror, System Health, Brain/WF views, auth |
| 13 | [phase-13-conscious-brain.md](phase-13-conscious-brain.md) | 🟢 OPERATIONAL | Autonomous hypothesis engine — brain runs every 10m |
| **14** | **[phase-14-10usdt-daily.md](phase-14-10usdt-daily.md)** | **🟡 IN PROGRESS — P0–P2 done, P3 next** | **Path to 10 USDT/day — brain fixes + OI feature + leverage tuning** |

---

## 🚨 Current Focus (2026-05-27)

**Active strategy:** `FinBuddyFreqAI_v23.py` — v23 live, **26 pairs**, 15m TF, LightGBMRegressor  
**Identifier:** `finbuddy_v23_no_median_1779447827`  
**Live thresholds:** LT=1.2 / ST=-0.8 (asymmetric — compensates for model mean bias)  
**Wallet:** 1000 USDT dry-run. Regime: **BEAR 80%**.

**Brain state (2026-05-27):**
- 339 completed, 108 failed, **140 queued** (66 bear-window entries at front)
- 0 promotions fired — first expected within Days 1-5
- Hypothesis space: num_leaves [15,31,63,127], learning_rate [0.01,0.03,0.05] ✅
- btc_ls_ratio feature in strategy ✅, n_estimators=100 in brain ✅
- Cross-window auto-queue active ✅, regime-sort auto-trigger in runner ✅

**All immediate items done:**
- ✅ P0.1: Brain parallel split (reverted 2026-05-24); single-group working
- ✅ P0.2: WF fold timeout fixed
- ✅ P1: Circuit breaker 10 USDT/day
- ✅ P2.1-P2.3: WR gate, SEED thresholds, multiplier cap
- ✅ btc_ls_ratio: already in strategy
- ✅ num_leaves/learning_rate: already in brain
- ✅ Regime-seeding: seed-regime command + auto-trigger

**Next actions:**
- ⬜ Days 1-2: bear configs run → first bear pass → cross-window auto-queue fires
- ⬜ Day 2: n_estimators A/B gate check (n=100 vs n=200 cohort Sharpe)
- ⬜ Days 3-5: ≥2 bull + ≥2 bear → scan fires → Telegram Apply
- ⬜ Future: historical parquets for market_cap_change_24h, news_sentiment, btc_dominance

**Walk-forward:**
- Daily @ 22:00 UTC — 1 fold, 4mo train + 1mo test (~3.5h)
- Deep @ 18:30 UTC every 4 days — **7 folds**, **18mo window**, --cpu-shares 256 (~35h)

---

## Rules for Claude Code Working on These Tasks

1. Read `FINBUDDY_PROJECT_MEMORY.md` first — master hub
2. Read `CLAUDE_HANDOFF.md` for current live state + dead-things list
3. Read the relevant phase file before changes
4. All new code goes in `freqtrade/user_data/` or `scripts/`
5. Auto-updated files (`finbuddy_memory/regimes/*`, `trades/*`, `research/*-nightly.md`, `CONTEXT.md`) — never edit manually
6. Strategy changes require backtest validation (brain or manual)
7. Mobile-debuggable — keep it simple
8. **Update phase file status + this index together at end of every session**
9. Hard cost ceiling: $3–5/month
10. Never pile session notes into `CLAUDE.md` — use phase files or `CLAUDE_HANDOFF.md`

---

## Overall Progress

```
Phases Complete:     6 / 14  (Phases 0, 8, 9, 11, 12 + Phase 14 P0-P2)
Phases Live (cron):  6 / 14  (Phases 2, 3, 4, 5, 7, 13)
Phases In Progress:  2 / 14  (Phase 1 — v23 live; Phase 14 — 10 USDT/day roadmap)
Phases Blocked:      1 / 14  (Phase 10 — needs WF PASS or 60-day track record)
Phases Abandoned:    1 / 14  (Phase 6 — TradingView)
```

---

## 🔗 Related Files
- [[CLAUDE]] ← operational context
- [[FINBUDDY_PROJECT_MEMORY]] ← master hub
- [[CLAUDE_HANDOFF]] ← current live state + dead-things list
- [[COLLABORATION_CONTRACT]] ← roles, automation principles
- [[CONTEXT]] ← live context injected into AI prompts
- [[current]] ← live regime snapshot
- [[strategies/graveyard]] ← retired strategies + historical backtests
