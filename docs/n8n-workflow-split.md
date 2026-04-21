# N8N v3 → Signal Generator + Trade Executor split

**Status:** Plan (not yet executed)
**Target:** Refactor N8N v3 into two separate workflows
**Date:** 2026-04-21

## Goal

Today, N8N v3 does two jobs in one workflow: it computes signals and it executes trades. The Phase 1 architecture (from ADR-001) requires these to be separate. This document is the concrete plan for splitting v3 into:

- **`signal-generator`** — runs every 15 min, produces a Signal JSON per `docs/signal-contract.md`, POSTs it to the executor webhook.
- **`trade-executor`** — receives signal webhooks, loads user config from `users/user_01_gaurav.json`, decides whether to act, places orders.

No logic is deleted in the split. The two resulting workflows, put together, behave identically to v3 today. Once split, they can evolve independently.

---

## Current v3 workflow (inventory)

From memory and Telegram output, v3 contains roughly:

1. **Cron trigger** — every 15 min.
2. **FreqTrade status fetcher** — queries FreqTrade API for open trades and P&L.
3. **Binance kline fetcher** — HTTP GET on Binance public klines endpoint.
4. **Indicator calculator (code node)** — computes RSI 14, MACD 12/26/9, ATR 14 from klines. Uses consolidated `.all()` + dual-path array handling.
5. **AI signal decider** — sends indicators + context to Groq Llama 3.3 70B, gets `buy` / `sell` / `hold` + rationale.
6. **Trade decision router** — if flat: BUY or HOLD; if in position: SELL or HOLD with P&L.
7. **Trade placer** — calls FreqTrade's `forcebuy` / `forcesell` endpoint.
8. **Telegram notifier** — posts RSI/MACD/trade/P&L to chat.

These map cleanly to the split below. Nothing is thrown away.

---

## Target: `signal-generator` workflow

**Nodes (in order):**

1. **Cron trigger** — every 15 min. Unchanged.
2. **Binance kline fetcher** — unchanged (or move to a shared cache later).
3. **Indicator calculator** — unchanged.
4. **AI signal decider** — unchanged. Output is a raw decision + confidence + rationale.
5. **Signal JSON builder (new code node)** — constructs a payload matching `docs/signal-contract.md`. Must:
   - Generate a `signal_id` (UUID v4). N8N: `$randomUUID()` or use a tiny JS expression.
   - Set `schema_version: "1.0"`.
   - Set `emitted_at` to now (ISO 8601 UTC).
   - Set `user_id: "user_01_gaurav"` (hardcoded for Phase 1; later comes from a list iteration).
   - Copy pair, timeframe, side, confidence, strategy_id (`rsi_macd_ai_v1`), regime (from HMM once built; placeholder `"NEUTRAL"` until then), position_size_pct (0.02), stop_loss_atr_multiplier (2.0).
   - Populate `market_context` with price, RSI, MACD histogram, ATR 14.
   - Populate `reasoning` with AI's one-line rationale.
   - Build payload via string concatenation, NOT template literals — N8N HTTP Request `jsonBody` does not support `return` statements in expressions (documented lesson from v3).
6. **HTTP POST to executor** — `POST http://localhost:8787/signals` with `Content-Type: application/json` and the signal JSON as body.
7. **On 202 Accepted** — log to Telegram as informational: `"Signal emitted: BTC/USDT buy @ 0.82 confidence"`.
8. **On 409 Conflict** — log that the executor rejected as duplicate (this should never happen in cron mode; if it does, investigate).
9. **On any other error** — Telegram error alert.

**This workflow must NOT:**
- Call FreqTrade `forcebuy`/`forcesell`.
- Read FreqTrade's open-trade status.
- Check user capital, risk limits, or position sizing logic.
- Touch any user-specific config.

Everything user-specific moves to the executor.

---

## Target: `trade-executor` workflow

**Nodes (in order):**

1. **Webhook trigger** — `POST /signals` on path `/webhook/signals`. This is the URL used in `signal-generator`'s HTTP POST step.
2. **Signal validation (code node)** — run all 10 checks from the signal contract validation rules:
   - schema_version, signal_id UUID shape, emitted_at freshness, user_id resolvable, pair valid, side enum, confidence ≥ user threshold, strategy_id active, regime allowed, position cap.
   - On any failure: respond with 400/409 and exit.
3. **Idempotency check (code node + SQLite)** — look up `signal_id` in a `seen_signals` table. If present, respond 409 and exit. If not, insert and continue.
4. **User config loader (code node)** — read `users/user_01_gaurav.json` from disk (N8N file ops) or env var. Extract risk params, exchange creds env names, notification config.
5. **FreqTrade status fetcher** — query FreqTrade API for open trades in this pair for this user.
6. **Trade decision router** —
   - If `side == "hold"`: log to SQLite, notify Telegram if configured, exit.
   - If `side == "buy"` and no position: continue to position sizing.
   - If `side == "buy"` and position exists: treat as hold (don't double-buy), log, exit.
   - If `side == "sell"` and position exists: continue to close logic.
   - If `side == "sell"` and no position: log "sell signal with no open position", exit.
7. **Position sizing (code node)** — compute order quantity from `allocated_usd * max_risk_per_trade_pct / (price * stop_loss_atr_multiplier * atr_14)`. Cap at `max_concurrent_positions` and `max_position_size_pct`.
8. **Trade placer** — call FreqTrade `forcebuy` / `forcesell` with computed size. (Later in Phase 1: replace with a direct ccxt call from a Python executor, making FreqTrade optional.)
9. **Trade log writer** — append to SQLite `trades` table: signal_id, user_id, pair, side, size, price, timestamp, result.
10. **Telegram notifier** — send formatted message with signal reasoning + execution result + running P&L.
11. **Respond with 202** to the webhook.

**This workflow must NOT:**
- Fetch market data (klines).
- Compute indicators.
- Call the AI.
- Make any trading decision based on its own analysis — it only acts on signals it received.

---

## Migration steps

Do these in order. Each step leaves the system in a working state.

### Step 1: duplicate v3 as `v3-backup` and keep it active

Disable no workflows. Current v3 keeps running. `v3-backup` is a safety net.

### Step 2: build `trade-executor` in parallel (v3 still running)

Create a new workflow named `trade-executor`. Wire up all 11 nodes above. At first, its webhook is not called by anyone. Manually fire test signals from Postman / curl to verify:

```bash
curl -X POST http://localhost:8787/webhook/signals \
  -H "Content-Type: application/json" \
  -d @test-signal-hold.json
curl -X POST http://localhost:8787/webhook/signals \
  -H "Content-Type: application/json" \
  -d @test-signal-buy.json
```

Verify logs, SQLite writes, Telegram notifications all happen correctly. Do this with `paper_trade: true` in the user config so no real orders are placed during testing.

### Step 3: build `signal-generator` in parallel (v3 still running)

Create a new workflow named `signal-generator`. Wire up all 9 nodes. Its HTTP POST targets the executor's webhook. Activate the cron trigger but keep v3 also running.

For the first day, both v3 and `signal-generator + trade-executor` run in parallel. The executor is in `paper_trade: true` so no duplicate trades. This is the shadow mode.

### Step 4: verify parity

For 24 hours, compare:
- Did both pipelines generate the same buy/sell/hold decisions?
- Did indicators match?
- Did Telegram messages say the same things?

Any mismatches → fix in the new pipeline, not v3.

### Step 5: cut over

- Disable v3.
- Flip `paper_trade` to `false` in the user config.
- Leave `v3-backup` disabled but present for 1 week as emergency rollback.
- Delete `v3-backup` after 1 week of clean operation.

### Step 6: commit

Git commit on the server:
```
git add .
git commit -m "Refactor: split N8N v3 into signal-generator + trade-executor per ADR-001"
git push
```

---

## N8N-specific gotchas to remember during the refactor

1. **Array handling in code nodes** — always use `.all()` with dual-path array handling in a single consolidated code node. Manual execution and cron execution handle arrays differently.
2. **HTTP Request `jsonBody` does NOT support `return` statements** — build payloads in a separate code node using string concatenation, not template literals. Pass the stringified JSON into the HTTP Request node.
3. **N8N API `/api/v1/workflows` scope** — workflows in named projects won't show up via API. If using the N8N API to script deployment, workflows must live in the default project space, or you must use direct URL access.
4. **Dead weight audit** — after this split, delete any residual duplicate workflows, Dify leftovers, and unrelated video-generation workflows sitting in N8N. Periodic hygiene.

---

## Definition of done

- [ ] `signal-generator` runs every 15 min and POSTs valid Signal JSON to the executor.
- [ ] `trade-executor` webhook accepts signals, validates, dedupes, sizes, and places orders.
- [ ] v3 is disabled. `v3-backup` deleted after 1 week.
- [ ] Telegram messages after split are at least as informative as before.
- [ ] All user-specific config is in `users/user_01_gaurav.json` and nowhere else.
- [ ] No hardcoded API keys, chat IDs, capital, or risk values in any workflow node.
- [ ] Git committed on the server with commit message referencing ADR-001.
