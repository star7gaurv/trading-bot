# Build Roadmap

Ten phases were planned for the single-user build-out. Status below is verified against the
server's actual live crontab as of 2026-09-10, not just carried forward from planning notes —
two phases below are corrected from what earlier documentation claimed.

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundation — FreqTrade, Telegram, server | ✅ Complete |
| 1 | FreqAI brain — long + short, regression | 🔄 In progress — live since 2026-05-19; no promotion has yet cleared the bar. See [The Brain](../brain.md) |
| 2 | External data — Fear & Greed, CoinGecko, CryptoPanic, DefiLlama, Google Trends | ✅ Live — cron every 15 min |
| 3 | Regime detection | ✅ Live — cron every 4h. See [Regime Detection](../data/regime-detection.md) |
| 4 | Memory vault — Obsidian-format auto-write + git auto-commit | ✅ Live — cron every 15 min |
| 5 | Nightly research loop (`scripts/karpathy/`) | ⏸️ Built, not currently scheduled — the code exists but is not in the live crontab as of this check |
| 6 | TradingView alerts | 🔴 Abandoned (2026-05-04) — requires a paid TradingView plan |
| 7 | Standalone signal executor | 🔴 Retired (2026-05-24) — a legacy prototype removed as dead weight; live trading runs through FreqTrade directly, not this |
| 8 | Futures setup — Binance API, isolated margin | ✅ Complete |
| 9 | Futures risk engine — regime sizing, cluster cap, funding guard | ✅ Complete. See [Risk Engine](../strategy/risk-engine.md) |
| 10 | Live capital migration | ⬜ Blocked — needs a walk-forward pass or a real track record; neither has happened yet. See [Directional](../modules/directional.md) |

## Why Phase 10 is the real gate

Every other phase either shipped or was deliberately retired. Phase 10 — actually trading real
money — is gated behind evidence, not a calendar date: a walk-forward run clearing profit factor
1.2, win rate 50%, Sharpe 0.5, and drawdown under 20%, or a long enough dry-run track record to
substitute for it. As of 2026-09-10 neither condition has been met — see
[Directional](../modules/directional.md) for exactly how far off the current numbers are, and why
new entries are currently paused rather than accumulating more of the same unproven track record.
