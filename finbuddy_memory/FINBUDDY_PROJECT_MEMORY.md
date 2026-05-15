# FinBuddy Project Hub

> **Phase boundary:** All performance evaluation and future research are **Futures Mode only** (Binance USDT-M Perpetual, long AND short). Any older spot-only conclusions are kept as historical context only.

**Project:** FinBuddy — Autonomous AI Brain for Crypto Trading  
**Owner:** Gaurav (star7gaurav@gmail.com)  
**Status:** 🟢 v20 code live · 2x Leverage · 8 Max Trades · Fixed Macro Data Fetchers · 25 pairs · Stoploss bug fixed  
**Last Updated:** 2026-05-14 (Claude Code — Phase 1-3 optimizations: v20 strategy, 2x leverage, macro safety gates, fixed regime path, fixed news/trends fetchers)

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
> 🤖 *Auto-synced by `scripts/sync_context.py` at 2026-05-15 08:00 UTC*

## 🚀 Live System State (Auto-Synced)

| Component | Status | Notes |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run | Strategy v16.2, Binance USDT-M, isolated margin, port 8080 |
| **FreqAI identifier** | `finbuddy_v19_asym_1778575138` | Active model key |
| **Whitelist** | 25 pairs | Binance USDT-M perpetuals |
| **Regime** | ⚖️ NEUTRAL | From HMM (updates every 4h) |
| **Open trades** | 2 (0L / 2S) | Live positions |
| **Closed trades** | 152 | All-time P&L: 11.90 USDT |
| **Last training** | unknown | Age of most recent 'Done training' log event |
| **Walk-forward** | ❌ FAIL — WR 47.0%, Sharpe -5.12, DD 21.8%, PF 0.73 (8535 trades, run `FinBuddyFreqAI_2024-01-01_2026-04-01_20260509T190609`) | OOS validator — gates Phase 10 |

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

## 📈 Backtest History — Futures (v6 → v18)

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

### v18 Campaign (2026-05-10): 24 Runs — 0/24 PASS

**Grid**: k_mult∈{1.0,1.5,2.0} × label_period∈{12,24} × ml_threshold∈{0.60,0.65} × 2 windows (bull+bear)

| Metric | Range across all 24 runs | Target | Pass? |
|---|---|---|---|
| Win Rate | 61–64% | >50% | ✅ Every combo |
| Max Drawdown | 1.57–4.60% | <20% | ✅ Every combo |
| Sharpe | −0.12 to −4.88 | >0.5 | ❌ Every combo |
| Profit Factor | 0.83–0.996 | >1.2 | ❌ Every combo |

**Root cause**: Symmetric 1:1 R:R (k_tp=k_sl). Fee drag (~$196/yr at 4.6 trades/day) exactly cancels gross edge. Losers held 2× longer (14h vs 7h), adding funding fee drag.

**Grid confirmed inert**: k_mult, label_period, and ml_threshold are all insufficient. The structural R:R must change.

**Fix — v19**: Asymmetric barriers `K_TP=2.0×ATR, K_SL=1.0×ATR`. At 62% WR → theoretical PF=3.26.

### v19 Plan — Asymmetric Barriers (2026-05-12)

**Grid**: K_TP∈{1.5,2.0,2.5} × K_SL∈{0.8,1.0} × ml_threshold∈{0.60,0.65,0.70} = **18 combos × 2 windows = 36 runs**

| Combo | Theoretical PF at 62% WR | Break-even WR |
|---|---|---|
| K_TP=1.5 / K_SL=1.0 | 2.45 | 40% |
| K_TP=2.0 / K_SL=1.0 | 3.26 | 33% |
| K_TP=2.5 / K_SL=1.0 | 4.07 | 29% |
| K_TP=1.5 / K_SL=0.8 | 3.06 | 35% |
| K_TP=2.0 / K_SL=0.8 | 4.08 | 29% |
| K_TP=2.5 / K_SL=0.8 | 5.10 | 24% |

**label_period_candles = 6 (fixed)** — R8 grid winner. Tighter K_SL resolves more labels within 6h.

**New in v19**: `feature_engineering_standard` active — adds day_of_week, hour_of_day, raw OHLCV.  
**Identifier**: `finbuddy_v19_asym_1778575138` — all 25 pairs retraining on next candle.  

### The v23 Pivot — Omni-Timeframe & MLOps (Phase 13)

**Why v21/v22 Failed:** The v21 campaign attempted to solve a low Win Rate by slapping a "dumb" 4H macro trend gate over a 1H ML model. The backtest campaign ran on 2026-05-15 and completely catastrophically failed (`0/18 PASS`, `WR 21%`). The 1H model was generating signals that conflicted massively with the static 4H gate. 

**How we fixed it (The Omni-Timeframe Shift):** We cannot restrict the AI with static rules; the AI must *learn* the rules. We shifted the entire architecture to **Phase 13: The Conscious Brain**:
1. **5-Minute Base:** The bot now evaluates the market every 5 minutes (`timeframe="5m"`).
2. **Peripheral Vision:** FreqAI now natively ingests the `15m`, `1h`, and `4h` timeframes simultaneously (`include_timeframes`). The AI learns the correlations between macro trends and micro pullbacks itself.
3. **Liquidity Vetoes:** We added 24-hour Order Block detection (Liquidity Pools). The bot strictly vetoes shorts at the bottom (Support) and longs at the top (Resistance).
4. **Volatility Shield:** A tick-volatility hook exits a trade immediately if volume spikes >500% against the position in the first 10 minutes, bypassing the slow ATR stoploss.

**What the MLOps Loop does:** We built a true Self-Evolution pipeline (`scripts/karpathy/run_loop.py`). Installed via cron (running at 2:00 AM nightly), this script reads the results of the `v23` autobacktest. If it finds a "God-Tier" parameter set (`WR > 60%`, `Sharpe > 1.0`), it automatically edits the live `docker-compose.yml` to inject the winning TP/SL multipliers and restarts the bot. FinBuddy now evolves autonomously.

---

## 🚀 Current State (2026-05-15)

| Component | Status |
|---|---|---|
| **FreqTrade** | ✅ Running, dry-run, futures isolated |
| **Strategy** | ✅ FinBuddyFreqAI **v23 code** — Phase 13 Omni-Timeframe (5m base), Order Block Vetoes, and Volatility hook. |
| **FreqAI identifier** | `finbuddy_v19_asym_1778575138` — 1h live (Awaiting v23 backtest to finish before deploying new 5m model). |
| **FreqAI Model** | ✅ FinBuddyLLMModel **v5** — auto-confirm fix (proba ≥ 0.90 bypasses LLM) |
| **Live P&L** | Monitoring existing trades while v23 computes |
| **Backtest Campaign** | ⏳ Running: `v23` Omni-timeframe autobacktest. MLOps loop waiting to automatically deploy God-Tier combos |
| **All Crons** | ✅ Live (Phase 2–5, watchdog, postmortem, daily summary, WF notify) |
| **Phase 10 go-live** | ⬜ BLOCKED — needs walk-forward PASS |

## 🐛 Critical Bug Fixed (2026-05-13) — commit `21796ea`

**Bug**: `custom_stoploss` returned `None` for ALL trades (longs and shorts) since v17.

**Root cause**: `stoploss_from_open()` ALWAYS returns `>= 0` (per docs). Guards were `< 0` — always rejected the value — always returned `None` — hard `-8%` config stoploss fired for every loss. No ATR protection ever worked since v17.

**Evidence**: NEAR short #64 ran 7.4h to exactly −8.14%. All open shorts showed `sl=0.0000`.

**Fix**: Changed both `< 0` guards to `> 0`. The `= 0` case (stop already breached) is correctly discarded.

**Implication**: v17/v18 backtest PF results were worse than they would have been with working ATR stops. v19 campaign will be the first with ATR protection actually functioning.

---

## 📋 Phase 0 Checklist (Foundation) ✅ COMPLETE

- [x] Task 0.1 — Trade Event Handler (wired, active in N8N v4 pipeline)
- [x] Task 0.2 — Telegram configuration (enabled with token + chat_id)
- [x] Task 0.3 — **Pairlist Audit** (D/USDT, CHIP, SOMI, ZBT blacklisted in config)
- [x] Task 0.4 — N8N cleanup (2 active workflows, dead ones removed)
- [x] Task 0.5 — User config (user_01_gaurav.json configured)

**Status:** All 5 tasks verified complete on live server. Phase 0 → Phase 1 transition ready.
## 🧱 Core Engineering Principles

1. **Code over manual work:** Automate with cron/script; never waste AI tokens on repetitive tasks.
2. **AI for progress, not routine:** Use AI for design, debugging, monitoring, improvements.
3. **DRY & reusable design:** Shared logic in helpers/modules — no duplication across strategies.
4. **Documentation as memory:** All non-trivial behavior must be documented.
5. **Memory Maintenance (Crucial):** Agents MUST review project memory (`CLAUDE.md` and `FINBUDDY_PROJECT_MEMORY.md`) at the start of every session, identify stale information (versions, status, results), and update it immediately. This minimizes token usage and ensures a single source of truth.
6. **Never hardcode secrets:** API keys always from environment variables, never committed files.

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
| **NVIDIA NIM (7 models)** | NVIDIA | `NVIDIA_API_KEY` | Free tier | ✅ Signal confirmation via FinBuddyLLMModel — PRIMARY chain |
| **OpenRouter free** | OpenRouter | `OPENROUTER_API_KEY` | Free tier | ✅ Signal confirmation fallback |
| **claude-sonnet-4-6** | Anthropic | `ANTHROPIC_API_KEY` | Per use | Claude Code — deploy, monitor, debug |
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
| 1 — FreqAI Brain | 🔄 In Progress | v17 live (symmetric barriers, LLM layer active); WF #5 running — gate to Phase 10 |
| 2 — Data Enrichment | ✅ Live | 5 external fetchers + combined_context.json, cron every 15m |
| 3 — HMM Regime | ✅ Live | 5-regime HMM + regime-aware sizing hooks, cron every 4h |
| 4 — Obsidian Memory | ✅ Live | CONTEXT auto-write + vault git-commit, cron every 15m |
| 5 — Karpathy Loop | ✅ Live | Nightly Gemini + DeepSeek R1 research at 02:00 |
| 6 — TradingView | 🔴 Abandoned | Requires paid plan — dropped 2026-05-04 |
| 7 — Executor | ✅ Live (paper) | Python signal executor cron every 5m |
| 8 — Futures Setup | ✅ Complete | Binance futures API, isolated margin, memory mounted |
| 9 — Risk Engine | ✅ Complete | Regime stake sizing, cluster cap, funding guard, DD gate |
| 10 — Live Migration | ⬜ BLOCKED | Needs walk-forward PASS or 6-month dry-run track record |
| 11 — Self-Evolution | ✅ Live | Memory integration, RS metrics, and dynamic regime thresholds |
| 12 — Brain Dashboard | ✅ Complete | God-Tier React SPA with WebSockets, Live Trades, and Neural Feed |
| 13 — Conscious Brain | ✅ Complete | Omni-Timeframe (5M Base), Liquidity Awareness, Dynamic SL, MLOps Loop |

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
