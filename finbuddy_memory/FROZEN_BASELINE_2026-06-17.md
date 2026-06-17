# FROZEN BASELINE — 2026-06-17 (clean control for the turnaround)

This is the deliberate, frozen live configuration set at the start of the
"Stop Bleed → Honest Brain → Meta-Label → New Features" turnaround. Every later
change is measured against the live behavior from this timestamp forward.

**DO NOT manually tweak live thresholds or apply any brain promotion until a
trustworthy (Phase-2 honest) brain produces a candidate that beats this baseline.**
The constant 15-min tweaking was motion, not progress.

## Frozen live config (as of 2026-06-17 ~18:50 UTC)
- Strategy: `FinBuddyFreqAI_v23.py`
- FreqAI identifier: `finbuddy_v23_nosvm_1780729988`
- Thresholds: **FREQAI_LONG_THRESHOLD=0.7**, **FREQAI_SHORT_THRESHOLD=-0.6** (raised this session
  from 0.3 / -0.3 — the post-deadlock bleeding regime). Asymmetric: longs are the worse side.
- FREQAI_STABILITY_N=1, FREQAI_K_TP=3.0, FREQAI_K_SL=2.0, FREQAI_LABEL_CANDLES=12
- 26 pairs, 15m, max 8 open, 1000 USDT dry-run wallet, confidence leverage 1x/2x/3x.

## Baseline diagnosis numbers to beat (forensics, this session)
Live (713 closed trades since 2026-04-04, total **+16.25 USDT** — but all of it from ONE week;
every week since loses):
- exit_signal exits: 204 trades, +1.82% avg, **+309 USDT, 89.7% WR** (the alpha — keep this).
- stop_loss exits: 288 trades, -1.39% avg, **-313 USDT, 0% WR** (the bleed — ~40% of entries).
- Payoff ratio 1.38 (fine — NOT the disease). Entry is a coin flip; exit is the edge.
- LONG -33 all-time / -50 last-30d; SHORT +49 all-time / -42 last-30d.

Brain (1,770 experiments, **0 scalable winners**): profit monotonic in trade count
(0-150 trades avg -0.34%; 1500+ avg -52%). The 89 "positive" runs avg 45 trades, PF~1.1 = noise.

## Success criteria for ANY future live change vs this baseline
- Must keep the exit_signal alpha (don't break the 90%-WR exit path).
- Must reduce stop_loss bleed count/PnL.
- Must be validated by the Phase-2 honest brain (>=150 trades, PF>1.1, expectancy>0), not by
  45-trade noise.
