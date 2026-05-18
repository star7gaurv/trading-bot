"""
FinBuddy Brain — Autonomous Hypothesis Engine

The brain generates hypotheses (parameter variants), tests them by running backtests
in the background, logs every result to an append-only JSONL, and proposes promotions
to live when a clear winner emerges (approval-gated via Telegram).

Per FinBuddy vision: the brain decides, not the human. Humans only approve promotions
and set strategic direction. No more "should I try X or Y?" — the brain tries both.

Components:
- experiment_log.py    — JSONL append-only experiment store; queryable
- hypothesis_gen.py    — SAFE + AGGRESSIVE variant generators
- runner.py            — picks next hypothesis, runs backtest, logs result
- promote.py           — finds winners, sends Telegram approval alert
- brain_cli.py         — single entry point: brain status / brain run / brain promote
"""
