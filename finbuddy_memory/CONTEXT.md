# FinBuddy — Master Context
Last updated: 2026-05-04 09:00 UTC

## May 4 2026 PM Session (Claude Code)
- Binance USDⓈ-M futures verified connected; dry-run active with FinBuddyFreqAI v11
- label_period_candles fixed 3→12 in config.json (backtest_config.json was already 12)
- ml_threshold grid extended: [0.50, 0.55, 0.60, 0.65, 0.70]
- RiskEngine wired into custom_stake_amount: regime-aware stake (BULL=1.0, NEUTRAL=0.75, BEAR=0.5, CRASH=0.0)
- finbuddy_memory/regimes/ bind-mounted into container (:ro) — regime file accessible at /freqtrade/finbuddy_memory/regimes/
- sys.path fallback fixed in strategy so risk_engine imports when loaded from /tmp (backtest mode)
- Bull grid relaunched: 90 combos, BACKTEST_TIMERANGE=20240101-20250101, PID 327995
- First successful result: combo 3 (ml_exit=0.45, atr=0.002) → 9 trades, WR 44.4%, Sharpe 32.6, DD 0.1%
- Overall completion: ~60%

## Current Regime
Regime: **NEUTRAL** | Confidence: 50.0% | Since: 2026-05-04

## Market Sentiment
Fear & Greed: 40 (Fear)
BTC Dominance: 58.52%
News Sentiment: 50.0% bullish

## Bot Performance
Total Trades: 0 | Win Rate: 0.0% | Total P&L: 0%

## Open Trades (0)
- No open trades
## Risk Flags
- None
