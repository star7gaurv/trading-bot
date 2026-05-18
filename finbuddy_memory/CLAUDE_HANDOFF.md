# 🤝 FinBuddy — Handoff Note for Claude Code

**Last updated:** 2026-05-18
**Branch:** `master`

---

## ✅ Current Live State

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI.py` (v22 code, 1h TF) — untouched, runs autonomously |
| FreqAI identifier | `finbuddy_v22_balanced_1779015982` |
| FreqAI model | `FinBuddyLLMModel` v5 (LightGBM + LLM auto-confirm ≥0.90) |
| Pairs | 25, futures USDT-M isolated, 2x leverage, max 8 trades |
| Regime | 🐻 BEAR (0.5× stake multiplier) |
| Live closed P&L | **+$107 USDT (+10.86%)** · 273 trades · WR 39.6% · PF 1.51 |
| Bot status | ✅ Running, dry-run mode, 4 open shorts |

**Reality check:** profit is real, but the bot's WF backtest fails catastrophically (-2,302 USDT, WR 21.2% on 21 folds May 16). Live performance is likely BEAR-favorable regime luck, not verified edge. Phase 10 still blocked — needs 6-month live track record OR WF pass.

---

## 🧠 Brain (Autonomous Hypothesis Engine) — Active

**On cron, no human intervention needed:**

| Cron | What |
|---|---|
| `*/10 * * * *` | Run 1 experiment (v22 or v23 variant on bull/bear window) — **accelerated 3× from 30min on 2026-05-18** |
| `0 */6 * * *` | Generate 4 safe + 6 aggressive hypotheses, queue to JSONL |
| `0 7 * * *` | Daily promotion-candidate scan + Telegram alert |
| `0 8 * * *` | **Daily digest** to Telegram — best results, queue health, 7d trend (added 2026-05-18) |

**State (2026-05-18):**
- 19 experiments completed, 125 queued
- Best so far: -0.106% / WR 52.9% / PF 0.88 on `bear_2025Q1` (5m, v23, k_sl=3.0/k_tp=2.0, N=2)
- **Zero positive-profit runs yet** — brain still exploring
- All hypotheses are v23-architecture variants (regression target, dynamic thresholds, OB veto)

**Smart hypothesis gen (added 2026-05-18):** `hypothesis_gen.py` now generates 50% guided variants (perturbations around top-3 known results) + 50% pure-random. Pure-random fallback if log empty.

---

## 📞 Telegram Bot Setup

**Two separate bots (since 2026-05-18):**

| Bot | Token | What |
|---|---|---|
| FreqTrade native | `8557119080:...` | Trade open/close, /status, /profit commands |
| **Brain bot** `@gauravbaliyan4557912145454_bot` | `8051489946:...` (BRAIN_TELEGRAM_TOKEN env) | All brain alerts, daily digest, promotion candidates with ✅Apply / ⏭️Skip / 🔍Details inline buttons |

Listener: `*/2 * * * * scripts/telegram_listener.py` polls brain bot, dispatches button taps.
Why two: FreqTrade was consuming all callback_query events on shared bot — now fixed.

---

## 🚨 Known Dead/Stale Things — DO NOT RESURRECT

| Thing | Status |
|---|---|
| `walk_forward.py` re-runs on v22 | v22 unchanged since May 16 fail; same result. Don't re-run. |
| v22b backporting | Aborted — wasted work. v22 stays live as-is. |
| `FinBuddyFreqAI_v23.py` direct manual edits | Brain owns v23 variant testing. Don't hand-tune. |
| `N8N` Telegram pipeline | Permanently disabled |
| `OpenClaw` / `jack.star7gaurav.in` | Abandoned proxy |
| Phase 6 TradingView | Abandoned (paid plan required) |

---

## ⏭️ Decision Point for Next Session

**v22 → v23 swap: NOT YET.**

Criteria for proposing the swap:
1. Brain finds ≥3 v23 configs with `profit_pct > 0` on BOTH bull AND bear windows
2. Best v23 PF ≥ 1.2 on at least one window
3. v23 best config validated on a 3rd window (e.g. `bull_2024Q2` or 6-month combined)

Currently: 0/3 conditions met. Let the brain run.

**Next thing to build (when user asks):** Auto-promotion logic — when v23 dry-run Sharpe > v22 live Sharpe for N days, send Apply button.

---

## 🔗 Related Files

- [[FINBUDDY_PROJECT_MEMORY]] — high-level hub (auto-synced)
- [[CONTEXT]] — live context injected into AI prompts
- [[../CLAUDE]] — deep project background (do NOT pile session notes here)
- [[tasks/phase-13-conscious-brain]] — current phase task tracker
- `scripts/brain/README.md` — brain operator cheatsheet
