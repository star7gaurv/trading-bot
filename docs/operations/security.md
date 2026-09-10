# Security

## The 2026-07-05 hardening pass

A focused security review found and fixed several real exposures that had accumulated over the
project's early build-out:

- **FreqTrade's REST API** was reachable from outside the server; restricted to loopback
  (`127.0.0.1`) only — see `docker-compose.yml`'s port binding.
- **Every credential** that had been hardcoded in committed files (the FreqTrade API password, the
  N8N admin password) moved to `freqtrade/.env`, which is gitignored and never committed.
- **Git history itself was scrubbed** of the secrets that had been committed before this pass.
- **Server sudoers configuration** was narrowed to what's actually needed.

One exposure from this pass was never fully closeable: the live Telegram bot token appears in an
already-merged GitHub pull request reference that can't be scrubbed after the fact. It's flagged
to rotate before any live-capital migration (see [Roadmap](../platform/roadmap.md)) — not yet
rotated, since the bot is still in active use and rotating requires a coordinated switch.

## A second exposure path found later (2026-07-14)

The same live Telegram token was also found hardcoded in a sample script inside a `.md`
documentation file — it had survived the July 5 scrub because that pass searched `.py`/`.json`
files, not markdown code samples. Fixed, and a full secret-value scan (matching in-memory, never
printing the actual value) was run across every git-tracked file in the repository — zero
remaining exposures found in the working tree at that time.

## Ongoing practice

- **Never hardcode secrets** — this project's own stated engineering principle (`CLAUDE.md`).
  Every script reads credentials from `freqtrade/.env` via `scripts/lib/ft_creds.py`, not from a
  literal in the source.
- **Config editing via Python `json`, never `sed`** — a working preference specifically because a
  malformed `sed` edit against a JSON config file is a silent-corruption risk that's easy to miss
  until the next container restart fails.
- **This documentation site itself is password-protected** at `/docs/` under the main domain
  precisely because it documents real internal details (cron schedules, strategy internals,
  infrastructure specifics) that this project's own [Confidentiality Style
  Guide](../confidentiality.md) says should never reach a public or customer-facing surface.

## What was found during a broader infrastructure review (2026-07-20)

Auditing beyond this project's own scope (the same server hosts several unrelated sites) found and
fixed exposed `.git` directories on three separate live sites, and a certificate that had been
silently broken for seven months because a dead subject-alternative-name was poisoning certbot's
batch renewal for every certificate on the box, not just the broken one. Unrelated to Cortexa
directly, but worth knowing this server's operator treats security findings anywhere on the box the
same way — investigate and fix, not just the piece that was asked about.
