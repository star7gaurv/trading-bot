# Cortexa

**Self-taught. Self-tuned. Self-evolving.**

Cortexa is not a trading bot. A bot follows fixed rules. Cortexa observes markets, forms
hypotheses, tests them, promotes winners, retires losers, and gets smarter over time — without
manual intervention. [FreqTrade](https://www.freqtrade.io/) placing orders on Binance is the
hands. The brain — the hypothesis engine, the regime detection, the self-measurement — is the
product.

This site documents that brain: the live trading strategy, the autonomous experiment engine
behind it, every paper-trading module, every scheduled job, and a complete, auto-generated
reference for every function in the codebase.

!!! warning "Internal only"
    This site names the real tech stack, internal script names, and system internals freely.
    That's deliberate — see the [Confidentiality Style Guide](confidentiality.md) before copying
    anything from here into anything customer-facing.

## Where to start

<div class="grid cards" markdown>

- :material-compass-outline: **[Getting Started](getting-started.md)**
  How to run this site, where the live system actually lives, and how to reach it from a phone.

- :material-sitemap-outline: **[Architecture](architecture.md)**
  How the pieces fit together — FreqTrade, the brain, the dashboard, and the data pipeline.

- :material-chart-line: **[Strategy & Brain](strategy.md)**
  How the live directional strategy makes entry/exit decisions, and how the brain that tunes it
  actually works.

- :material-view-module-outline: **[Modules](modules/directional.md)**
  Every trading module — live and paper — with its real, current track record.

- :material-cog-outline: **[Operations](operations/cron-reference.md)**
  Every scheduled job, what it does, and how monitoring and cleanup work.

- :material-file-code-outline: **[Reference](reference/index.md)**
  Every module, every function, auto-generated from the code's own docstrings on every build.

</div>

## What's live right now

The one line that matters most, kept current in
[`CLAUDE.md`](https://github.com/star7gaurv/trading-bot/blob/master/CLAUDE.md)'s "What Is Live and
Working Right Now" section at the project root — that file is the single source of truth for
current state, and this site is the deep-reference layer underneath it.

## How this site stays current

Everything under **Reference**, the **Cron Reference**, **Third-Party Integrations**, and
**Documentation Coverage** pages is regenerated from the live codebase and the live crontab every
time this site is built — nothing there is hand-maintained, so nothing there can silently drift
the way a hand-written wiki page does. See [Contributing](contributing.md) for exactly how that
works and what you need to do (usually: nothing) when you add a new script.
