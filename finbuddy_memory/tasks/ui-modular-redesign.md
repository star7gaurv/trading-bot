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

**Files:** `dashboard-ui/src/App.jsx`, `components/Layout.jsx`

- [ ] New nav model: array of `{ group, id, label, status, icon, Component }`.
- [ ] `Layout.jsx` renders two labeled sections with the module badges inline.
- [ ] Module shell component (`components/ModuleShell.jsx`) — renders the mandatory
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

### 2a. Directional Trading module `[Live]`
Absorbs today's Overview / Trades / Signals / Performance as **sub-tabs** under one
module. Header one-liner: *"Predicts price direction and trades long or short."*
- [ ] `tabs/modules/Directional/index.jsx` with sub-tabs: Dashboard / Trades / Performance / Signals.
- [ ] Move existing Overview/Trades/Signals/Performance content under it (mostly file moves).
- [ ] New: Long-vs-Short equity curves (needs Phase 3 `/api/performance/side-split`).
- [ ] New: per-pair exposure heatmap (capital in each pair right now).
- [ ] New: exit-reason waterfall (signal wins vs SL losses → net) — make the
  "exits are the edge, entries are coin flips" story legible to a stranger.

### 2b. Funding Farm module `[Paper]`
Currently a small card → becomes a full page. Header one-liner:
*"Collects funding fees with no bet on price direction — market-neutral."*
- [ ] `tabs/modules/FundingFarm/index.jsx`.
- [ ] Opportunities table: pair, current APR, 7d-avg APR, threshold status (from
  existing `/api/funding-farm`).
- [ ] Active paper positions: pair, entry date, accumulated funding earned, est. APR
  (needs Phase 3 `/api/funding-farm/positions` reading `finbuddy_memory/funding_farm/ledger.jsonl`).
- [ ] Daily funding-income chart from the ledger.

### 2c. Pairs Trading module `[Coming Soon]`
- [ ] `tabs/modules/PairsTrading/index.jsx` — locked overlay, plain-English explainer
  (*"Bets that two related coins drift back together — wins whether the market goes
  up or down"*), optional live cointegration-scanner preview, "Notify me" static CTA.

### 2d. Grid Trading module `[Coming Soon]`
- [ ] `tabs/modules/GridTrading/index.jsx` — same locked pattern. Explainer:
  *"Profits from a coin bouncing inside a range — no direction guess needed."*

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
