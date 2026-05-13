# FinBuddy — Closed Trade Ledger

> Auto-written by `scripts/trade_postmortem.py` every 15 minutes.
> One row per closed trade. The brain reads this back via Karpathy loop
> and external research scripts to find which slots/regimes pay off.

## Caveats — read before drawing conclusions

- **Trades 26–29 (2026-05-09 BTC/ETH/DOGE/BCH shorts, all losses)** were
  fired under a buggy 3-class HOLD label scheme. After the v16 fix that
  removed HOLD, the next "fix" mapped time-barrier candles to "S" (short),
  which baked in a systematic short bias. Both bugs are now resolved
  in v16.1 (commit pending) — time-barrier candles are dropped from
  training entirely. Trades 26–29 should NOT be treated as legitimate
  signal-quality evidence.
- **Trades 1–25** are legacy v11 spot trades from April 2026 on BTC only.
  Not v15/v16 evidence either.
- **First clean v16.1 trades** will be at trade id 30+ after 2026-05-09 retrain.

| Closed (UTC) | Pair | Side | Hold | P&L % | P&L $ | Exit | Regime | Tag |
|---|---|---|---|---|---|---|---|---|
| 2026-04-05 22:46:16 | BTC/USDT | LONG | 1d3h | +1.04% | +2.07 | roi | NEUTRAL | force_entry |
| 2026-04-06 09:22:06 | BTC/USDT | LONG | 3h52m | +1.15% | +2.31 | roi | NEUTRAL | force_entry |
| 2026-04-07 06:00:01 | BTC/USDT | LONG | 20h00m | -1.75% | -3.49 | force_exit | NEUTRAL | force_entry |
| 2026-04-07 21:06:46 | BTC/USDT | LONG | 12h21m | +1.07% | +2.15 | roi | NEUTRAL | force_entry |
| 2026-04-07 22:45:01 | BTC/USDT | LONG | 0h45m | +0.83% | +1.66 | force_exit | NEUTRAL | force_entry |
| 2026-04-08 13:07:36 | BTC/USDT | LONG | 12h07m | +1.06% | +2.12 | roi | NEUTRAL | force_entry |
| 2026-04-09 02:15:00 | BTC/USDT | LONG | 12h30m | -1.40% | -2.79 | force_exit | NEUTRAL | force_entry |
| 2026-04-09 15:34:36 | BTC/USDT | LONG | 12h49m | +1.05% | +2.10 | roi | NEUTRAL | force_entry |
| 2026-04-09 22:17:21 | BTC/USDT | LONG | 5h32m | +1.04% | +2.07 | roi | NEUTRAL | force_entry |
| 2026-04-11 18:36:56 | BTC/USDT | LONG | 1d20h | +1.20% | +2.39 | roi | NEUTRAL | force_entry |
| 2026-04-12 12:52:56 | BTC/USDT | LONG | 18h07m | -3.41% | -6.83 | stop_loss | NEUTRAL | force_entry |
| 2026-04-13 19:26:06 | BTC/USDT | LONG | 3h56m | +1.05% | +2.10 | roi | NEUTRAL | force_entry |
| 2026-04-13 22:30:06 | BTC/USDT | LONG | 2h00m | +1.27% | +2.53 | roi | NEUTRAL | force_entry |
| 2026-04-14 14:22:16 | BTC/USDT | LONG | 7h07m | +1.00% | +2.01 | roi | NEUTRAL | force_entry |
| 2026-04-17 08:54:31 | BTC/USDT | LONG | 2d17h | +1.03% | +2.05 | roi | NEUTRAL | force_entry |
| 2026-04-20 04:45:01 | BTC/USDT | LONG | 14h15m | -2.16% | -4.33 | force_exit | NEUTRAL | force_entry |
| 2026-04-20 18:06:26 | BTC/USDT | LONG | 7h36m | +1.00% | +2.00 | roi | NEUTRAL | force_entry |
| 2026-04-22 02:29:51 | BTC/USDT | LONG | 1d8h | +1.03% | +2.07 | roi | NEUTRAL | force_entry |
| 2026-04-22 05:24:16 | BTC/USDT | LONG | 2h54m | +1.08% | +2.15 | roi | NEUTRAL | force_entry |
| 2026-04-22 14:10:51 | BTC/USDT | LONG | 5h40m | +1.01% | +2.02 | roi | NEUTRAL | force_entry |
| 2026-04-24 08:30:00 | BTC/USDT | LONG | 1d17h | -1.72% | -3.44 | force_exit | NEUTRAL | force_entry |
| 2026-04-26 11:06:11 | BTC/USDT | LONG | 2d1h | +0.46% | +0.91 | force_exit | NEUTRAL | force_entry |
| 2026-04-27 00:53:56 | BTC/USDT | LONG | 12h23m | +1.00% | +2.00 | roi | NEUTRAL | force_entry |
| 2026-04-27 15:18:51 | BTC/USDT | LONG | 14h18m | -3.21% | -6.43 | stop_loss | NEUTRAL | force_entry |
| 2026-04-30 18:09:56 | BTC/USDT | LONG | 1d1h | +0.46% | +0.92 | force_exit | NEUTRAL | force_entry |
| 2026-05-09 01:13:33 | DOGE/USDT:USDT | SHORT | 4h13m | -1.23% | -1.84 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v11_short |
| 2026-05-09 01:50:38 | BCH/USDT:USDT | SHORT | 4h50m | -0.67% | -1.00 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v11_short |
| 2026-05-09 13:00:14 | DASH/USDT:USDT | SHORT | 2h49m | -0.91% | -1.37 | exit_signal | NEUTRAL | freqai_lgbm_v11_short |
| 2026-05-09 15:00:11 | DOGE/USDT:USDT | SHORT | 1h59m | +0.82% | +1.23 | exit_signal | NEUTRAL | freqai_lgbm_v11_short |
| 2026-05-09 20:01:31 | TAO/USDT:USDT | SHORT | 3h01m | -1.17% | -1.75 | exit_signal | NEUTRAL | freqai_lgbm_v11_short |
| 2026-05-10 01:24:12 | XRP/USDT:USDT | LONG | 5h22m | -0.78% | -1.46 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v17_long |
| 2026-05-10 05:35:52 | TRX/USDT:USDT | LONG | 3h05m | -0.73% | -1.36 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v17_long |
| 2026-05-10 09:00:27 | AVAX/USDT:USDT | LONG | 0h24m | -0.25% | -0.45 | exit_signal | NEUTRAL | freqai_lgbm_v17_long |
| 2026-05-10 16:07:35 | ATOM/USDT:USDT | LONG | 6h57m | +3.89% | +7.21 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-10 18:10:03 | TRX/USDT:USDT | LONG | 6h05m | +0.39% | +0.72 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-10 23:02:07 | ETH/USDT:USDT | LONG | 2h01m | +2.11% | +3.93 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-11 16:05:16 | XRP/USDT:USDT | LONG | 19h04m | +2.08% | +3.90 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-11 19:00:38 | TAO/USDT:USDT | LONG | 19h58m | +1.86% | +3.48 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-11 20:05:25 | BTC/USDT:USDT | LONG | 19h04m | +0.60% | +0.98 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-12 10:00:19 | ETH/USDT:USDT | LONG | 17h55m | -1.75% | -3.31 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-12 10:00:19 | AVAX/USDT:USDT | LONG | 13h54m | -3.06% | -5.63 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-12 10:02:12 | ARB/USDT:USDT | LONG | 9h00m | -2.10% | -3.98 | exit_signal | NEUTRAL | freqai_lgbm_v18_long |
| 2026-05-12 11:00:32 | DOGE/USDT:USDT | SHORT | 1h00m | +0.46% | +0.87 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-12 11:00:32 | DOT/USDT:USDT | SHORT | 1h00m | +0.70% | +1.32 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-12 14:00:29 | ETH/USDT:USDT | SHORT | 2h00m | +0.67% | +1.26 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-12 16:04:23 | ZEC/USDT:USDT | SHORT | 2h03m | +0.90% | +1.69 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-12 17:22:03 | DOGE/USDT:USDT | SHORT | 2h09m | +0.33% | +0.63 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 09:48:55 | ETH/USDT:USDT | SHORT | 16h48m | -2.59% | -4.86 | force_exit | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 09:50:21 | ZEC/USDT:USDT | SHORT | 16h28m | -1.87% | -3.54 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
