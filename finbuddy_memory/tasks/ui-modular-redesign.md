# UI Modular Redesign — Implementation Plan

> Created 2026-06-24. Goal: restructure the dashboard so each trading edge is a
> **separate, self-explanatory module** that any non-technical user understands by
> looking at the screen alone — and that we can sell individually later.

## North-Star Design Rule (applies to EVERY screen)

**"Readable by a stranger in 5 seconds."** No screen may rely on jargon the user
must already know. Concretely, every module page MUST open with:

1. **Plain-English one-liner** — what this module does ("Earns funding fees while
   holding zero directional risk").
2. **Status badge** — `Live` / `Paper` / `Coming Soon` (color-coded, always visible).
3. **"How it makes money" micro-explainer** — one sentence + a tiny icon, collapsible.
4. **The single number that matters** — big, top-left (P&L for Live, est. APR for Farm).

Supporting rules:
- Every jargon term gets a hover tooltip (`?` icon) with a 1-line plain definition
  (e.g. "Win Rate = % of closed trades that made money").
- Every table column that shows money says the unit (USDT) and color (green up / red down).
- Empty states explain *why* it's empty, not just "No data" ("No positions yet — the
  bot is waiting for a strong enough signal").
- Dry-run/paper state is watermarked so nobody mistakes it for real money.

---

## Phase 0 — Data gaps (UI only) ✅ SHIPPED 2026-06-24 (checkpoint #1)

**Files:** `components/InfoTip.jsx` (new), `tabs/Overview.jsx`, `tabs/Performance.jsx`,
`dashboard/streamer.py` (two small read-only enrichments).

- [x] `InfoTip` component — hover/tap/focus `?` → 1-line plain definition. Reused.
- [x] Open Positions table — added `Invested` (stake_amount), `% Wallet`, `Entry`
  (open_rate), `Now` (current_rate), `Held` (now − open_timestamp). Leverage folded
  into the side badge. Empty-state explains *why* it's empty.
- [x] Recent Trades panel — added `Invested`, `Entry`, `Exit`, `P&L %`. Required
  enriching `/api/trades/recent` (open_rate/close_rate/stake_amount/leverage).
- [x] Overview stat strip — added `Streak`, `Deployed %`, `Avg Hold` (client-side from
  open trades + last-30 closed via `getRecentTrades(30)`). Grid → `xl:grid-cols-6`.
- [x] Performance tab — "Capital per Pair" table (Invested / Returned / Net / Return% /
  Trades), directly answering "how much did we put into each pair vs profit." Enriched
  `/api/performance/pair` with invested/returned/roi_pct.
- [ ] Deferred to a Phase-3 increment: Best/Worst day, P&L-by-exit-reason bar,
  long-vs-short split (needs the side-split endpoint).

**Verified:** UI build passes; streamer restarted; both enriched endpoints return the new
fields with a minted token. User must hard-refresh once (no-cache index.html).

---

## Phase 1 — Navigation architecture

Replace 8 flat tabs with a **2-group** sidebar: `Modules` (the products) and
`System` (the engine room). Each module shows its status badge in the nav itself.

## Phase 1 SHIPPED 2026-06-24 (checkpoint #2)

**Files:** `App.jsx`, `components/{Layout,Tab,StatusBadge,ModuleShell,SubTabs,ComingSoon}.jsx`,
`tabs/modules/{Directional,FundingFarm,PairsTrading,GridTrading}/index.jsx`.

- [x] Grouped nav model `{ group, id, label, status, icon, Component }` in `App.jsx`.
  Legacy hashes (#overview/#trades/#signals/#performance) map → directional.
- [x] `Layout.jsx` renders inline group labels ("MODULES" / "SYSTEM") with a divider;
  `Tab.jsx` gained a `statusBadge` slot; `StatusBadge.jsx` = Live/Paper/Soon pill.
- [x] `ModuleShell.jsx` — mandatory header (one-liner + status + "how it earns" + hero
  number). Every module wraps in it → self-explanatory header is structural.
- [x] `Directional` [Live] module = ModuleShell + `SubTabs` (Dashboard/Trades/Performance/
  Signals) reusing the existing tab components. Hero = total closed P&L.
- [x] `FundingFarm` [Paper] = full page: opportunities + active-positions tables (existing
  `/api/funding-farm` already returns positions — NO new endpoint needed) + status explainer.
- [x] `PairsTrading` / `GridTrading` [Soon] = ModuleShell + `ComingSoon` explainer (live
  preview scanners deferred to Phase 2 — no backend scanner exists yet).
- Build passes (no backend change this phase → no streamer restart). User hard-refreshes once.

### Original spec (for reference)

- New nav model: array of `{ group, id, label, status, icon, Component }`.
- `Layout.jsx` renders two labeled sections with the module badges inline.
- Module shell component (`components/ModuleShell.jsx`) — renders the mandatory
  header (one-liner + status badge + "how it makes money" + hero number) above any
  module's body. Every module page wraps its content in this shell so the
  self-explanatory header is **structurally guaranteed**, not optional.

```
Modules                         System
  ▸ Directional Trading  [Live]   ▸ Brain
  ▸ Funding Farm        [Paper]   ▸ Walk-Forward
  ▸ Pairs Trading       [Soon]    ▸ System Health
  ▸ Grid Trading        [Soon]    ▸ Settings
```

**Acceptance:** the difference between "a product" and "the plumbing" is obvious from
the nav. A user can see at a glance which modules are real vs. roadmap.

---

## Phase 2 — Module pages

### 2a. Directional Trading module `[Live]` — SHIPPED 2026-06-24 (checkpoint #3)
- [x] `tabs/modules/Directional/index.jsx` sub-tabs: Dashboard / Trades / Performance /
  Insights / Signals (reuse existing components — no logic change).
- [x] New `Insights` sub-tab (`Directional/Insights.jsx`): Long-vs-Short scorecard +
  mini equity curves; exit-reason **waterfall** ("where the edge is" — signal exits earn,
  stop-losses bleed, net line); current per-pair **exposure** bars from open trades.
- [x] New read-only endpoint `/api/performance/side-split` (long/short summary + daily
  cumulative series). Verified live: long 209 trades −32.9 USDT / 42.6% WR, short 604
  +41.9 / 40.4% — matches the known asymmetry. `getSideSplit` added to client.
- Note: per-pair exposure lives in Insights (not a separate "heatmap"); bars convey it clearly.

### 2b. Funding Farm module `[Paper]` — page SHIPPED in Phase 1; chart DEFERRED
- [x] Full page with Opportunities + Active Positions tables on existing `/api/funding-farm`
  (already returns positions — the planned `/positions` endpoint was unnecessary).
- [ ] Daily funding-income chart — DEFERRED: ledger `credit` values are currently all 0
  (accruals crediting 0), so a chart adds nothing yet. Revisit when real funding accrues.

### 2c. Pairs Trading module `[Coming Soon]` — SHIPPED 2026-06-24 (checkpoint #4)
- [x] `tabs/modules/PairsTrading/index.jsx` — explainer + **live cointegration-lite scanner
  preview** under the locked overlay. Real current data: 26 coins, 112 correlated candidates.
- [x] New read-only endpoint `/api/pairs/scan` (streamer.py): loads whitelist 1h closes
  (720h), correlation on log-returns, OLS hedge ratio beta, current spread z-score, AR(1)
  mean-reversion half-life. Pure pandas/numpy (no statsmodels). Cached 15min, runs in
  executor, fails soft. `getPairsScan` in client. Verified: DOT/FIL z=−3.0, hl 24h.
### 2d. Grid Trading module `[Coming Soon]` — SHIPPED 2026-06-24 (checkpoint #5)
- [x] `tabs/modules/GridTrading/index.jsx` — explainer + **live grid-suitability scanner
  preview**. Ranks coins by grid-friendliness (ranging but still swinging).
- [x] New read-only endpoint `/api/grid/scan` (streamer.py): per coin over 14d of 1h —
  Kaufman efficiency ratio (trendiness), hourly volatility %, range %, grid_score =
  vol·(1−ER). Pure pandas/numpy, cached 15min, executor, fails soft. `getGridScan` in client.
  Verified: ENA/UNI/NEAR top "ranging — good".

**Acceptance:** opening any module page, a stranger understands what it does and
whether it's making money, without scrolling or clicking.

---

## Phase 3 — New backend endpoints (`dashboard/streamer.py` + `api/client.js`)

Add only as each consuming UI piece needs it.

- [ ] `/api/trades/open` (enhance) — add open_rate, current_rate, stake_amount,
  wallet_pct, open_date_ts. *(May already be in FreqTrade payload — verify before adding.)*
- [ ] `/api/trades/recent` (enhance) — add open_rate, close_rate, stake_amount,
  profit_pct, regime_at_entry (join `regimes/historical_regime.parquet`).
- [ ] `/api/funding-farm/positions` (new) — parse `ledger.jsonl` → active positions
  + accumulated earnings.
- [ ] `/api/performance/side-split` (new) — long-only vs short-only daily P&L.
- [ ] `/api/performance/pair-capital` (new) — per-pair total staked / returned / net.
- [ ] `/api/system/streak` (new) — current win/loss streak from recent closed trades.
- [ ] Mirror each new endpoint in `api/client.js`.

---

## Build order (recommended)

1. Phase 0 (data gaps) — immediate, no backend risk.
2. Phase 1 (nav + ModuleShell) — the skeleton everything else hangs on.
3. Phase 2a Directional (mostly moving existing code into the shell).
4. Phase 3 endpoints for side-split / pair-capital / streak (feed 2a + Phase 0).
5. Phase 2b Funding Farm + its `/positions` endpoint.
6. Phase 2c/2d placeholders (cheap, high marketing value).

## Constraints / guardrails
- **Do NOT touch live trading logic** (strategy, .env thresholds, FreqAI). UI/backend-read only.
- Streamer changes are **read-only** endpoints — no new auth-bypass, keep `Depends(require_auth)`.
- Rebuild + nginx reload per `reference_dashboard_deploy.md` (index.html no-cache, assets immutable).
- Commit code + memory together (project rule).

## Future SaaS hook (why modular matters)
Module-per-page + status badges + self-explanatory headers = the exact shape needed to
later gate modules behind per-user subscriptions. Build the UI as if each module is a
sellable product from day one.
