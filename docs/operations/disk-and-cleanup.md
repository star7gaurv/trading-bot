# Disk & Cleanup

## What actually consumes disk here

Nearly all of it is FreqAI model artifacts. Every retrain (every 4 hours, per pair, per active
FreqAI identifier) writes a `sub-train-<PAIR>_<timestamp>/` directory. Left unmanaged, this grows
without bound — a single identifier that ran live for about two and a half months once reached
**82GB by itself**, 89% of the entire disk, before being found and cleaned up.

## Two layers of defense, both added 2026-09-10

**FreqAI's own retention** (`config.json`'s `freqai.purge_old_models: true`) keeps only the 2 most
recent retrains per pair for whatever identifier is currently live, automatically, after every
retrain — no cron needed.

**`scripts/brain_cleanup.py`** (cron, daily 04:00 UTC) handles everything that setting can't:

- The brain's own scratch directories (`brain_*`, `wf_*`, `fam_*`, `wfam_*`) older than 2 days,
  with the top-10 best-profit experiment models preserved indefinitely as analyzable history.
- **Retired identifiers** — any FreqAI identifier directory that *isn't* the currently-live one
  (read fresh from `freqtrade/.env` on every run). This is the layer that would have caught the
  82GB problem: it purges `sub-train-*` bloat from any identifier a promotion or feature change has
  moved away from, while always preserving that identifier's small metadata files
  (`historic_predictions.pkl` and similar) — some of this project's own research scripts depend on
  a retired identifier's prediction history surviving longer than the live rolling window keeps.
- Orphaned top-level `sub-train-*` directories not nested under any identifier at all — debris this
  project found accumulating from an old bug, unrelated to any identifier's own retention.
- Old backtest result zips and brain log files, on separate, longer retention windows.

## If disk pressure ever recurs

1. `du -h --max-depth=1 freqtrade/user_data/models/` to find what's actually large.
2. Check `freqtrade/.env`'s `FREQTRADE__FREQAI__IDENTIFIER` against what's on disk — anything else
   there is, by definition, retired.
3. Run `scripts/brain_cleanup.py --dry-run` to see what it would remove before trusting it to run
   for real.
