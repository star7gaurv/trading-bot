# FinBuddy — Closed Trade Ledger

> Auto-written by `scripts/trade_postmortem.py` every 15 minutes.
> One row per closed trade. The brain reads this back via Karpathy loop
> and external research scripts to find which slots/regimes pay off.

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
