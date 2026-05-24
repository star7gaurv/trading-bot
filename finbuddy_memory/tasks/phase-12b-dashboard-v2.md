# Phase 12b — Dashboard v2: Professional Trading Console

**Status:** 🟡 IN PROGRESS — started 2026-05-24
**Supersedes:** Phase 12 v1 (kept as history at `phase-12-brain-dashboard.md`)
**Plan reference:** `/home/ubuntu/.claude/plans/5-24-2026-12-00-am-star7gaurav-gleaming-rain.md`

---

## Goal

Rebuild the FinBuddy dashboard from scratch as a compact, dense, Binance-class trading console. Mirror every relevant FreqTrade UI feature, add full system-health visibility for all 24 crons + 3 processes, dedicated views for Brain and Walk-Forward, password-gated.

**Stack stays:** React 19 + Vite + Tailwind + FastAPI streamer + nginx. No framework changes.

---

## Why v2 (what v1 missed)

| v1 (shipped 2026-05) | v2 (this redesign) |
|---|---|
| 3 panels in one view | 7 tabs (Overview, Trades, Performance, Brain, Walk-Forward, System Health, Settings) |
| Heavy neon glow, animated mesh background | Restrained dark theme, single muted accent, information-density-first |
| Only 3 data sources (regime, F&G, open trades, log feed) | Full FreqTrade API mirror + brain queue + WF results + cron health + system stats |
| Public URL | Password-gated (JWT) |
| Zero visibility into background cron jobs | Live System Health tab with all 24 crons + last-run + log tail |
| `App.jsx` = 268 LOC single file | Decomposed into `tabs/` + `components/` + `api/` tree |

---

## Design Tokens (Claude-designed, from scratch)

| Token | Value |
|---|---|
| Canvas | `#0a0d11` |
| Surface | `#13171c` |
| Elevated | `#1a1f26` |
| Hover | `#222831` |
| Border default | `#1f242b` |
| Border emphasis | `#2b323b` |
| Accent | `#3b82f6` |
| Profit | `#22c55e` |
| Loss | `#ef4444` |
| Warn | `#f59e0b` |
| Text primary | `#f1f5f9` |
| Text secondary | `#94a3b8` |
| Text tertiary | `#64748b` |
| Text muted | `#475569` |
| Sans font | Inter (variable, Google Fonts) |
| Mono font | JetBrains Mono |
| Spacing | 4 / 8 / 12 / 16 / 24 / 32 px |
| Type sizes | 11 / 12 / 13 / 14 / 16 / 20 / 28 px |

---

## Sub-Tasks

### Increment 1 — Foundation
- `[ ]` Design tokens — `dashboard-ui/src/styles/tokens.css` + Tailwind config extend
- `[ ]` Google Fonts: Inter + JetBrains Mono (via `index.html`)
- `[ ]` Shared components in `dashboard-ui/src/components/`:
  - `[ ]` `Layout.jsx` — sticky top nav + tab bar + content area
  - `[ ]` `Tab.jsx` — horizontal tab control
  - `[ ]` `Stat.jsx` — dense stat block (label + value + delta + sparkline)
  - `[ ]` `Table.jsx` — sortable, sticky-header, compact
  - `[ ]` `Card.jsx` — surface with header (title + last-updated + actions)
  - `[ ]` `Badge.jsx` — color-coded chip
  - `[ ]` `Sparkline.jsx` — SVG mini-chart
  - `[ ]` `LogStream.jsx` — virtualized log feed
  - `[ ]` `LoginGate.jsx` — password screen
- `[ ]` API client + hooks scaffold:
  - `[ ]` `dashboard-ui/src/api/client.js` — fetch wrapper with auth header
  - `[ ]` `dashboard-ui/src/api/hooks.js` — useTrades, useCronStatus, useBrainQueue, etc.
- `[ ]` Backend auth:
  - `[ ]` `dashboard/auth.py` — JWT generate/validate (use `python-jose` or `PyJWT`)
  - `[ ]` Login endpoint in `streamer.py`
  - `[ ]` Token middleware for `/api/*` routes
  - `[ ]` Add `DASHBOARD_PASSWORD` env var (systemd service file or `.env`)
- `[ ]` Tab shell — all 7 tabs render content stubs

### Increment 2 — Overview + System Health
- `[ ]` `tabs/Overview.jsx`:
  - `[ ]` Top stat row: P&L today / 7d / 30d, WR, open positions, regime, F&G
  - `[ ]` Live trades mini-table (5 rows max)
  - `[ ]` Brain status card
  - `[ ]` WF status card
  - `[ ]` System health summary card
- `[ ]` `tabs/SystemHealth.jsx`:
  - `[ ]` Cron table (name, schedule, last run, status, log tail)
  - `[ ]` Processes table (FreqTrade, streamer, brain backtests)
  - `[ ]` Server stats (load, disk, memory)
  - `[ ]` Watchdog status + alert history
- `[ ]` Backend endpoints:
  - `[ ]` `GET /api/cron/status` — parse crontab + tail logs
  - `[ ]` `GET /api/system/health` — uptime + df + free + docker ps
  - `[ ]` `GET /api/brain/queue` — read `queue.jsonl`
  - `[ ]` `GET /api/wf/latest` — most recent summary.json
- `[ ]` `dashboard/cron_status.py` + `dashboard/system_health.py`
- `[ ]` 30s in-memory cache for expensive endpoints

### Increment 3 — Trades + Performance
- `[ ]` `tabs/Trades.jsx`:
  - `[ ]` Open trades table (with force-exit)
  - `[ ]` Closed trades table (paginated, sortable, filterable)
  - `[ ]` Per-pair performance
  - `[ ]` Trade detail drawer
- `[ ]` `tabs/Performance.jsx`:
  - `[ ]` Cumulative P&L chart (lightweight-charts)
  - `[ ]` Daily / Weekly / Monthly P&L tables
  - `[ ]` Per-pair P&L bar chart
  - `[ ]` Per-regime P&L breakdown
  - `[ ]` WR over time
- `[ ]` Backend endpoints:
  - `[ ]` `GET /api/trades/closed?limit&offset` — proxy + paginate
  - `[ ]` `GET /api/performance/daily?days=30`
  - `[ ]` `GET /api/performance/pair`
- `[ ]` Add `lightweight-charts` to npm dependencies

### Increment 4 — Brain + Walk-Forward
- `[ ]` `tabs/Brain.jsx`:
  - `[ ]` Queue summary
  - `[ ]` Recent experiments table
  - `[ ]` Promotion candidates (if any)
  - `[ ]` Brain log stream (reuse existing `/ws/brain`)
- `[ ]` `tabs/WalkForward.jsx`:
  - `[ ]` Latest run header with PASS/FAIL gates
  - `[ ]` Fold-by-fold metrics
  - `[ ]` Historical runs list
  - `[ ]` Trend chart
- `[ ]` Backend endpoints:
  - `[ ]` `GET /api/brain/experiments?limit=50`
  - `[ ]` `GET /api/wf/history`

### Increment 5 — Settings + Polish
- `[ ]` `tabs/Settings.jsx` (read-only):
  - `[ ]` Current env vars
  - `[ ]` Current pair_whitelist
  - `[ ]` Current FreqAI identifier
  - `[ ]` Live thresholds
- `[ ]` Mobile responsiveness pass
- `[ ]` Empty states + error states + loading skeletons for every panel
- `[ ]` Final type/spacing audit

---

## Files to Create / Modify

```
dashboard-ui/src/
  App.jsx                          # rewrite — tab state + LoginGate + Layout
  api/
    client.js                      # NEW
    hooks.js                       # NEW
  components/
    Layout.jsx Tab.jsx Stat.jsx Table.jsx Card.jsx Badge.jsx
    Sparkline.jsx Chart.jsx LogStream.jsx LoginGate.jsx   # all NEW
  tabs/
    Overview.jsx Trades.jsx Performance.jsx Brain.jsx
    WalkForward.jsx SystemHealth.jsx Settings.jsx          # all NEW
  styles/
    tokens.css base.css                                    # NEW
dashboard-ui/tailwind.config.js   # extend with tokens
dashboard-ui/index.html            # Inter + JetBrains Mono Google Fonts

dashboard/
  streamer.py                      # extend with REST + auth middleware
  auth.py                          # NEW — JWT
  cron_status.py                   # NEW
  system_health.py                 # NEW

finbuddy_memory/tasks/
  phase-12b-dashboard-v2.md        # this file
  TASKS.md                         # update Phase 12 line

CLAUDE.md                          # mention dashboard v2 in "What Is Live"
finbuddy_memory/FINBUDDY_PROJECT_MEMORY.md  # session entry
```

---

## Verification

Run after each increment:
```bash
# 1. Build succeeds
cd dashboard-ui && npm run build

# 2. Streamer running with new endpoints
curl -X POST https://trade.star7gaurav.in/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "<DASHBOARD_PASSWORD>"}' | jq .token
# → save token to TOKEN env var

# 3. Smoke-test each endpoint
curl -H "Authorization: Bearer $TOKEN" https://trade.star7gaurav.in/api/cron/status | jq .
curl -H "Authorization: Bearer $TOKEN" https://trade.star7gaurav.in/api/system/health | jq .

# 4. Open in browser, verify:
#    - LoginGate appears in incognito
#    - All tabs load < 500ms
#    - System Health shows recent timestamps for every cron
#    - Trades tab matches FreqTrade /api/v1/status
```

---

## Constraints (non-negotiable)

- ❌ No framework swap — React + Vite + Tailwind only
- ❌ No React Router — tab state via `useState`
- ❌ No heavy component library (MUI, Ant) — components built from scratch
- ❌ FreqTrade auth never exposed to client — proxied via streamer
- ❌ No giant single commit — five incremental commits
- ❌ Existing `/ws/brain` + `/ws/memory` contracts preserved (Brain tab reuses them)

---

*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]] · [[tasks/phase-12-brain-dashboard]] (v1 history)*
