"""ft_creds.py — Single source of truth for FreqTrade REST API credentials.

Added 2026-07-05 security pass: several scripts previously hardcoded the real
password as an os.environ.get(..., <literal>) fallback, which meant the real
credential lived in tracked source files even when unused. This resolves the
same way those scripts always intended (env var first) but falls back to
reading freqtrade/.env directly instead of a hardcoded literal, so rotating
the password in ONE place (freqtrade/.env) is enough — no source file needs
to change.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path("/home/ubuntu/var/www/html/trade/freqtrade/.env")


def read_freqtrade_env() -> dict:
    """Parse freqtrade/.env into a dict — the single source of truth for every secret
    that used to be hardcoded as a fallback literal in various scripts (API password,
    Telegram tokens, exchange keys). Safe to call repeatedly; cheap file read."""
    vals: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip()
    return vals


# Back-compat alias (internal use within this module)
_read_env_file = read_freqtrade_env


def get_ft_auth() -> tuple[str, str]:
    """Return (username, password) for the FreqTrade REST API.

    Priority: explicit FT_USER/FT_PASS (or FT_API_PASS/FT_API_USER) env vars,
    then freqtrade/.env's FREQTRADE__API_SERVER__USERNAME/PASSWORD.
    """
    env_file = _read_env_file()
    user = (
        os.environ.get("FT_USER")
        or os.environ.get("FT_API_USER")
        or env_file.get("FREQTRADE__API_SERVER__USERNAME")
        or "bot"
    )
    pw = (
        os.environ.get("FT_PASS")
        or os.environ.get("FT_API_PASS")
        or env_file.get("FREQTRADE__API_SERVER__PASSWORD")
    )
    if not pw:
        raise RuntimeError(
            "FreqTrade API password not found — set FT_PASS/FT_API_PASS env var "
            "or FREQTRADE__API_SERVER__PASSWORD in freqtrade/.env"
        )
    return user, pw
