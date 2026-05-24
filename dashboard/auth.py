"""
Simple HMAC-signed token auth for the FinBuddy dashboard.

No external dependencies — uses Python stdlib only. Token format:

    <base64url(payload_json)>.<base64url(hmac_sha256_signature)>

Where payload is `{"sub": "admin", "iat": <epoch>, "exp": <epoch>}`.

Two env vars must be set (we exit on startup if missing):
- DASHBOARD_PASSWORD: the single password the dashboard accepts
- DASHBOARD_SECRET_KEY: HMAC signing key (32+ random bytes recommended)

Use `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` to generate.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

# 7 days
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def get_secret_key() -> bytes:
    key = os.environ.get("DASHBOARD_SECRET_KEY", "")
    if not key:
        raise RuntimeError(
            "DASHBOARD_SECRET_KEY env var not set. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    return key.encode("utf-8")


def get_password() -> str:
    pw = os.environ.get("DASHBOARD_PASSWORD", "")
    if not pw:
        raise RuntimeError("DASHBOARD_PASSWORD env var not set.")
    return pw


def check_password(submitted: str) -> bool:
    """Constant-time comparison against DASHBOARD_PASSWORD."""
    return hmac.compare_digest(submitted.encode("utf-8"), get_password().encode("utf-8"))


def issue_token(subject: str = "admin") -> str:
    """Mint a signed token valid for TOKEN_TTL_SECONDS."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(8),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(get_secret_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


def verify_token(token: str) -> Optional[dict]:
    """Return payload dict if valid + unexpired, else None."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            get_secret_key(), payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def extract_bearer(authorization_header: Optional[str]) -> Optional[str]:
    """Pull token out of an `Authorization: Bearer <token>` header value."""
    if not authorization_header:
        return None
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
