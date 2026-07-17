"""Symmetric encryption for secrets stored at rest (OAuth / provider tokens).

The only persisted third-party secret today is a tenant's HubSpot Private-App token in
``integration_tokens.token``. Before any shared/cloud deployment that column must not be
plaintext. This module gives every persisted secret authenticated encryption (Fernet:
AES-128-CBC + HMAC-SHA256) with a key derived from the deployment's own secret — no new
env var is required (it falls back to ``ABA_AUTH_SECRET``), and there is a deterministic
dev/CI fallback so the offline test suite runs with no configuration at all.

Storage format is versioned and self-describing:

    enc:v1:<urlsafe-b64 fernet token>

``decrypt`` is deliberately **fail-open on read**: a value without the ``enc:v1:`` prefix is
returned unchanged (legacy plaintext rows written before encryption existed), and an
undecryptable ciphertext returns the raw stored value rather than raising — a corrupted row
must never take down an integration. Encryption on *write* is always applied.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

log = logging.getLogger("aba.crypto")

_PREFIX = "enc:v1:"
# Stable fallback used only when no deployment secret is configured (auth-off dev + CI).
# It keeps the encrypt/decrypt roundtrip deterministic with zero config; it is NOT a
# security boundary — production sets ABA_ENCRYPTION_KEY or ABA_AUTH_SECRET.
_DEV_FALLBACK_SECRET = "aba-local-dev-encryption-key-not-for-production"

_fernet: Fernet | None = None


def _derive_key(secret: str) -> bytes:
    """Derive a urlsafe-base64 32-byte Fernet key deterministically from a secret string."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        s = get_settings()
        secret = (s.encryption_key or s.auth_secret or _DEV_FALLBACK_SECRET).strip()
        if secret == _DEV_FALLBACK_SECRET:
            log.warning(
                "Secrets-at-rest using the built-in dev key — set ABA_ENCRYPTION_KEY "
                "(or ABA_AUTH_SECRET) before any shared deployment."
            )
        _fernet = Fernet(_derive_key(secret))
    return _fernet


def reset_cache() -> None:
    """Drop the cached Fernet (used by tests that swap the configured secret)."""
    global _fernet
    _fernet = None


def encrypt(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns a versioned ``enc:v1:…`` string.

    An empty/None value is returned unchanged (nothing to protect)."""
    if not plaintext:
        return plaintext
    token = _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt(stored: str | None) -> str | None:
    """Decrypt a stored secret. Fail-open on read (see module docstring):

    * ``None``/empty → returned as-is.
    * no ``enc:v1:`` prefix → legacy plaintext, returned unchanged.
    * undecryptable ciphertext → the raw stored value (never raises).
    """
    if not stored or not stored.startswith(_PREFIX):
        return stored
    token = stored[len(_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        log.error("Failed to decrypt a stored secret — returning the raw value.")
        return stored


def is_encrypted(stored: str | None) -> bool:
    """True if the value is in the encrypted-at-rest format."""
    return bool(stored) and stored.startswith(_PREFIX)
