# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-20
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (15m TF, LightGBMRegressor, regression) |
| FreqAI identifier | `finbuddy_v23_funding_1779270021` (bumped 2026-05-19 when funding feature added) |
| Model features | **533 total** (added 3 funding-rate features 2026-05-19) |
| Pairs | 25, futures USDT-M isolated, 2x leverage, max 8 trades |
| Regime | ⚪ NEUTRAL |
| Live closed P&L | **+$98.01 USDT · 295 trades** — best-known v23 config (not verified edge) |
| Bot status | ✅ Running, dry-run mode (training fresh on funding features) |
| Per-pair-per-regime gate | ✅ Active |
| docker-compose env-vars | ✅ Wired via `environment:` block |

**Live env vars:** K_TP=2.0, K_SL=2.0, LONG_THRESHOLD=3.25, SHORT_THRESHOLD=-2.75, STABILITY_N=2

---

## 🐛 Bugs Fixed This Session (2026-05-19 → 2026-05-20)

1. **Stop-ratchet bug** (commit `4702549`) — `custom_stoploss` was recomputing `sl_pct` every candle using live ATR. As volatility contracted post-entry the stop ratcheted inward, killing 106 trades at avg -0.18%. Now caches `entry_atr_pct` via `trade.set_custom_data`.
2. **Time-limit exit** (commit `4702549`) — 72 → 24 candles (= 2× label_period). Was force-closing dead positions at 18h on 15m TF; now 6h.
3. **Brain promotion gates loosened** (commit `3eafab8`) — `MIN_AVG_PROFIT_IMPROVEMENT` 1.0 → 0.1; `min(profits) > 0` → `avg(profits) > 0 AND min > -0.3`. Brain `requeue` CLI added.
4. **Funding-rate feature** (commit `b4e9d6f`) — 3 new features fed to LightGBM. Backfilled 7,333 historical funding events.
5. **Live bot dead 6h recovery** (commit `7c8bf52`) — adding funding feature created schema mismatch with FreqAI's root-level pipeline cache. Recovery recipe saved.
6. **auto_promote.py None rendering** (commit `7c8bf52`) — was reading wrong path in summary.json; now formats "—" for missing.
7. **Daily walk-forward** (commit `d6c883d`) — `0 22 * * *` cron added. Monthly heavy kept.
8. **Disk cleanup** — 4.7 GB reclaimed (docker images + retired-version model dirs).

---

## 🧠 Brain (Autonomous Hypothesis Engine) — Active

**Crons:**

| Cron | What |
|---|---|
| `*/10 * * * *` | Run 1 experiment |
| `0 */6 * * *` | Generate 4 safe + 6 aggressive hypotheses |
| `30 */6 * * *` | Analyse + prune dead patterns |
| `0 7 * * *` | Daily promotion-candidate scan |
| `0 8 * * *` | Daily digest to Telegram |
| `0 22 * * *` | **Daily walk-forward** (12mo rolling, ~80 min) |
| `0 3 1 * *` | Monthly heavy walk-forward (27mo) |
| `0 4 * * *` | `auto_promote.py` — Telegrams Sharpe vs baseline |
| `25 1 * * *` | **Funding-rate parquet refresh** |

**State (2026-05-20):**
- 234 experiments completed, 13 queued, 14 failed
- **Best so far:** `e0e1bf338410` — profit=+0.192%, WR=48.1%, Sharpe=1.424, PF=1.21 (bear_2025Q1)
- 5 cross-window winners requeued via `brain_cli.py requeue` to reach 2+2 sample count
- Loosened gate: promotion needs `avg(profits) > 0 AND min > -0.3` per side, `improvement ≥ +0.1pp`
- Live baseline: `avg_profit_pct=0.0` (initialised this session)

**Brain → live path** (fully wired, just needs a winner):
```
brain run → analyst → scan (daily 07:00) → pending.json + Telegram with Apply/Skip buttons
→ tap Apply → telegram_listener calls promote.py --apply
→ backup config.json, write .env, bump identifier, docker-compose restart
```

---

## 📞 Telegram Bot Setup

| Bot | Token | What |
|---|---|---|
| FreqTrade native | `8557119080:...` | Trade open/close, /status, /profit commands |
| **Brain bot** | `8051489946:...` (BRAIN_TELEGRAM_TOKEN env) | Brain alerts, daily digest, promotion candidates with ✅Apply / ⏭️Skip / 🔍Details inline buttons |

Listener: `*/2 * * * * flock -n ... scripts/telegram_listener.py` — flock prevents duplicate instances.

---

## 🚨 Known Dead/Stale Things — DO NOT RESURRECT

| Thing | Status |
|---|---|
| `FinBuddyFreqAI.py` (v22) | File on disk for history — never re-activate. **Always grep config.json "strategy" before editing.** |
| `FinBuddyLLMModel.py` (v5) | File on disk for history — v23 doesn't use it |
| `scripts/run_promotion.sh` | Removed from cron 2026-05-19 (legacy CSV path). File on disk. |
| `walk_forward.py` v22 re-runs | v22 failed catastrophically (WR 21.2%). No point re-running. |
| `N8N` Telegram pipeline | Permanently disabled |
| `OpenClaw` / `jack.star7gaurav.in` | Abandoned proxy |
| Phase 6 TradingView | Abandoned (paid plan required) |
| Manual threshold tuning | Brain owns this — never hand-tune |

---

## ⚠️ Open Strategic Issues (not blocking, document for next session)

1. **Model is over-long in bear regimes** — bear_2025Q1 brain runs show avg ~60% longs. Training data is skewed toward 2024 bull → constant optimistic regression bias. Fix path: target standardization or class-weight on regression. Deferred this session.
2. **Bull_2024Q1 30% WR catastrophe** — same root cause. Bull_2024Q1 has only 3mo of post-spot-pivot data, model under-trained there.
3. **Brain analyst occasionally queues already-pruned TFs** — minor cycle waste. Low priority.

---

## ⏭️ Next Actions (in priority order)

1. **Watch tonight's walk-forward** (22:00 UTC) — first run on v23 + funding feature. Expected to take ~80 min. `tail -f ~/.finbuddy/logs/walk_forward.log`.
2. **Watch 04:00 auto_promote** for first non-"None" Telegram with real Sharpe vs baseline.
3. **Implement Open Interest delta as the next feature** — same fetch pattern as funding rate. Second-best published signal.
4. **Then tackle the long-bias** — target standardization on `&-future_return` (subtract rolling mean over training window).
5. **Phase 10** — BLOCKED until walk-forward PASSES (Sharpe > 0.5, WR > 50%, DD < 20%, PF > 1.2) OR 6-month dry-run track record.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub
- [[CONTEXT]] — live context injected into AI prompts
- [[../CLAUDE]] — deep project background
- `scripts/brain/README.md` — brain operator cheatsheet
