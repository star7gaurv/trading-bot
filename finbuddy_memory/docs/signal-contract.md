# FinBuddy Signal Contract v1

**Status:** Draft — not yet implemented
**Last updated:** 2026-04-21
**Owner:** Gaurav

The signal contract is the public API between FinBuddy's **signal generator** (the brain) and its **trade executor** (the hands). Every trading decision flows through this JSON structure. Once an executor accepts a signal, the signal's fields determine exactly what happens.

This contract is **versioned**. Breaking changes require bumping the version and running both versions in parallel during migration. `schema_version` is a required field for forward compatibility.

---

## Schema (v1)

```json
{
  "schema_version": "1.0",
  "signal_id": "550e8400-e29b-41d4-a716-446655440000",
  "emitted_at": "2026-04-21T12:00:00Z",

  "user_id": "user_01_gaurav",

  "pair": "BTC/USDT",
  "timeframe": "15m",
  "side": "buy",

  "confidence": 0.78,
  "regime": "BULL",
  "strategy_id": "rsi_macd_ai_v1",

  "position_size_pct": 0.02,
  "stop_loss_atr_multiplier": 2.0,
  "take_profit_atr_multiplier": 4.0,

  "market_context": {
    "price": 67234.50,
    "rsi": 58.2,
    "macd_histogram": 0.0034,
    "atr_14": 1245.30
  },

  "reasoning": "RSI neutral-bullish, MACD crossover confirmed, HMM regime = BULL, AI agrees."
}
```

---

## Field reference

### Meta fields

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | Contract version. Currently `"1.0"`. Executors reject unknown versions. |
| `signal_id` | string (UUID v4) | yes | Globally unique. **Executors dedupe on this.** Same ID twice = ignore second. |
| `emitted_at` | string (ISO 8601 UTC) | yes | When the signal generator produced this. Executors reject signals older than 10 minutes. |

### Routing

| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | yes | Which user this signal is for. Format: `user_<NN>_<handle>`. Phase 1 always `user_01_gaurav`. |

### Trade intent

| Field | Type | Required | Description |
|---|---|---|---|
| `pair` | string | yes | Trading pair in `BASE/QUOTE` format, e.g. `"BTC/USDT"`. Must exist on user's exchange. |
| `timeframe` | string | yes | Candle timeframe the signal was computed on: `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"`. |
| `side` | enum | yes | One of: `"buy"`, `"sell"`, `"hold"`. Executor skips on `"hold"` but still logs the signal. |

### Decision quality

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence` | float 0.0–1.0 | yes | Signal generator's confidence. Executor may filter by user's min-confidence threshold. |
| `regime` | enum | yes | HMM regime classification: `"CRASH"`, `"BEAR"`, `"NEUTRAL"`, `"BULL"`, `"EUPHORIA"`. |
| `strategy_id` | string | yes | ID from `strategies/registry.json`. Used for P&L attribution and A/B testing. |

### Risk parameters

| Field | Type | Required | Description |
|---|---|---|---|
| `position_size_pct` | float 0.0–1.0 | yes | Fraction of user's capital to risk. Default 0.02 (Turtle 2% rule). |
| `stop_loss_atr_multiplier` | float | yes | Stop-loss distance as a multiple of ATR. Default 2.0. |
| `take_profit_atr_multiplier` | float | no | Take-profit distance as a multiple of ATR. If omitted, executor uses strategy default. |

### Market snapshot (for debugging / future ML input)

| Field | Type | Required | Description |
|---|---|---|---|
| `market_context.price` | float | yes | Spot price at signal emission. |
| `market_context.rsi` | float | no | 14-period RSI at emission. |
| `market_context.macd_histogram` | float | no | MACD histogram value. |
| `market_context.atr_14` | float | yes | 14-period ATR. Executor uses this for stop-loss placement. |

### Human-readable

| Field | Type | Required | Description |
|---|---|---|---|
| `reasoning` | string | no | One-sentence human-readable rationale. For Telegram notifications and debugging. Max 500 chars. |

---

## Transport

**Phase 1:** HTTP POST from signal-generator to executor. Executor runs a webhook endpoint at `http://localhost:8787/signals`.

**Phase 2 (future):** Redis pub/sub or a managed message broker. The JSON payload does not change — only the transport.

### HTTP transport details

- Method: `POST`
- URL: `http://localhost:8787/signals`
- Headers:
  - `Content-Type: application/json`
  - `X-Signal-Source: signal-generator` (for log correlation)
- Body: the signal JSON above.
- Expected response: `202 Accepted` on enqueue, `409 Conflict` if `signal_id` is a duplicate, `400 Bad Request` on schema violation.

---

## Idempotency rules

1. Executor maintains a SQLite table `seen_signals(signal_id PRIMARY KEY, first_seen_at)`.
2. On receipt, executor checks the table before doing anything else. If present, return `409` and log.
3. Entries older than 24 hours are pruned nightly.
4. If a signal is rejected for any reason (schema, stale, duplicate, user-config mismatch), it is NOT marked as "seen" — so a corrected republish can still be processed.

---

## Validation rules (what the executor enforces)

Before placing a trade, the executor MUST verify:

1. `schema_version` matches a supported version (currently `"1.0"`).
2. `signal_id` is a valid UUID and not in `seen_signals`.
3. `emitted_at` is within the last 10 minutes (reject stale signals).
4. `user_id` corresponds to a config file in `users/`.
5. `pair` exists on the user's configured exchange.
6. `side` is one of the allowed values.
7. `confidence` ≥ user's `min_confidence_threshold` from their config.
8. `strategy_id` exists in `strategies/registry.json` AND is listed in the user's `active_strategies`.
9. `regime` is allowed under the user's `regime_filter` (e.g., user may disable trading in `CRASH`).
10. The resulting position size does not exceed the user's `max_position_size_pct` or any daily risk caps.

If any check fails, the signal is logged and skipped. The executor does NOT crash on a bad signal.

---

## Example signals

### A `buy` signal (normal case)

```json
{
  "schema_version": "1.0",
  "signal_id": "a7f3d2e4-9c8b-4e5f-a1b2-c3d4e5f6a7b8",
  "emitted_at": "2026-04-21T12:00:00Z",
  "user_id": "user_01_gaurav",
  "pair": "BTC/USDT",
  "timeframe": "15m",
  "side": "buy",
  "confidence": 0.82,
  "regime": "BULL",
  "strategy_id": "rsi_macd_ai_v1",
  "position_size_pct": 0.02,
  "stop_loss_atr_multiplier": 2.0,
  "take_profit_atr_multiplier": 4.0,
  "market_context": {
    "price": 67234.50,
    "rsi": 58.2,
    "macd_histogram": 0.0034,
    "atr_14": 1245.30
  },
  "reasoning": "MACD bullish crossover confirmed on 15m; HMM regime BULL; AI concurs."
}
```

### A `hold` signal (most common)

Hold signals are still emitted and logged so the Karpathy loop has full decision history. Executor logs and skips trade.

```json
{
  "schema_version": "1.0",
  "signal_id": "b8e4c3f5-0d9c-5f6e-b2c3-d4e5f6a7b8c9",
  "emitted_at": "2026-04-21T12:15:00Z",
  "user_id": "user_01_gaurav",
  "pair": "BTC/USDT",
  "timeframe": "15m",
  "side": "hold",
  "confidence": 0.45,
  "regime": "NEUTRAL",
  "strategy_id": "rsi_macd_ai_v1",
  "position_size_pct": 0.0,
  "stop_loss_atr_multiplier": 0.0,
  "market_context": {
    "price": 67198.10,
    "rsi": 52.1,
    "atr_14": 1240.00
  },
  "reasoning": "No strong signal; RSI mid-range, regime NEUTRAL."
}
```

### A `sell` signal for an open position

```json
{
  "schema_version": "1.0",
  "signal_id": "c9f5d4e6-1e0d-6a7f-c3d4-e5f6a7b8c9d0",
  "emitted_at": "2026-04-21T14:30:00Z",
  "user_id": "user_01_gaurav",
  "pair": "BTC/USDT",
  "timeframe": "15m",
  "side": "sell",
  "confidence": 0.75,
  "regime": "BULL",
  "strategy_id": "rsi_macd_ai_v1",
  "position_size_pct": 1.0,
  "stop_loss_atr_multiplier": 0.0,
  "market_context": {
    "price": 68500.00,
    "rsi": 72.3,
    "macd_histogram": -0.0008,
    "atr_14": 1250.00
  },
  "reasoning": "RSI overbought, MACD momentum turning; exit position."
}
```

For sell signals, `position_size_pct` means "fraction of the open position to close" — `1.0` closes the whole position.

---

## Versioning and migration

When a breaking change is needed:

1. Draft the new schema (e.g., `v1.1` adds a field, `v2.0` removes one) in this doc under a new heading.
2. Update signal generator to emit both old and new versions in parallel for 1 week (dual-writes).
3. Update executor to accept both versions during transition.
4. After 1 week, signal generator drops the old version.
5. After 1 month, executor drops old-version support.

Non-breaking changes (adding optional fields) do not require a version bump.

---

## Non-goals

- This contract does NOT include exchange-specific order parameters (limit price, time-in-force, etc.). The executor decides those based on the user's config and the signal.
- This contract does NOT include the raw feature vector used by the AI. Keep `market_context` human-readable; the AI's internal features live in the signal generator's logs.
- This contract does NOT prescribe position management beyond entry. Trailing stops, partial take-profits, etc. are the executor's domain once a position is open.
