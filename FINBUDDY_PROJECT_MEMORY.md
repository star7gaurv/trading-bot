# FinBuddy Project Hub

> **Phase boundary:** All performance evaluation and future research are **Futures Mode only** (Binance USDT-M Perpetual, long AND short). Any older spot-only conclusions are kept as historical context only.

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟢 v16.2 live · 25 pairs · Walk-forward running · First clean trades #30–32 fired  
**Last Updated:** 2026-05-09 (Claude Code — v16.1 clean model, v16.2 confirm_trade_entry, watchdog hardened, walk-forward launched, daily summary added)

---

## 🧠 What Is FinBuddy?

An **autonomous, self-evolving AI brain for crypto trading** — NOT a bot.
- Observes markets, forms hypotheses, tests them via walk-forward backtest
- Promotes winning strategies, retires losers
- Gets smarter over time without manual intervention
- FreqTrade is just the hands (execution); the brain is the product
- **Primary market: Binance Futures (USDT-M Perpetual) — long AND short**
- Spot trading will be added later as a secondary module

---

<!-- AUTO-SYNC-START -->
> 🤖 *Auto-synced by `scripts/sync_context.py` at 2026-05-09 12:30 UTC*

## 🚀 Live System State (Auto-Synced)

| Component | Status | Notes |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run | Strategy v16.2, Binance USDT-M, isolated margin, port 8080 |
| **FreqAI identifier** | `finbuddy_v16_clean_1778316280` | Active model key |
| **Whitelist** | 25 pairs | Binance USDT-M perpetuals |
| **Regime** | ⚖️ NEUTRAL | From HMM (updates every 4h) |
| **Open trades** | 3 (0L / 3S) | Live positions |
| **Closed trades** | 32 | All-time P&L: 3.38 USDT |
| **Last training** | unknown | Age of most recent 'Done training' log event |
| **Walk-forward** | ❌ ['❌ WR 30.3% (need >50%)', '❌ Sharpe -10.435 (need >0.5)', '✅ Worst DD 19.3%', '❌ PF 0.430 (need >1.2)'] — median Sharpe ?, WR ?% (FinBuddyFreqAI_2024-01-01_2026-04-01_20260509T091607) | OOS validator — gates Phase 10 |

<!-- AUTO-SYNC-END -->

---

## 📊 Monitoring Tools

| Script | Schedule | Purpose |
|---|---|---|
| `scripts/watchdog.py` | Cron every 30m | Telegram alert: container down, training stale (>8h), heartbeat lost (>5m), **disk >80%**. File-log fallback prevents false alerts from Docker buffer eviction or slow docker daemon. |
| `scripts/trade_postmortem.py` | Cron every 15m | Appends every closed trade to `finbuddy_memory/trades/closed.md` with regime tag. **Bias detector**: Telegram alert if last 10 trades are ≥85% one-sided (6h cooldown). |
| `scripts/daily_summary.py` | Cron 8am daily | Telegram morning digest: regime, open trades (L/S split), yesterday P&L, all-time stats, last training age. |
| `scripts/pair_performance.py` | Cron 8am daily | Per-pair WR/PF/profit table (last 7 days). |
| `scripts/sync_context.py` | Cron every 4h | Auto-syncs the `<!-- AUTO-SYNC -->` block in this file with live state; appends state-change events to `finbuddy_memory/session_events.md`; auto-commits. |
| `scripts/walkforward_notify.py` | Cron every 30m | Watches `walkforward_results/` for completed runs (`summary.json` present) and Telegrams the PASS/FAIL verdict. Idempotent. |
| `scripts/walkforward_monthly.sh` | Cron 1st of month 03:00 UTC | Auto-runs `walk_forward.py` on a 27-month window. flock(1) prevents overlap. |
| `scripts/download_data_daily.sh` | Cron 04:30 UTC daily | Refreshes 3 days of futures OHLCV/funding/mark data so monthly WF can use `--skip-download`. |
| `scripts/walk_forward.py` | On-demand + monthly cron | Rolling-fold OOS validator (train 6mo / test 1mo, 21 folds). Gates Phase 10. |

---

## 📈 Backtest History — Futures (v6 → v16)

### Rounds 1–5 (v6 → v10): Stop-Loss Architecture Sweep

| Round | Strategy | Key Change | Bull P&L | Bear P&L | Bull Sharpe | Bear Sharpe |
|---|---|---|---|---|---|---|
| 1 | v6 | Futures-ready spot rewrite | -10 | -23 | -0.145 | -0.258 |
| 2 | v7 | Stoploss tightened to -1.5% | -47 | -36 | -0.896 | -0.554 |
| 3 | v8 | ATR-based `custom_stoploss()` | -33 | -12 | -0.78 | -0.22 |
| 4 | v9 | `trailing_stop=False` + macro short-gate | -7 | -22 | -0.13 | -0.37 |
| **5** | **v10** | **`stoploss_from_open()` — entry-anchored stops** | **+7.24** | **-8.78** | **+0.13** | **-0.15** |

### Round 8 (v15): Grid Search — The Breakthrough

**Grid**: 90 combos; 1h TF; label_period∈{4,6,8}; ml_threshold∈{0.55,0.60,0.65,0.70}

**Winner**: ml_threshold=0.60, ml_exit=0.60, label_period=6, atr_threshold=0.002

| Metric | Bull (2024-01-01→2025-01-01) | Bear (2025-01-01→2026-04-01) | Target | Pass? |
|---|---|---|---|---|
| Win Rate | 57.7% | 58.7% | >50% | ✅ Both |
| Max Drawdown | 2.5% | 7.0% | <20% | ✅ Both |
| Sharpe | +1.49 | -0.114 | >0.5 | ✅ Bull / ❌ Bear |
| Profit Factor | >1.2 | 0.979 | >1.2 | ✅ Bull / ❌ Bear |

**Decision**: CONDITIONAL GO. Deploy, run dry-run; walk-forward OOS is the next gate.

---

## 🧱 Core Engineering Principles

1. **Code over manual work:** Automate with cron/script; never waste AI tokens on repetitive tasks.
2. **AI for progress, not routine:** Use AI for design, debugging, monitoring, improvements.
3. **DRY & reusable design:** Shared logic in helpers/modules — no duplication across strategies.
4. **Documentation as memory:** All non-trivial behavior must be documented.
5. **Never hardcode secrets:** API keys always from environment variables, never committed files.

---

## 📚 Critical Freqtrade Rules (from develop docs — must follow)

| Rule | Why It Matters |
|---|---|
| `INTERFACE_VERSION = 3` in every strategy | v2 strategies silently break in new versions |
| `can_short = True` at strategy class level | Without this, short signals are silently ignored |
| `startup_candle_count ≥ max_indicator_period` | Backtesting will use unstable (NaN-filled) candles without this |
| Never use `datetime.now()` in callbacks | Use `current_time` parameter — live vs backtest differ |
| Never use `iloc[-1]` or loops in `populate_*` | Must be vectorized pandas — loops break backtesting |
| Custom stoploss for futures: `return -0.04 * trade.leverage` | Without leverage multiply, stoploss is too tight |
| `adjust_trade_position()` for DCA | Requires `position_adjustment_enable: true` in config |
| Env vars override config.json override strategy | `FREQTRADE__EXCHANGE__KEY=...` format in Docker |
| Backtest flag `--enable-protections` | Includes cooldown/stoploss guard effects |
| `--timeframe-detail 1m` for precise SL/TP | Without this, stoploss fires may be imprecise in backtest |

---

## 🤖 AI Model Stack

> **Rule:** Never hardcode API keys. Always use environment variables.

| Model | Provider | Env Var | Cost | Role |
|---|---|---|---|---|
| **grok-3-mini** | xAI | `XAI_API_KEY` | $0.10/M | ✅ Real-time signal confirmation — PRIMARY |
| **grok-3** | xAI | `XAI_API_KEY` | $2/M | Optional upgrade if needed |
| **claude-sonnet-4-5** | Anthropic | `ANTHROPIC_API_KEY` | $3/$15/M | ✅ Claude Code — deploy, monitor, debug |
| **gemini-2.5-flash** | Google | `GEMINI_API_KEY` | Free tier | Nightly research loop (Phase 5) |
| **deepseek-chat** | DeepSeek | `DEEPSEEK_API_KEY` | ~$0.01/M | Future bulk hypothesis generation |

---

## 🚨 7-Day No-Trade Crisis (2026-05-08) — RESOLVED

**Symptom:** Bot running, training models, refreshing pairlist — ZERO trades for 7 days.

| Root Cause | Fix |
|---|---|
| 21 new pairs not training — old identifier had pre-existing partial state (4 pairs) | Changed identifier → forced clean retrain of all 25 pairs |
| `datasieve.pipeline WARNING - Could not find step di` (assumed blocking) | Confirmed cosmetic when `DI_threshold` not set — no fix needed |
| Macro filter deadlock — BTC between MA200 and 4h EMA50, neither long nor short could fire | Defaulted `BTC_MA200_GATE=0` (opt-in); removed hardcoded `btc_4h_below_ema50==1` short filter |

**Commit:** `d127347` — "fix: unstick v15 — disable BTC MA200 gate, remove hard btc_4h_below_ema50 short filter, fresh FreqAI identifier"

---

## 🚨 Status Legend

| Icon | Meaning |
|---|---|
| ✅ COMPLETE | Verified live on server by Claude Code |
| ⚠️ CONDITIONAL | Partially passes — conditions remain |
| ⏳ RUNNING | Actively in progress |
| ⬜ PENDING | Not started |
| 🔴 RETIRED/ABANDONED | Superseded — do not continue |

---

## 🆕 Phase Roadmap (Authoritative — 2026-05-09)

| Phase | Status | Focus |
|---|---|---|
| 0 — Foundation | ✅ Complete | FreqTrade, Telegram, server, N8N cleanup |
| 1 — FreqAI Brain | ⚠️ Conditional Pass | v16.2 live; bull ALL PASS; bear WR/DD pass; walk-forward is the gate to Phase 10 |
| 2 — Data Enrichment | ✅ Live | 5 external fetchers + combined_context.json, cron every 15m |
| 3 — HMM Regime | ✅ Live | 5-regime HMM + regime-aware sizing hooks, cron every 4h |
| 4 — Obsidian Memory | ✅ Live | CONTEXT auto-write + vault git-commit, cron every 15m |
| 5 — Karpathy Loop | ✅ Live | Nightly Gemini + DeepSeek R1 research at 02:00 |
| 6 — TradingView | 🔴 Abandoned | Requires paid plan — dropped 2026-05-04 |
| 7 — Executor | ✅ Live (paper) | Python signal executor cron every 5m |
| 8 — Futures Setup | ✅ Complete | Binance futures API, isolated margin, memory mounted |
| 9 — Risk Engine | ✅ Complete | Regime stake sizing, cluster cap, funding guard, DD gate |
| 10 — Live Migration | ⬜ BLOCKED | Needs walk-forward PASS or 6-month dry-run track record |

---

## 🗓️ Live Crontab (server — verified 2026-05-09)

```
0 * * * *    auto_commit.sh                                     # vault git commit hourly
*/15 * * * * fetch_all_external.py                              # Phase 2 data
0 */4 * * *  hmm_regime_detector.py                             # Phase 3 HMM
*/15 * * * * memory_writer.py && git_commit.sh                  # Phase 4 memory
0 2 * * *    karpathy/run_loop.py                               # Phase 5 research
*/5 * * * *  executor/executor.py                               # Phase 7 executor
0 8 * * *    pair_performance.py --since 7-days-ago             # monitoring
*/30 * * * * watchdog.py                                        # bot silence detector
*/15 * * * * trade_postmortem.py                                # closed-trade ledger
0 6 * * *    run_promotion.sh                                   # daily promotion check
0 8 * * *    daily_summary.py                                   # Telegram morning digest
# REMOVED 2026-05-09: @reboot openclaw (abandoned), @reboot uvicorn webhook_receiver (TV abandoned)
```

---

## 🔗 Related Files

- [[CLAUDE]] ← deep project context, architecture, and full session history
- [[COLLABORATION_CONTRACT]] ← roles, automation rules, AI vs code boundaries
- [[CLAUDE_HANDOFF]] ← current action queue + label/walk-forward decisions
- [[tasks/TASKS]] ← canonical phase list and statuses
- [[finbuddy_memory/CONTEXT]] ← live context injected into AI prompts
- [[finbuddy_memory/regimes/current]] ← live regime snapshot
- [[strategies/registry]] ← strategy registry & lifecycle

---

*This hub must be updated at the end of every major session. It is the high-level single source of truth for the project.*
