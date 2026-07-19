# Cortexa Modules — Plain-English Explainers

**Audience: marketing copy, investor materials, customer-facing content.** Every sentence here has
already been checked against the [Confidentiality Style Guide](../docs/confidentiality.md) — no
third-party framework or library names. Source-of-truth taglines below are pulled directly from
the live dashboard's own module descriptions, so this stays consistent with what a user actually
sees once they log in.

---

## The core idea

Cortexa isn't one trading bot — it's several independent, narrowly-scoped strategies ("modules"),
each one measured honestly before it's trusted with anything. Some modules bet on price direction;
others are built to make money regardless of which way the market moves. All of them are watched
by the same underlying research process: observe, hypothesize, test out-of-sample, and only
promote what actually clears the bar.

---

## Directional Trading — `Live`

> Predicts which way price will move and trades long or short on Binance futures.

The flagship module. An AI model scores every tracked coin on every price update, looking for a
strong enough signal to open a long or short position. It exits either when its own signal says
the move has played out, or when a stop-loss is hit. This is the only module currently trading
with (simulated, dry-run) directional conviction — the others below are explicitly built to avoid
needing to guess direction at all.

**Status honesty**: currently dry-run only — proven on paper before any real capital moves.

---

## Grid Trading — `Paper`

> Profits from a coin bouncing inside a price range — no direction guess needed.

Instead of betting on where price goes next, this module places a ladder of buy/sell levels
across a price range and profits every time the price oscillates through them — up or down, it
doesn't matter, as long as the coin keeps moving within its range rather than trending hard in one
direction. It's the natural complement to Directional Trading: it earns in the choppy, sideways
conditions where a directional bet struggles most.

---

## Pairs Trading — `Paper`

> Bets that two related coins drift back together — profits whether the market goes up or down.

Some coins move together most of the time because they're economically linked. When two such
coins temporarily drift apart, this module bets on them snapping back into their usual
relationship — going long the one that's lagged, short the one that's run ahead. Because it's a
bet on the *relationship* between two assets rather than on either one's absolute price, it's
structurally insulated from broad market direction.

---

## Funding-Rate Farming — `Paper`

> Collects funding fees with no bet on price direction — fully market-neutral.

Perpetual futures markets periodically exchange a small fee between long and short traders to
keep contract prices anchored to the underlying spot price. This module collects that fee by
holding a perfectly offsetting position (long the underlying, short the equivalent futures
contract, or vice versa) — its market exposure nets to zero, so it earns from the fee itself, not
from picking a direction.

---

## What ties these together

Every module — win, lose, or still-in-paper — reports into the same measurement discipline: real
fees modeled, real slippage assumed, no cherry-picked backtest windows, and a clear, visible
distinction between "live with real capital," "live dry-run," and "paper simulation" at all times.
Nothing graduates to real capital without first proving itself honestly at the stage before it.
