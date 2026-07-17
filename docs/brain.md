# Brain — Autonomous Hypothesis Engine

`scripts/brain/` is the self-evolving loop: generate hypotheses → queue → backtest → self-diagnose
→ prune/inject → promote winners to live. See `scripts/brain/analyst.py`'s own module docstring
for the full loop description.

## Core pipeline

::: brain.experiment_log

::: brain.hypothesis_gen

::: brain.runner

::: brain.analyst

::: brain.promote

## CLI entrypoint

::: brain.brain_cli

## LLM-driven proposal

::: brain.llm_hypothesis

## Measurement / diagnostics

::: brain.feature_ic

::: brain.meta_auc

::: brain.ic_advisor
