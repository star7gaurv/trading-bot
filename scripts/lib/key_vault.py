"""PyNaCl envelope encryption for customer exchange API keys (Phase 3.3).

Two-layer scheme:
  KEK (key-encryption-key) — lives outside the repo and DB at
    /etc/finbuddy/platform_master.key (root:600), same pattern as the
    existing /etc/finbuddy/dashboard.env secret. Never stored in Postgres.
  DEK (data-encryption-key) — one per stored API key, randomly generated,
    encrypts the actual secret, then is itself "wrapped" (encrypted) by the
    KEK before being stored alongside the ciphertext. A DB leak alone never
    exposes plaintext — the KEK on disk is also required.

Losing the master key means every customer must re-enter their exchange
key — back it up offline, never alongside automated DB backups.

Interface is deliberately small (encrypt_secret/decrypt_secret) so a future
swap to a cloud KMS doesn't touch calling code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import nacl.secret
import nacl.utils

KEK_PATH = Path(os.environ.get("FINBUDDY_PLATFORM_KEK_PATH", "/etc/finbuddy/platform_master.key"))


class MasterKeyMissing(RuntimeError):
    pass


def _load_kek() -> bytes:
    if not KEK_PATH.exists():
        raise MasterKeyMissing(
            f"Platform master key not found at {KEK_PATH}. Generate one with "
            "generate_master_key() and install it root:600 before storing or "
            "reading any customer API key."
        )
    key = KEK_PATH.read_bytes()
    if len(key) != nacl.secret.SecretBox.KEY_SIZE:
        raise ValueError(
            f"Master key at {KEK_PATH} is {len(key)} bytes, expected {nacl.secret.SecretBox.KEY_SIZE}"
        )
    return key


def generate_master_key() -> bytes:
    """Generate a new 32-byte KEK. Caller is responsible for writing it to
    KEK_PATH with root:600 permissions — this function never touches disk."""
    return nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)


@dataclass
class EncryptedSecret:
    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes


def encrypt_secret(plaintext: str) -> EncryptedSecret:
    """Encrypt a customer exchange API secret (or key) for storage.
    Generates a fresh DEK per call — never reuse a DEK across secrets."""
    kek = _load_kek()
    dek = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)

    data_box = nacl.secret.SecretBox(dek)
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    encrypted = data_box.encrypt(plaintext.encode("utf-8"), nonce)

    kek_box = nacl.secret.SecretBox(kek)
    wrapped_dek = kek_box.encrypt(bytes(dek))  # self-contained blob, own random nonce

    return EncryptedSecret(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        wrapped_dek=bytes(wrapped_dek),
    )


def decrypt_secret(record: EncryptedSecret) -> str:
    """Decrypt a stored secret back to plaintext. Only ever call this
    in-memory, immediately before use (e.g. building a scoped ccxt client)
    — never log or persist the return value."""
    kek = _load_kek()
    kek_box = nacl.secret.SecretBox(kek)
    dek = kek_box.decrypt(record.wrapped_dek)

    data_box = nacl.secret.SecretBox(dek)
    plaintext = data_box.decrypt(record.ciphertext, record.nonce)
    return plaintext.decode("utf-8")


def check_non_custodial(exchange_id: str, api_key: str, api_secret: str) -> tuple[bool | None, str]:
    """Best-effort check that a customer-supplied key cannot withdraw funds.

    Returns (ok, detail):
      ok=True  — positively confirmed trade-only (withdrawals disabled)
      ok=False — withdrawal permission detected, MUST be rejected
      ok=None  — could not be positively confirmed (exchange has no unified
                 permissions probe wired up yet); treat as unverified, never
                 as safe. Callers must not silently accept a None result.

    Honesty rule, same as the arbitrage module's gap classification: absence
    of evidence is not evidence of safety. Only exchanges with an explicit
    check implemented below ever return True.
    """
    import ccxt  # local import — this module is imported by code that may not need ccxt

    if not hasattr(ccxt, exchange_id):
        return None, f"unknown exchange id '{exchange_id}'"

    client = getattr(ccxt, exchange_id)({"apiKey": api_key, "secret": api_secret, "enableRateLimit": True})
    try:
        if exchange_id == "binance":
            restrictions = client.sapiGetAccountApiRestrictions()
            withdrawals_enabled = bool(restrictions.get("enableWithdrawals"))
            if withdrawals_enabled:
                return False, "withdrawals ENABLED on this key — reject"
            return True, "withdrawals disabled, trade-only confirmed"

        return None, f"no permission-introspection implemented for '{exchange_id}' yet — treat as unverified"
    except Exception as e:
        return None, f"permission check failed: {e}"
    finally:
        close = getattr(client, "close", None)
        if close:
            try:
                close()
            except Exception:
                pass
