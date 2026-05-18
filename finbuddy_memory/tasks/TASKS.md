# FinBuddy — Master Task Index

> Execution roadmap for the FinBuddy autonomous AI brain.
> Each phase has its own file. Read `FINBUDDY_PROJECT_MEMORY.md` first for live state.
> Tasks within each phase are ordered — top to bottom unless marked [PARALLEL].

---

## Phase Overview

| Phase | File | Status | Description |
|---|---|---|---|
| 0 | [phase-0-foundation.md](phase-0-foundation.md) | ✅ Complete (2026-04-27) | Foundation — Docker, FreqTrade, Telegram |
| 1 | [phase-1-freqai-brain.md](phase-1-freqai-brain.md) | 🟢 LIVE — v22 dry-run +$107 | FreqAI brain — `FinBuddyFreqAI` v22, 1h TF, 25 pairs, 2x leverage |
| 2 | [phase-2-data-enrichment.md](phase-2-data-enrichment.md) | ✅ Live (cron) | Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends |
| 3 | [phase-3-hmm-regime.md](phase-3-hmm-regime.md) | ✅ Live (cron 4h) | 5-regime HMM engine |
| 4 | [phase-4-obsidian-memory.md](phase-4-obsidian-memory.md) | ✅ Live (cron 15m) | Auto-write + git auto-commit |
| 5 | [phase-5-karpathy-loop.md](phase-5-karpathy-loop.md) | ✅ Live (cron 02:00) | Nightly research loop — Gemini + DeepSeek |
| 6 | _phase-6 deleted_ | 🔴 Abandoned (2026-05-04) | TradingView dropped (paid plan required) |
| 7 | [phase-7-executor.md](phase-7-executor.md) | ✅ Live (cron 5m) | Python signal executor (paper mode) |
| 8 | [phase-8-futures-setup.md](phase-8-futures-setup.md) | ✅ Complete (2026-05-05) | Binance USDT-M, isolated margin |
| 9 | [phase-9-futures-risk.md](phase-9-futures-risk.md) | ✅ Complete (2026-05-05) | Regime-aware sizing, cluster cap, funding guard |
| 10 | [phase-10-live-migration.md](phase-10-live-migration.md) | ⛔ BLOCKED | Real-capital migration — waiting for brain-promoted variant OR 60-day track record |
| 11 | [phase-11-self-evolution.md](phase-11-self-evolution.md) | ✅ Live | RS metrics + dynamic regime sizing in strategy |
| 12 | [phase-12-brain-dashboard.md](phase-12-brain-dashboard.md) | ✅ Complete | React SPA dashboard (dashboard-ui/, dashboard/streamer.py) |
| 13 | [phase-13-conscious-brain.md](phase-13-conscious-brain.md) | 🟢 OPERATIONAL | Autonomous hypothesis engine — 4/4 pillars built |

---

## 🚨 Current Focus (2026-05-18)

**Strategy live**: v22 untouched, +$107 dry-run, runs as evidence stream.

**Active work**: Brain (Phase 13) autonomously testing variants — `*/10 * * * *` cadence, smart guided generation around top-3 known results, daily 08:00 Telegram digest. 19 experiments completed / 125 queued / 0 positive-profit yet.

**Immediate gates:**
1. ⏳ Brain finds ≥3 v23 configs `profit_pct > 0` on BOTH bull AND bear windows
2. ⏳ Best v23 PF ≥ 1.2
3. Once 1+2 met → Telegram promotion alert with Apply button → v23 swap

**Walk-forward**: DEPRECATED as Phase 10 gate. v22 fails it catastrophically (-2,302 USDT). Replaced by per-window brain experiments + dry-run track record.

**Monitoring (all cron'd):**
- Brain: run every 10 min, generate every 6h, scan daily 07:00, digest daily 08:00
- Watchdog: every 30m (container/training/heartbeat alerts)
- Trade postmortem: every 15m → `finbuddy_memory/trades/closed.md`
- Daily summary: 08:00 (FreqTrade-native Telegram digest)

---

## Rules for Claude Code Working on These Tasks

1. Read `FINBUDDY_PROJECT_MEMORY.md` first — master hub
2. Read `CLAUDE_HANDOFF.md` for current decisions + dead-things list
3. Read the relevant phase file before changes
4. All new code goes in `freqtrade/user_data/` or `scripts/`
5. Auto-updated files (`finbuddy_memory/regimes/*`, `trades/*`, `research/*-nightly.md`, `CONTEXT.md`) — never edit manually
6. Strategy changes require backtest validation (brain or manual)
7. Mobile-debuggable — keep it simple
8. Update phase file status + this index together
9. Hard cost ceiling: $3–5/month
10. Don't pile session notes into `CLAUDE.md` — use phase files or `CLAUDE_HANDOFF.md`

---

## Overall Progress

```
Phases Complete:     5 / 13  (Phases 0, 8, 9, 11, 12)
Phases Live (cron):  6 / 13  (Phases 2, 3, 4, 5, 7, 13)
Phases In Progress:  1 / 13  (Phase 1 — v22 live, waiting for brain to find upgrade)
Phases Blocked:      1 / 13  (Phase 10 — needs brain-promoted variant or track record)
Phases Abandoned:    1 / 13  (Phase 6 — TradingView)
```

---

## 🔗 Related Files
- [[../CLAUDE]] ← operational context (do NOT pile session notes here)
- [[../FINBUDDY_PROJECT_MEMORY]] ← master hub
- [[../CLAUDE_HANDOFF]] ← current session decisions + dead-things list
- [[../COLLABORATION_CONTRACT]] ← roles, automation principles
- [[../CONTEXT]] ← live context injected into AI prompts
- [[../regimes/current]] ← live regime snapshot
- [[../strategies/graveyard]] ← retired strategies + historical backtests
