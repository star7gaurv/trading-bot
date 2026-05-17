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
| 2026-05-13 10:30:44 | BTC/USDT:USDT | SHORT | 13h05m | -0.48% | -0.77 | force_exit | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 10:30:56 | BCH/USDT:USDT | SHORT | 2h28m | -0.22% | -0.41 | force_exit | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 10:41:56 | OP/USDT:USDT | SHORT | 0h42m | +1.87% | +3.45 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 11:07:37 | TON/USDT:USDT | SHORT | 0h36m | -0.01% | -0.02 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 12:42:56 | ONDO/USDT:USDT | SHORT | 2h11m | +3.80% | +7.00 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 12:51:11 | BTC/USDT:USDT | SHORT | 1h43m | +0.49% | +0.80 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 12:46:31 | SOL/USDT:USDT | SHORT | 0h38m | +1.43% | +2.64 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 14:01:34 | LTC/USDT:USDT | SHORT | 1h18m | +1.11% | +2.06 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 14:01:31 | XRP/USDT:USDT | SHORT | 1h14m | +0.61% | +1.15 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 14:01:34 | ARB/USDT:USDT | SHORT | 1h10m | +2.17% | +4.05 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 14:28:54 | LINK/USDT:USDT | SHORT | 0h27m | -1.20% | -2.27 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 16:10:18 | NEAR/USDT:USDT | SHORT | 1h41m | +2.28% | +4.26 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 16:08:58 | ONDO/USDT:USDT | SHORT | 1h08m | +2.25% | +4.23 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 16:10:18 | LINK/USDT:USDT | SHORT | 0h12m | -0.18% | -0.33 | exit_signal | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-13 16:31:18 | DOGE/USDT:USDT | SHORT | 0h22m | -1.26% | -2.38 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 05:46:05 | XRP/USDT:USDT | SHORT | 12h45m | -0.71% | -1.35 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 11:15:12 | ZEC/USDT:USDT | SHORT | 18h04m | +3.02% | +5.71 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 12:02:12 | ENA/USDT:USDT | SHORT | 0h59m | +1.16% | +0.73 | exit_signal | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 12:02:37 | BCH/USDT:USDT | SHORT | 0h39m | -0.14% | -0.09 | exit_signal | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 12:25:27 | UNI/USDT:USDT | SHORT | 0h23m | -0.92% | -0.58 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:07:11 | TON/USDT:USDT | SHORT | 1h04m | -2.52% | -1.59 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:06:31 | ZEC/USDT:USDT | SHORT | 0h06m | -1.52% | -0.96 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:11:40 | SUI/USDT:USDT | SHORT | 0h11m | -1.44% | -0.91 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:12:10 | LTC/USDT:USDT | SHORT | 0h11m | -0.60% | -0.38 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:16:20 | BCH/USDT:USDT | SHORT | 0h09m | -0.48% | -0.30 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:52:05 | ARB/USDT:USDT | SHORT | 0h44m | -1.00% | -0.63 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:49:41 | UNI/USDT:USDT | SHORT | 0h37m | -1.02% | -0.63 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 13:50:06 | ENA/USDT:USDT | SHORT | 0h33m | -1.19% | -0.75 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:13:13 | ZEC/USDT:USDT | SHORT | 0h12m | -1.75% | -1.09 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:19:33 | LTC/USDT:USDT | SHORT | 0h18m | -0.60% | -0.38 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:18:27 | BCH/USDT:USDT | SHORT | 0h17m | -0.51% | -0.32 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:26:38 | ARB/USDT:USDT | SHORT | 0h25m | -1.00% | -0.63 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:16:02 | UNI/USDT:USDT | SHORT | 0h15m | -0.91% | -0.56 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:18:28 | TON/USDT:USDT | SHORT | 0h05m | -2.10% | -1.31 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:21:43 | DASH/USDT:USDT | SHORT | 0h05m | -1.15% | -0.72 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:19:04 | ENA/USDT:USDT | SHORT | 0h00m | -1.35% | -0.84 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:26:08 | TAO/USDT:USDT | SHORT | 0h07m | -1.03% | -0.64 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:21:34 | SUI/USDT:USDT | SHORT | 0h02m | -1.46% | -0.91 | trailing_stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:45:18 | SOL/USDT:USDT | SHORT | 0h24m | -0.82% | -0.51 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:45:43 | ADA/USDT:USDT | SHORT | 0h23m | -0.75% | -0.47 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:51:13 | LINK/USDT:USDT | SHORT | 0h05m | -0.95% | -0.59 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 14:58:28 | ATOM/USDT:USDT | SHORT | 0h12m | -1.62% | -1.00 | stop_loss | BEAR | freqai_lgbm_v19_short |
| 2026-05-14 15:50:45 | NEAR/USDT:USDT | SHORT | 0h59m | -1.45% | -0.90 | stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 15:48:00 | ATOM/USDT:USDT | SHORT | 0h47m | -1.16% | -0.72 | stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 15:56:40 | ARB/USDT:USDT | SHORT | 0h56m | -1.13% | -0.70 | stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 15:51:35 | SOL/USDT:USDT | SHORT | 0h03m | -0.86% | -0.53 | stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 16:53:44 | SUI/USDT:USDT | SHORT | 0h46m | +2.95% | +2.73 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 17:45:30 | OP/USDT:USDT | SHORT | 0h44m | +1.83% | +1.69 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 18:12:32 | ARB/USDT:USDT | SHORT | 0h11m | -1.43% | -1.33 | stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-14 18:33:12 | OP/USDT:USDT | SHORT | 0h20m | -1.17% | -1.09 | stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-15 00:34:13 | APT/USDT:USDT | SHORT | 6h05m | +2.38% | +2.20 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v19_short |
| 2026-05-15 00:39:03 | ONDO/USDT:USDT | SHORT | 0h38m | -1.88% | -1.74 | stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 03:11:12 | NEAR/USDT:USDT | SHORT | 1h10m | -1.36% | -1.25 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 06:00:47 | APT/USDT:USDT | SHORT | 0h59m | +3.94% | +3.65 | exit_signal | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 06:05:37 | TAO/USDT:USDT | SHORT | 0h04m | -1.27% | -1.18 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 07:14:32 | LINK/USDT:USDT | SHORT | 0h40m | -1.07% | -1.01 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 07:22:27 | ENA/USDT:USDT | SHORT | 0h21m | -1.62% | -1.52 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 07:23:32 | SOL/USDT:USDT | SHORT | 0h08m | -0.89% | -0.84 | stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 08:08:23 | TON/USDT:USDT | SHORT | 0h07m | -1.89% | -1.77 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 11:33:42 | TON/USDT:USDT | SHORT | 2h33m | -1.79% | -1.67 | trailing_stop_loss | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 14:00:21 | ENA/USDT:USDT | SHORT | 4h59m | +13.07% | +12.25 | exit_signal | NEUTRAL | freqai_lgbm_v21_short |
| 2026-05-15 14:10:34 | ARB/USDT:USDT | SHORT | 3h14m | +7.98% | +7.47 | exit_signal | NEUTRAL | freqai_lgbm_v22_short |
| 2026-05-15 14:00:23 | TON/USDT:USDT | SHORT | 1h59m | +9.05% | +8.46 | exit_signal | NEUTRAL | freqai_lgbm_v22_short |
| 2026-05-15 14:00:24 | UNI/USDT:USDT | SHORT | 0h10m | +3.05% | +2.84 | exit_signal | NEUTRAL | freqai_lgbm_v22_short |
| 2026-05-15 16:33:03 | UNI/USDT:USDT | SHORT | 0h32m | -1.52% | -0.99 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-15 17:06:25 | SOL/USDT:USDT | SHORT | 0h06m | -0.99% | -0.66 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-15 17:39:44 | BTC/USDT:USDT | SHORT | 0h38m | -0.63% | -0.25 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-15 17:53:34 | DASH/USDT:USDT | SHORT | 0h52m | -1.59% | -1.05 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-15 18:04:28 | OP/USDT:USDT | SHORT | 1h03m | -1.25% | -0.83 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 01:58:04 | ENA/USDT:USDT | SHORT | 7h55m | +2.77% | +1.83 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 07:01:39 | ZEC/USDT:USDT | SHORT | 12h59m | +9.09% | +6.00 | exit_signal | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 07:01:40 | ONDO/USDT:USDT | SHORT | 12h57m | +10.22% | +6.75 | exit_signal | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 07:01:44 | ARB/USDT:USDT | SHORT | 5h03m | +5.86% | +3.88 | exit_signal | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 07:23:04 | ATOM/USDT:USDT | SHORT | 0h21m | +1.92% | +1.32 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 09:35:49 | UNI/USDT:USDT | SHORT | 0h35m | +2.12% | +1.43 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 11:13:40 | ATOM/USDT:USDT | SHORT | 0h11m | -1.11% | -0.76 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 13:11:04 | LTC/USDT:USDT | SHORT | 1h10m | -0.69% | -0.47 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 13:08:14 | OP/USDT:USDT | SHORT | 1h07m | -0.99% | -0.68 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 14:31:36 | DOGE/USDT:USDT | SHORT | 0h21m | -1.08% | -0.74 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 14:34:46 | OP/USDT:USDT | SHORT | 0h24m | -0.98% | -0.68 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 15:10:16 | SUI/USDT:USDT | SHORT | 0h09m | -1.26% | -0.86 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 16:04:47 | ENA/USDT:USDT | SHORT | 0h54m | -1.45% | -0.99 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-16 16:05:42 | OP/USDT:USDT | SHORT | 0h05m | -1.12% | -0.77 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 01:11:14 | DOGE/USDT:USDT | SHORT | 9h06m | +1.55% | +1.06 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 01:05:09 | BTC/USDT:USDT | SHORT | 8h59m | +0.65% | +0.25 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 01:02:44 | APT/USDT:USDT | SHORT | 8h57m | +4.44% | +3.02 | exit_signal | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 01:16:49 | OP/USDT:USDT | SHORT | 0h14m | -0.84% | -0.57 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 02:01:57 | SOL/USDT:USDT | SHORT | 0h56m | +0.62% | +0.42 | exit_signal | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 02:32:02 | OP/USDT:USDT | SHORT | 0h30m | -0.84% | -0.57 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 03:39:15 | BTC/USDT:USDT | SHORT | 0h38m | -0.35% | -0.14 | trailing_stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 03:32:36 | AVAX/USDT:USDT | SHORT | 0h31m | -0.68% | -0.44 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 03:40:50 | OP/USDT:USDT | SHORT | 0h35m | -0.84% | -0.57 | stop_loss | BEAR | freqai_lgbm_v22_short |
| 2026-05-17 03:34:35 | UNI/USDT:USDT | SHORT | 0h29m | -0.77% | -0.52 | stop_loss | BEAR | freqai_lgbm_v22_short |
