# Dashboard Backend

The FastAPI service behind the operator dashboard. Password-gated, operator-only — see the
[Confidentiality Style Guide](confidentiality.md) for why this is fine to document with real
system names even though customer-facing surfaces are not.

::: auth

::: system_health

::: cron_status

Note: `streamer.py` (the main API surface, ~2000 lines) is intentionally not fully rendered here
via mkdocstrings — it's large enough that a full auto-generated dump is more noise than signal.
Read it directly for the endpoint list; this page covers the smaller, more stable supporting
modules.
