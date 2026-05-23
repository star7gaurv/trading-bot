# FinBuddy — Master Task Index

> Execution roadmap for the FinBuddy autonomous AI brain.
> Each phase has its own file. Read `FINBUDDY_PROJECT_MEMORY.md` first for live state.
> Tasks within each phase are ordered — top to bottom unless marked [PARALLEL].

---

## Phase Overview

| Phase | File | Status | Description |
|---|---|---|---|
| 0 | [phase-0-foundation.md](phase-0-foundation.md) | ✅ Complete (2026-04-27) | Foundation — Docker, FreqTrade, Telegram |
| 1 | [phase-1-freqai-brain.md](phase-1-freqai-brain.md) | 🟢 LIVE — v23 dry-run +97 USDT, WR 38.6% | FreqAI brain — `FinBuddyFreqAI_v23.py`, 15m TF, 37 pairs, LightGBMRegressor |
| 2 | [phase-2-data-enrichment.md](phase-2-data-enrichment.md) | ✅ Live (cron 15m) | Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends |
| 3 | [phase-3-hmm-regime.md](phase-3-hmm-regime.md) | ✅ Live (cron 4h) | 5-regime HMM engine |
| 4 | [phase-4-obsidian-memory.md](phase-4-obsidian-memory.md) | ✅ Live (cron 15m) | Auto-write + git auto-commit |
| 5 | [phase-5-karpathy-loop.md](phase-5-karpathy-loop.md) | ✅ Live (cron 02:00) | Nightly research loop — Gemini + DeepSeek |
| 6 | _phase-6 deleted_ | 🔴 Abandoned (2026-05-04) | TradingView dropped (paid plan required) |
| 7 | [phase-7-executor.md](phase-7-executor.md) | ✅ Live (cron 5m) | Python signal executor (paper mode) |
| 8 | [phase-8-futures-setup.md](phase-8-futures-setup.md) | ✅ Complete (2026-05-05) | Binance USDT-M, isolated margin |
| 9 | [phase-9-futures-risk.md](phase-9-futures-risk.md) | ✅ Complete (2026-05-09) | Regime-aware sizing, cluster cap, funding guard |
| 10 | [phase-10-live-migration.md](phase-10-live-migration.md) | ⛔ BLOCKED | Real-capital migration — needs WF PASS or 60-day track record |
| 11 | [phase-11-self-evolution.md](phase-11-self-evolution.md) | ✅ Live | RS metrics + dynamic regime sizing in strategy |
| 12 | [phase-12-brain-dashboard.md](phase-12-brain-dashboard.md) | ✅ Complete | React SPA dashboard |
| 13 | [phase-13-conscious-brain.md](phase-13-conscious-brain.md) | 🟢 OPERATIONAL | Autonomous hypothesis engine — brain runs every 10m |
| **14** | **[phase-14-10usdt-daily.md](phase-14-10usdt-daily.md)** | **🟡 IN PROGRESS — P0–P2 done, P3 next** | **Path to 10 USDT/day — brain fixes + OI feature + leverage tuning** |

---

## 🚨 Current Focus (2026-05-23)

**Active strategy:** `FinBuddyFreqAI_v23.py` — v23 live, 37 pairs, 15m TF, LightGBMRegressor  
**Identifier:** `finbuddy_v23_no_median_1779447827`  
**Wallet:** 1000 USDT dry-run. P&L: +97 USDT. WR: 38.6%. Target: 10 USDT/day.

**Phase 14 progress (P0–P2 shipped, P3 next):**
- ✅ P0.1: Brain parallel pair-group split — experiments completing again (was 100% timeout)
- ✅ P0.2: WF fold timeout 4.5h → 6h — real fold results expected tonight 22:00 UTC
- ✅ P1: Daily circuit breaker 10 USDT — prevents -26 USDT loss days
- ✅ P2.1: Brain WR gate ≥50% — only consistent configs promoted
- ✅ P2.2: Asymmetric SEED short=-0.8 — brain explores better shorts first
- ✅ P2.3: Combined multiplier cap 2.0× — prevents 0-trade days in BEAR+bad WR
- ⬜ P3.1: Open Interest Delta feature — `build_historical_oi.py` + strategy + identifier bump
- ⬜ P3.2: Leverage tier tuning — MED_CONF 1.5→1.7, HIGH_CONF 2.0→2.5

**Brain state:**
- 268+ experiments — all excluded from promotion (legacy raw-% target, wrong label semantics)
- Now exploring z-scored hypothesis space with correct windows + parallel pair split
- Seed: long_threshold=1.5, short_threshold=-0.8, windows: bull_2024Q1/Q2, bear_2025Q1, bull_2025Q4, bear_2026Q1
- First promotion: needs ≥2 bull + ≥2 bear z-scored experiments passing WR ≥ 50% gate

**Walk-forward:**
- Daily @ 22:00 UTC (9mo window, 3 folds, 2 workers, ~8-10h with 6h/fold timeout)
- Deep @ 03:00 UTC every 4 days (27mo, 21 folds)
- All folds were timing out until P0.2 fix — first real results tonight

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
- [[regimes/current]] ← live regime snapshot
- [[strategies/graveyard]] ← retired strategies + historical backtests
