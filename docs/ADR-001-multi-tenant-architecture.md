# ADR-001: Multi-Tenant Architecture for Jarvis SaaS

**Status:** Proposed
**Date:** 2026-04-21
**Deciders:** Gaurav (sole builder)

---

## Context

Jarvis is currently a single-tenant crypto trading system: one FreqTrade instance + N8N workflow orchestration, running on an Oracle Free Tier ARM64 box, trading Gaurav's own account in dry-run mode. The long-term goal is to evolve it into a multi-tenant SaaS platform for non-technical retail crypto traders who want "set it, forget it, earn money" — users who connect their own exchange account (non-custodial) and rely on Jarvis to run trades for them.

The core architectural question is: **how does a single Jarvis instance serve N users without the cost or complexity scaling linearly with N, while still delivering high-quality trading results?**

### Forces at play

- **Hard cost ceiling.** Infra target is ~$3–5/month total across all users. Oracle Free Tier (4 OCPUs ARM, 24GB RAM) is the home base; anything that requires paid infra is a last resort.
- **Non-custodial mandate.** Users keep their funds on their own exchange. Jarvis only gets trade-permission API keys (no withdrawal). This is both a trust and a regulatory requirement.
- **Single-operator reality.** Gaurav is solo, works from mobile via Termius SSH. Operational complexity must be low enough to debug from a phone.
- **"Don't replace, extend" principle.** Existing FreqTrade + N8N + Karpathy loop stays. The question is how to fan out execution, not whether to rewrite the brain.
- **Quality > feature breadth.** Users don't pick strategies. Jarvis does. This means the expensive compute (HMM regime engine, Karpathy auto-research loop, AI signals) can be centralized — every user benefits from one great brain, not N mediocre ones.
- **Isolation matters.** One user's bad config, exhausted API rate limit, or exchange outage must not cascade to others.

### Current resource envelope (single-user baseline)

- FreqTrade container: ~250MB RAM idle, ~400MB active, ~3–5% CPU
- N8N container: ~200MB RAM, spikes on cron runs
- Market data: one Binance connection pulling klines for ~20 pairs on the 15m cadence
- AI inference: Groq Llama 3.3 70B free tier (external, not on-box)

---

## Decision

Adopt **Option C: Signal-as-a-Service + thin per-user executor**, delivered in **two phases**:

**Phase 1 (now → ~6 months): Single-user, multi-tenant-shaped.** Build the full Option C architecture, but deploy it with exactly one user — Gaurav. No signup flow, no billing, no dashboard, no user management UI. The *shape* of the code is already multi-tenant (signal service separate from executor, user identity is a parameter, signal contract is a defined JSON schema), but the *deployment* is single-user. This is the live public track-record phase. FreqTrade continues in parallel as the research environment.

**Phase 2 (after 6 months of live track record): Multi-tenant activation.** Add the glue that turns a multi-tenant-shaped system into an actual multi-tenant product: user signup, API-key encryption, paper-trading mode for new users, billing, dashboard. The core brain and executor do not change. Adding user 2 is a config file, not a rewrite.

Rationale for phasing: Option C's scaling and quality benefits matter only at scale, but Option C's *shape* matters from day one — because retrofitting the shape later is the expensive move. Building in Phase 1 shape costs maybe 10–20% more effort than a hacked-together single-user script, but avoids a 2–4 week rewrite in Phase 2.

---

## Options Considered

### Option A: FreqTrade-per-user (container isolation)

Each user gets their own Docker container running FreqTrade with their own config and API key.

| Dimension | Assessment |
|---|---|
| Complexity | Low (familiar pattern) |
| RAM per user | ~300–400MB |
| Users per Oracle box | ~40–50 before RAM is exhausted |
| CPU per user | 2–5% idle, spikes on bar close |
| Market data cost | N × the same Binance kline fetches (wasteful, rate-limit risk) |
| Karpathy loop | Must be shared externally or duplicated (expensive if duplicated) |
| Blast radius | Good — containerized |
| Scale cost | Linear: hits paid infra around 40 users |

**Pros:**
- Each user is fully isolated.
- FreqTrade is battle-tested as a single-user bot.
- No custom execution code needed — just spawn containers.

**Cons:**
- Catastrophic resource inefficiency: N copies of identical market data pipelines, indicator calculations, and strategy evaluations.
- Forces "one bot per user" mental model, which is the wrong shape for an AI-driven shared-intelligence product.
- Binance API rate limits become a real worry at scale (each container polls independently).
- Hits the free-tier ceiling fast — 40–50 users and you're paying for another box.
- Operationally painful: N containers to monitor, update, debug from a phone.

---

### Option B: Shared FreqTrade pool (multi-tenant fork)

Modify FreqTrade (or build a shim around it) so a single instance serves multiple users with per-user configs and API keys routed internally.

| Dimension | Assessment |
|---|---|
| Complexity | High (FreqTrade is not designed for this) |
| RAM per user | Low marginal (~20–40MB) |
| Market data cost | Shared (good) |
| Karpathy loop | Naturally shared |
| Blast radius | Poor — one bug affects all users |
| Scale cost | Good |
| Engineering cost | Very high — fork maintenance forever |

**Pros:**
- Resource-efficient at runtime.
- Single process to monitor.

**Cons:**
- FreqTrade's internals assume one user. Retrofitting multi-tenancy is a fork that must be re-rebased with every upstream release — a permanent tax on a solo builder.
- Violates "don't replace, extend" — this is deep modification.
- A single crash kills trading for everyone.
- Account state (trades, P&L, risk limits) becomes tangled inside FreqTrade's data model.

---

### Option C: Signal-as-a-Service + thin per-user executor  ← **recommended**

One central brain publishes trading signals to a message queue / webhook. Each user has a lightweight executor (a few hundred lines of Python, or even a serverless function) that subscribes to signals, sizes the position against their capital and risk profile, and places the trade via their own Binance API key.

```
┌────────────────────────────────────────────────┐
│  CENTRAL BRAIN (runs once on Oracle Free Tier) │
│  - Market data feed (one Binance connection)   │
│  - HMM regime detection engine                 │
│  - Karpathy auto-research loop                 │
│  - AI signal generation (Groq/Gemini/DeepSeek) │
│  - Strategy promotion logic                    │
│  → publishes signals: {pair, side, confidence, │
│    stop_loss, regime_tag, strategy_id}         │
└────────────────────┬───────────────────────────┘
                     │
              [message bus / webhook]
                     │
      ┌──────────────┼──────────────┐
      ▼              ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Executor │   │ Executor │   │ Executor │
│  user 1  │   │  user 2  │   │  user N  │
│          │   │          │   │          │
│ - filter │   │ - filter │   │ - filter │
│ - size   │   │ - size   │   │ - size   │
│ - trade  │   │ - trade  │   │ - trade  │
└────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │
     ▼              ▼              ▼
  Binance       Binance        Binance
  (user 1       (user 2        (user N
   API key)      API key)       API key)
```

| Dimension | Assessment |
|---|---|
| Complexity | Medium (build lightweight executor, keep brain) |
| RAM per user | 20–50MB (or $0 serverless) |
| Users per Oracle box | ~500–1,000+ |
| Market data cost | O(1) — one feed for everyone |
| Karpathy loop | Centralized, O(1) |
| Blast radius | Excellent — user data, keys, balances all isolated |
| Scale cost | Near-flat well past 1,000 users |
| Engineering cost | Medium upfront, low ongoing |

**Pros:**
- **O(1) on the expensive parts.** One market data feed, one HMM engine, one Karpathy loop — cost of the brain does not grow with user count.
- **Better results, not just cheaper.** Centralization concentrates compute: the brain can run heavier models, more backtests, more data sources than N weaker per-user brains could. Quality improves with scale rather than degrading.
- **User isolation is natural.** Each user's API key, capital, risk profile, and trade history live in their executor's scope. No shared mutable state to corrupt.
- **Each user's Binance rate limit is their own.** The central brain uses *public* market data (no auth); each user's executor uses only that user's API quota. Rate-limit issues don't cascade.
- **Fits the "don't replace, extend" principle in a deeper sense.** FreqTrade remains the research environment on Gaurav's account. The SaaS is a *different product surface* built around the same brain.
- **Natural path to serverless.** Executors are so light they can be Cloudflare Workers, Deno Deploy, or AWS Lambda free tier — $0 marginal cost per user for the execution layer.
- **Operational simplicity.** One brain process to monitor. Executor failures are per-user and self-healing on next signal.

**Cons:**
- Must build a custom executor (≈500 LOC Python + ccxt). Less battle-tested than FreqTrade.
- Central brain is a single point of failure for signal generation. Mitigation: executors cache the last signal and skip trading rather than error; brain restart is fast.
- Harder to offer "custom strategies per user" — by design, everyone uses the central brain's strategies. This is actually aligned with the "user doesn't pick strategies" product decision from the brainstorm; flagged here as a design constraint, not a defect.
- Requires a message bus or webhook layer (can be minimal: Redis pub/sub, or even just HTTP POST to executor endpoints).

---

## Trade-off Analysis

The real decision is between **A (easy, doesn't scale)** and **C (more engineering, scales near-flat)**. Option B is a trap — it gets the runtime efficiency of C with the engineering burden of forking FreqTrade forever, and it's the worst of both worlds.

**A vs. C on the two constraints that matter:**

| | Option A (FreqTrade per user) | Option C (SaaS + executor) |
|---|---|---|
| Cost at 10 users | Oracle Free Tier, fine | Oracle Free Tier, fine |
| Cost at 100 users | Needs 2–3 paid boxes (~$40/mo) | Still Oracle Free Tier (~$0) |
| Cost at 1,000 users | Needs 20+ boxes (~$400/mo) | One box + maybe CDN (~$5/mo) |
| Quality of signals | Each user gets an independent mediocre brain | Every user gets the best brain |
| Time to first user | ~2 weeks | ~4–6 weeks |

The time delta (A is faster to first user) is the only real cost of choosing C, and it's recoverable within the first 3 months because Option C doesn't require rewriting when scaling up.

**Quality argument is underweighted.** Resource efficiency is the obvious C benefit, but the hidden benefit is that centralized intelligence produces *better* trading results. One brain with full compute can run walk-forward backtests across the entire strategy library nightly. N weak brains each get a fraction of that compute. For a product whose promise is "we trade better than you could," this matters more than cost.

---

## Consequences

**What becomes easier:**
- Adding a user is `INSERT INTO users`, not `docker run`.
- Improving strategy quality benefits every user instantly.
- Monitoring: one brain, one log stream to watch. Per-user issues are isolated to their executor's logs.
- Shipping a "paper trading" mode: executor just skips the actual order placement. No new infra.
- Walk-forward backtesting becomes a first-class feature of the brain, not something retrofit into FreqTrade.
- Non-custodial story is architecturally enforced: executor literally cannot withdraw even if compromised, because API keys are scoped that way.

**What becomes harder:**
- Custom per-user strategies — not supported by default. Users get a choice of risk levels, not a choice of strategies. (Aligned with the product direction, but named here.)
- Migrating Gaurav's existing N8N-driven setup to the new shape — need to decouple "signal generation" from "trade execution" in the current pipeline, which are currently entangled in the v3 workflow.
- Testing: must simulate the full pipeline (brain → bus → executor → fake Binance). More moving parts than a single FreqTrade container.

**What we'll need to revisit:**
- Whether the message bus is Redis pub/sub, a managed service, or raw webhooks. Start with webhooks for simplicity.
- Whether executors run on the same Oracle box or as serverless functions. Start same-box; move to serverless when user count justifies it (probably >100).
- FreqAI role. Currently dormant. In this architecture, FreqAI would live *inside the central brain* as a signal source, not per-user. Its empty `freqaimodels/` folder is actually a green-field opportunity here.

---

## Action Items

### Phase 1 — Single-user, multi-tenant-shaped (do now)

**Build these in multi-tenant shape from day one.** Deploy with one user (Gaurav).

1. [ ] **Finish the Trade Event Handler N8N import** (existing loose end). Get the FreqTrade Webhook Production URL and complete the workflow. This closes out v3 and gives a clean baseline to refactor from.
2. [ ] **Define the signal JSON contract.** Spec it in a file (`docs/signal-contract.md` in the repo) before writing any code. Required fields: `signal_id` (UUID), `user_id`, `pair`, `side` (buy/sell/hold), `confidence` (0-1), `regime` (CRASH/BEAR/NEUTRAL/BULL/EUPHORIA), `strategy_id`, `stop_loss_atr_multiplier`, `position_size_pct`, `timestamp`. This is the single most important artifact — everything downstream depends on it.
3. [ ] **Decouple signal generation from execution in N8N.** Split v3 into two separate workflows: `signal-generator` (runs every 15m, produces signals conforming to the contract, writes to a queue or POSTs to a webhook) and `trade-executor` (subscribes, applies user-scoped risk params, places orders). No user-specific code inside `signal-generator`.
4. [ ] **Introduce the `users/` config directory.** Create `users/user_01_gaurav.json` with: `binance_api_key`, `binance_api_secret` (env var reference, not literal), `capital_usd`, `max_risk_per_trade_pct` (2% per Turtle), `max_drawdown_pct`, `active_strategies: [strategy_ids]`, `notification_telegram_chat_id`. Everything personal lives here — nothing hardcoded in workflows or strategies.
5. [ ] **Build a minimal Python executor** (~300–500 LOC) that: reads a user config, subscribes to the signal bus (start with HTTP webhook), dedupes on `signal_id`, sizes positions using 2% rule + ATR, places orders via ccxt, logs to SQLite. Run it on the Oracle box alongside FreqTrade — don't replace FreqTrade yet.
6. [ ] **Create a strategy registry.** `strategies/registry.json` listing each strategy with an ID, description, and activation status. Signals reference strategies by ID. The Karpathy loop promotes/demotes strategies by updating this registry.
7. [ ] **Add idempotency from day one.** Executor maintains a "seen signal IDs" set (SQLite table). Duplicate signal IDs are logged and skipped. Test by intentionally retransmitting a signal during development.
8. [ ] **Keep FreqTrade running in parallel as the research environment.** Executor trades are the "official" Jarvis trades. FreqTrade continues to be where you prototype new strategies before adding them to the registry.
9. [ ] **Run the live public track record** on Gaurav's own capital using the new executor. Six months minimum before Phase 2.

### Phase 2 — Multi-tenant activation (after 6 months of track record)

These are deferred until the track record exists. Creating an ADR for each when the time comes.

10. [ ] **Onboarding + non-custodial Binance connection flow** (separate ADR).
11. [ ] **API-key encryption at rest** (KMS or libsodium box).
12. [ ] **Paper-trading mode for new users** — executor variant that logs trades but doesn't call Binance.
13. [ ] **Billing + subscription management.**
14. [ ] **User-facing dashboard** — read-only view of their trades, P&L, active strategies, risk settings.
15. [ ] **Revisit at 100 users:** decide on message bus upgrade (Redis pub/sub), whether to push executors to serverless (Cloudflare Workers), and whether Postgres is needed.

### Phase 1 non-goals (explicitly NOT doing now)

- No user signup or login.
- No web UI beyond the existing FreqTrade dashboard.
- No payment integration.
- No API-key encryption (use env vars — fine for one user).
- No message bus beyond direct HTTP webhook on localhost.
- No Postgres — SQLite is enough.
- No Kubernetes, no microservices, no containers per user. Just processes on the Oracle box.

---

## Decision Context (for future-you)

This ADR is the answer to "what shape does Jarvis take when it stops being a bot for one person and becomes a product for many." The short version: **don't clone the bot per user. Separate the brain from the hands. One brain, many hands.** The brain gets smarter over time and every user inherits that improvement; the hands stay dumb, cheap, and isolated.

**On the single-user-first approach:** the whole point of Phase 1 is that you get to ship *immediately* (no SaaS complexity) but do not accumulate architectural debt you'll have to pay back later. The rule of thumb: if you catch yourself writing `my_api_key`, `my_capital`, `my_telegram_id` anywhere outside a user config file, stop. That's a Phase 1 violation and will cost weeks in Phase 2.

If in six months you find yourself considering per-user strategy customization, that is the signal that this architecture needs to evolve — probably toward "strategy tiers" (conservative / balanced / aggressive) rather than per-user tuning, to preserve the O(1) brain property.
