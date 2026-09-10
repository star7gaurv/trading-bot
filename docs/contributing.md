# Contributing to This Codebase (and These Docs)

## The rule this whole documentation system exists to enforce

**Documentation as memory**: any non-trivial behavior — strategy logic, cron setup, API
integration, an experiment's outcome — must be documented so it's never forgotten. Historically
that meant remembering to hand-write something. Most of this site now makes that automatic instead
of asking anyone to remember.

## What updates itself, and what doesn't

| Page | How it stays current |
|---|---|
| [Reference](reference/index.md) | Regenerated from every `.py` file's own docstrings on every `mkdocs build`. Add a function with a docstring anywhere under `scripts/`, `dashboard/`, or the FreqTrade `user_data` tree — it appears here next build, with zero manual editing. |
| [Cron Reference](operations/cron-reference.md) | Read directly from the server's live `crontab -l` on every build, paired with each script's own module docstring. |
| [Third-Party Integrations](third-party.md) | Scanned from source for known usage patterns (exchange clients, LLM SDKs, Telegram API calls) on every build. |
| [Documentation Coverage](coverage.md) | Computed fresh on every build — a live checklist of exactly which functions still lack a docstring. |
| Everything else (Overview, Architecture, Strategy & Brain, Modules, this page) | Hand-written. Update these the same way `CLAUDE.md`'s session history gets updated — when something material changes. |

## Writing a docstring that shows up well here

This project uses **Google-style docstrings** (configured in `mkdocs.yml`'s `docstring_style`).
A function docstring should say what the function does, its parameters, and what it returns —
not restate its name:

```python
def _reversion_gate() -> dict:
    """Read the full closed-position ledger and decide whether new entries
    should be paused.

    Returns:
        dict: {"active": bool, "reasons": [...], stats...}
    """
```

Module-level docstrings (the triple-quoted string at the very top of a file, before any imports)
become that module's page introduction in the Reference section — write them as you would the
opening paragraph of a doc page, because that's literally what they become.

## The cron rule

Every crontab entry must `cd` into the project root first, or use an absolute script path. This
project has hit the same silent-failure pattern more than once: a cron missing that `cd`, dying
immediately on every single run, and nothing noticing for days because a dead cron produces no
error a human sees — just a feature or a report that's quietly gone stale. `data_sentinel.py`
(see [Monitoring](operations/monitoring.md)) exists specifically to catch this pattern going
forward, but the cheapest fix is still writing the cron entry correctly the first time.

## Engineering principles (the durable ones)

From this project's own root `CLAUDE.md`, unchanged since 2026-05-01 and worth restating here
because they're exactly what this documentation system was built to serve:

1. **Code over manual work.** If something can be automated once with a script or a cron, do that
   instead of repeating the manual effort — this entire docs system is that principle applied to
   documentation itself.
2. **DRY.** Shared logic lives in `scripts/lib/`, not duplicated across strategies and scripts.
3. **Documentation as memory.** See above.
4. **Never hardcode secrets.** Credentials come from `freqtrade/.env` (gitignored), never from a
   committed file.
5. **Don't build ahead of proof.** Multi-tenant infrastructure, new modules, and new integrations
   are worth building when something already running has a genuine, measured track record — not
   before. This project's own architecture decision (ADR-001) explicitly gates multi-tenant work
   behind a real live track record for exactly this reason.
