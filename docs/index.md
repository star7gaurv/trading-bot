# FinBuddy — Internal Documentation

This is internal documentation for the FinBuddy codebase, generated from the code's own
docstrings. It is **not** customer or public-facing — see the
[Confidentiality Style Guide](confidentiality.md) before copying anything from here into any
customer-visible surface.

## Sections

- **[Brain](brain.md)** — the autonomous hypothesis-generation and self-diagnosis engine
  (`scripts/brain/`): queues, runs, and evaluates backtest experiments, then promotes winners to
  live via `promote.py`.
- **[Shared Libraries](lib.md)** — reusable helpers (`scripts/lib/`) used across the brain, the
  dashboard, and standalone scripts: credentials, live pricing, Telegram messaging.
- **[Dashboard Backend](dashboard.md)** — the FastAPI service (`dashboard/`) that powers the
  operator dashboard: auth, system health, and the streaming API the React frontend consumes.

## Building this site

```bash
/home/ubuntu/.finbuddy/venvs/docs/bin/mkdocs build   # outputs to ./site/
/home/ubuntu/.finbuddy/venvs/docs/bin/mkdocs serve    # live-reload dev server on :8000
```

`mkdocs serve` binds to localhost only by default — reach it from your phone via an SSH port
forward through Termius (`Local port 8000 -> 127.0.0.1:8000` on the server), not by exposing it
publicly.
