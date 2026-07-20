# 🤝 Cortexa — Handoff Note for Claude Code

**Last updated:** 2026-07-20 UTC (rebrand to Cortexa; probe_scale/progress_cut sweep result recorded — also NO-GO)
**Branch:** `master`

---

## ✅ Current Live State (verified 2026-07-20 via `.env` + `config.json`)

| Item | Value |
|---|---|
| Live strategy | `FinBuddyFreqAI_v23.py` (1h TF; LightGBMRegressor, z-scored target) — file/class name intentionally NOT renamed in the Cortexa rebrand (live-system risk, deferred) |
| FreqAI identifier | `finbuddy_v23_tf1h_1782044602` |
| Pairs | **25** (TON removed 2026-07-08 — delisted) |
| Leverage | Confidence-based tiers 1×/2×/3× (FALLBACK = 1×) |
| Regime | **NEUTRAL (70% confidence)**, since 2026-07-20 |
| Wallet | **1000 USDT** dry-run \| max_open_trades **8** |
| Manual kill-switch | ✅ force-exit (dashboard + Telegram) + pause/resume, shipped 2026-07-14 |
| DI / SVM | DI_threshold=0, SVM disabled |
| Daily circuit breaker | ✅ FREQAI_DAILY_LOSS_LIMIT=10 |

**Live env vars (`freqtrade/.env`) — current:**
```
FREQAI_LONG_THRESHOLD=0.7
FREQAI_SHORT_THRESHOLD=-0.6    # asymmetric: longs are the worse side
FREQAI_K_TP=3.0
FREQAI_K_SL=3.5                # RAISED 2.0→3.5 on 2026-07-08 (Lever 1) — cut stop_loss share but PF got worse, see below
FREQAI_STABILITY_N=1
FREQAI_DAILY_LOSS_LIMIT=10
FREQAI_REENTRY_COOLDOWN_CANDLES=8
FREQAI_DAILY_FLATTEN_MULT=1.5
FREQAI_THRESHOLD_FLOOR=1        # default; effective threshold can only tighten past nominal
FREQTRADE__FREQAI__IDENTIFIER=finbuddy_v23_tf1h_1782044602
```
`FREQAI_PARTIAL_TP` / `FREQAI_PROBE_SCALE` / `FREQAI_PROGRESS_CUT` / `FREQAI_META_LABEL` all built, all plumbed through all 3 layers (runner/promote/docker-compose), all still **OFF live** — every A/B run so far has failed (see Brain State below).

⚠️ `docker-compose.yml` has an explicit `environment:` block — every new `.env` var MUST also be added there. `docker-compose restart` does NOT reload `.env` — always `docker-compose up -d freqtrade`.

---

## 📊 Live Performance (since 2026-07-17 diagnosis)

| Metric | Value |
|---|---|
| Lifetime P&L | **+11.34 USDT** (1,003+ trades) |
| Since 2026-07-08 (K_SL=3.5 went live) | **−10.46 USDT** on 111 trades — losing streak, not a bug |
| Pre-fix (K_SL=2.0) | WR 41.9%, PF 1.04, net +21.80 — stop_loss (39% of trades, 0% WR) almost exactly canceled by exit_signal (29%, 91% WR) |
| Post-fix (K_SL=3.5) | WR rose to 47.7%, stop_loss down to 13% of trades (fix worked as predicted) — but **PF got WORSE (0.84 vs 1.04)**: the bleed didn't disappear, it moved into `time_limit_exit` (57% of all trades, only 38% WR) |

**The diagnosis that still holds:** the EXIT is genuine alpha (exit_signal ~90-100% WR, unchanged), the ENTRY is a coin flip (IC≈0.03-0.05). Widening the stop just gives losing entries more room to drift to the clock instead of the stop. See [[FROZEN_BASELINE_2026-06-17]] and [[reference_ic_and_edge_location]].

---

## 🧠 Brain State — every cheap lever now tried, ALL NO-GO (as of 2026-07-18)

| Attempt | Result |
|---|---|
| Threshold re-sweep (LT×ST at K_SL=3.5) | Best PF **0.822** (bull_2024Q4), still a net loser |
| K_SL re-test (2.5 / 3.0) | Best PF **0.870** (K_SL=2.5) — nominal improvement over live 0.84, still loses, nowhere near MIN_PF=1.1 |
| Partial take-profit (Lever 3) | All 4 completed runs PF 0.54–0.77 → OFF live |
| **`progress_cut`** (cut dead trades early) | Best PF **0.725** — worse than both the live baseline (0.84) and the threshold/K_SL sweep's best (0.87) |
| **`probe_scale`** (anti-martingale sizing) | 0/6 completed (all `scout_failed`) |
| Combined probe_scale + progress_cut | 0/4 completed (all `scout_failed`) |
| Meta-labeling (2nd model, act/skip filter) | AUC=0.50 — no separable signal — **dead for good** |
| Quantile entry mode / feature pruning / sample weighting | All validated OFF, no improvement |
| Shadow-account rule extraction (KMeans + decision trees on own trade history) | Mostly confirmatory NO-GO (~0-1.0x lift); one 1.94x cluster flagged as likely in-sample overfitting, not real |

`promote.py find_candidates()` has surfaced **zero** candidates across all of the above. Brain queue is currently empty (0 pending experiments).

**This closes out every remaining cheap/parameter-level lever** — thresholds, stop geometry, partial-TP, probe-scale, progress-cut, meta-labeling, quantile mode, feature pruning, sample weighting, and independent rule-extraction all point the same way: **the entry signal itself has no real edge (IC≈0.03-0.05) to extract**, whether by tuning thresholds around it or by changing how capital is committed to it.

---

## 🎯 What's Next

**The fork Gaurav himself set up on 2026-07-17 is now live:** *"if both [probe_scale, progress_cut] come back flat/negative, that's a stronger signal to seriously consider the market-neutral modules (grid/funding/pairs) as the better use of attention, since even position-sizing tricks aren't enough to rescue a coin-flip entry."* Both came back flat/negative (0.725, still below baseline). Two real paths forward — **needs Gaurav's call, not a default**:

1. **Phase 4: build genuinely NEW entry-time features** (order-flow imbalance, OI-delta/CVD, funding/basis, cross-asset lead-lag — signals the model currently cannot see at all, as opposed to re-tuning what it already sees). Per Gaurav's standing instruction: **research & scope first, bring a plan, get approval BEFORE writing any code.** Not started.
2. **Shift attention to the market-neutral paper modules** (Funding Farm, Pairs Trading, Grid Trading — all already live in paper mode, see [[project_ui_modular_redesign]]) and the platform roadmap, since directional entry-alpha may be a dead end regardless of position-sizing cleverness.

**Separately, the platform roadmap (approved 2026-07-17, see [[project_20260717_platform_roadmap]]) has its own next steps, independent of the above:**
- Phase 3 (multi-tenant DB/auth/key-vault) is **blocked on two manual steps only Gaurav can do**: `sudo -u postgres psql -f scripts/platform/bootstrap_db.sql` (creates the DB) and installing the generated KEK to `/etc/finbuddy/platform_master.key` — neither has been done yet (verified 2026-07-20). Also blocked on a Clerk signup (external account creation, not something to do automatically).
- The arbitrage feed daemon systemd service (`scripts/arbitrage/finbuddy-arb-feed.service`) is written but still **not installed/enabled** (verified inactive 2026-07-20) — needs Gaurav to run the `sudo cp ... && systemctl enable --now` step from `scripts/platform/README.md`.
- Once those unblock, next platform step is: apply the Alembic migration, verify the 9 tables exist, then the API-key connection flow + executor worker pool.

### Open / deferred (low priority)
- ~800 old-named experiment-log entries (bull_2024Q2/bull_2025Q4 pre-2026-06-19 rename) — left immutable, low impact.
- **Cortexa rebrand (2026-07-19/20):** branding/docs/UI/comments swept repo-wide + dashboard rebuilt & deployed. Deliberately left as `finbuddy_*`: the `finbuddy_memory/` directory path, the live strategy file/class, `config.json`/`docker-compose.yml`, and the FreqAI identifier strings — renaming those forces a container recreate + likely full retrain, deferred pending explicit approval. See [[project_20260719_rebrand_cortexa]].

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[FROZEN_BASELINE_2026-06-17]] · [[CONTEXT]]*
