# Claude Code Handoff — FinBuddy AutoBacktest

## ✅ Current Status

- **Strategy**: v6 pushed (Option C — trailing stop + tighter ML exit combined)
- **Grid**: v3 — 72 combos (stoploss x trailing_offset x ml_exit_threshold x ml_threshold x atr_threshold)
- **autobacktest.py**: v4 — updated PATCH_RULES + CSV headers for new params
- **Round 2 result**: 36/36 FAIL — full CSV at `_autobacktest_results.csv`
- **Round 2 root cause**: avg loser > avg winner. Asymmetry attack = v6 goal.

## 🚀 Your Job (Claude Code)

Run Round 3 grid search:

```bash
cd /home/ubuntu/var/www/html/trade
git pull origin gaurav
sudo chown -R ubuntu:ubuntu freqtrade/user_data/
python3 scripts/autobacktest.py
```

Expected runtime: ~72 combos × ~15 min each = up to ~18 hours. Run in tmux:

```bash
tmux new -s autobacktest3
python3 scripts/autobacktest.py
# Ctrl+B D to detach
```

## 📋 After Grid Completes

1. Commit `_autobacktest_results.csv` with message: `data: Round 3 grid results — v6 Option C`
2. Update `finbuddy_memory/graveyard.md` with any new dead combos
3. If PASS found: update `finbuddy_memory/winners.md`
4. Update this file with outcome + best result
5. Push to gaurav branch

## ⚠️ Do NOT

- Do NOT touch `FinBuddyFreqAI.py` directly — autobacktest.py handles patching
- Do NOT modify `autobacktest_grid.json` — Perplexity owns that
- Do NOT run without `git pull` first — always pull latest before starting

## 📊 Round History

| Round | Combos | Best Sharpe | Best WR | Root Cause |
|-------|--------|-------------|---------|------------|
| 1 | 12 | negative | 65% | EMA/RSI tuning useless. Also chmod bug → all 12 tested combo 1 |
| 2 | 36 | -0.236 | 60.8% | roi_multiplier dead lever. stoploss=-0.030 is the best lever |
| 3 | 72 | TBD | TBD | Testing trailing_offset + ml_exit_threshold (Option C) |

## 🔑 Key Architecture

- Strategy temp-patched to `/tmp/FinBuddyFreqAI_test.py` (avoids opc ownership)
- Config `stoploss` patched + `minimal_roi` removed (dead lever, strategy controls it)
- Results → `_autobacktest_results.csv` (append mode, survives restarts)
- Stop on first PASS (Sharpe>0.5, WR>50%, DD<20%, PF>1.2)
