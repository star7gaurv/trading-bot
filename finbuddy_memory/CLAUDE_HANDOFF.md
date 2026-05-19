# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-19
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, regression) |
| FreqAI identifier | `finbuddy_v23_live_1779189570` |
| FreqAI model class | `LightGBMRegressor` — NO LLM wrapper (v23 dropped FinBuddyLLMModel) |
| Pairs | 25, futures USDT-M isolated, 2x leverage, max 8 trades |
| Regime | ⚖️ NEUTRAL |
| Live closed P&L | **+$94.94 USDT (+9.59%)** · 291 trades — **regime-coincidental, not verified edge** |
| Bot status | ✅ Running, dry-run mode |
| Per-pair-per-regime gate | ✅ Active — `pair_regime_stats.json` blocks combos with rolling 30d WR<40% AND PF<0.7 |
| docker-compose env-vars | ✅ Fixed 2026-05-19 — all `FREQAI_*` now wired via `environment:` block |

**Live env vars (best-known v23):** K_TP=2.0, K_SL=2.0, LONG_THRESHOLD=3.25, SHORT_THRESHOLD=-2.75, STABILITY_N=2

**Reality check:** v22 +$94 profit was 45-day BEAR regime coincidence (last 20 v22 trades = 3W/17L). v23 has no backtest-confirmed edge yet. Phase 10 still blocked.

---

## 🐛 Bug Fixed This Session (2026-05-19 PM)

**Candle-count calculations hardcoded 5m seconds (`/300`) — strategy runs on 15m (900s).**

Both `custom_stoploss` (emergency vol shield) and `custom_exit` (time-limit) divided `total_seconds` by `300`. On 15m TF:
- Emergency shield fired after 10 min instead of 30 min (first 2 real candles)
- Time-limit exit fired at 6h instead of 18h — force-closing trades 3× too early

Fix: imported `timeframe_to_seconds` from `freqtrade.exchange` and replaced both hardcoded `300` values. Commit: `0ede041`.

---

## 🧠 Brain (Autonomous Hypothesis Engine) — Active

**All crons running, no human intervention needed:**

| Cron | What |
|---|---|
| `*/10 * * * *` | Run 1 experiment (v23 variant on bull/bear window) |
| `0 */6 * * *` | Generate 4 safe + 6 aggressive hypotheses, queue to JSONL |
| `30 */6 * * *` | Analyse completed runs, write analyst_report.json |
| `0 7 * * *` | Daily promotion-candidate scan + Telegram alert |
| `0 8 * * *` | Daily digest to Telegram — best results, queue health, 7d trend |

**State (2026-05-19):**
- 139 experiments completed, 61 queued
- **2 profitable runs found:**
  - `bear_2025Q1`: profit=+0.192%, Sharpe=1.424 ✅, PF=1.214 ✅, DD=16.4% ✅, WR=48.1% ❌
  - `bull_2024Q2`: profit=+0.04%, Sharpe=0.258 ❌
- Best config: `long_threshold=3.25, short_threshold=-3.0, k_sl=2.0, k_tp=2.0, stability_n=1, label_period=12`
- Promotion criteria NOT met yet (need ≥2 bull AND ≥2 bear profitable runs with positive Sharpe + ≥60 total trades)

**Smart hypothesis gen (added 2026-05-18):** 50% guided variants (perturbations around top-3 results) + 50% pure-random.

---

## 📞 Telegram Bot Setup

**Two separate bots:**

| Bot | Token | What |
|---|---|---|
| FreqTrade native | `8557119080:...` | Trade open/close, /status, /profit commands |
| **Brain bot** | `8051489946:...` (BRAIN_TELEGRAM_TOKEN env) | Brain alerts, daily digest, promotion candidates with ✅Apply / ⏭️Skip / 🔍Details inline buttons |

Listener: `*/2 * * * * flock -n ... scripts/telegram_listener.py` — flock prevents duplicate instances.

---

## 🚨 Known Dead/Stale Things — DO NOT RESURRECT

| Thing | Status |
|---|---|
| `FinBuddyFreqAI.py` (v22) | File on disk for history — never re-activate |
| `FinBuddyLLMModel.py` (v5) | File on disk for history — v23 doesn't use it |
| `walk_forward.py` v22 re-runs | v22 failed catastrophically (WR 21.2%). No point re-running. |
| `N8N` Telegram pipeline | Permanently disabled |
| `OpenClaw` / `jack.star7gaurav.in` | Abandoned proxy |
| Phase 6 TradingView | Abandoned (paid plan required) |
| Manual threshold tuning | Brain owns this — never hand-tune |

---

## ⏭️ Next Actions (in priority order)

1. **Brain continues autonomously** — let it run. Cross-window validation of the best bear config will happen when the analyst sees it pass.
2. **Add cross-window validation to brain** — when a config passes one window, immediately queue the same exact config on the other 2 windows. Currently relies on random sampling to cross-validate, which is slow.
3. **Fix `download_data_daily.sh` backfill** — script only forward-increments. Newly-added pairs won't get historical 4h data → same NaN crash repeats. Needs `--if-short-history` backfill check.
4. **Phase 10** — BLOCKED until brain finds a passing config + walk-forward passes.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub (auto-synced)
- [[CONTEXT]] — live context injected into AI prompts
- [[../CLAUDE]] — deep project background
- `scripts/brain/README.md` — brain operator cheatsheet
