# Regime Detection

Every entry decision, every threshold, and every stake size in the live strategy is conditioned on
a market regime: `CRASH`, `BEAR`, `NEUTRAL`, `BULL`, or `EUPHORIA`. This page explains what that
classification actually is and its real, known limitation.

## What it actually is

`scripts/regime_core.py` is the single source of truth both the live detector and the historical
backtest builder import from — a deliberate fix after the two used to run on *unrelated* inputs
(price action live, sentiment historically) and routinely disagreed. It's a rule over BTC price
action, not a hidden Markov model despite "HMM" appearing in some older script names:

- **CRASH** — a sharp 7-day drawdown past -15%, or a 30-day return past -25%
- **EUPHORIA** — a strong 30-day rally (+30%) with price stretched 20% above its own 90-day trend
- **BEAR** — a 30-day return below -10% while price sits under its 90-day trend
- **BULL** — a 30-day return above +10% while price sits above its 90-day trend
- **NEUTRAL** — none of the above

## Two consumers, one source

`scripts/build_historical_regime.py` (daily cron) applies these rules to every historical BTC
4-hour candle and writes a parquet series, so backtests see a genuine per-candle regime history
instead of a single constant value. `freqtrade/user_data/scripts/hmm_regime_detector.py` (cron,
every 4 hours) applies the identical rules live and writes `finbuddy_memory/regimes/current.json`.

## The real limitation, measured

Because the classification depends on 7-day and 30-day trailing returns, it is structurally
2-4 weeks late relative to the market itself — this isn't a bug so much as an inherent property of
any trailing-return-based classifier. It has caused real, observed problems: a 2026-08-17 to
2026-08-21 rally produced almost no long entries because the regime hadn't flipped yet, and when it
did flip to BULL on 2026-08-25 — after the rally had already ended — the hard entry gate forced
long-only trading into the chop that followed. See [Directional](../modules/directional.md) for
what that specific episode cost.

## The 2026-09-10 mitigation

Rather than build a second, faster discrete regime classifier — this project has hit the
unreachable-threshold and deadlock bug class from exactly that pattern of hand-tuned discrete
thresholds multiple times — the model was instead given continuous, real-time-scaled multi-day BTC
momentum features (`%-btc_mom_3d/7d/14d`) directly, alongside the discrete regime. The regression
model can weight a 3-day move differently from a 14-day one on its own; there's no new magic
threshold for a market shift to silently drift past.

## A stale-data failure mode worth knowing about

The historical regime parquet is rebuilt once daily and can lag real time by up to ~36 hours. Live
candles beyond the parquet's coverage fall back to the fresh live regime from `current.json` rather
than a stale forward-filled value — a fix shipped 2026-06-08 after the opposite behavior caused a
genuine trading deadlock (the parquet said CRASH, the live detector said NEUTRAL, and the
mismatch blocked every entry). The same historical-vs-live distinction now governs several other
live-only data sources in this codebase — see
[Directional](../modules/directional.md#whats-actually-been-measured) for the most recent instance
of this exact bug class.
