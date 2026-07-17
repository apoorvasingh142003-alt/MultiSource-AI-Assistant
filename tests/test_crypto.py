"""Secrets-at-rest encryption (app/crypto.py).

Hermetic + deterministic: with no ABA_ENCRYPTION_KEY / ABA_AUTH_SECRET configured, crypto
falls back to the built-in dev key, so the roundtrip works with zero config (matching the
offline test floor). Verifies ciphertext ≠ plaintext, the versioned format, backward-compatible
decryption of legacy plaintext, and fail-open behaviour on garbage input.

Run:  .venv/bin/python -m pytest tests/test_crypto.py -q
"""
from __future__ import annotations

from app import crypto


def test_roundtrip():
    token = "pat-na2-super-secret-value"
    enc = crypto.encrypt(token)
    assert enc != token
    assert crypto.is_encrypted(enc)
    assert enc.startswith("enc:v1:")
    assert crypto.decrypt(enc) == token


def test_ciphertext_is_not_plaintext():
    token = "sensitive-oauth-token"
    enc = crypto.encrypt(token)
    # the raw secret must not appear anywhere in the stored value
    assert token not in enc


def test_legacy_plaintext_decrypts_unchanged():
    # rows written before encryption existed have no enc:v1: prefix — returned as-is.
    assert crypto.decrypt("pat-legacy-plaintext") == "pat-legacy-plaintext"
    assert not crypto.is_encrypted("pat-legacy-plaintext")


def test_empty_and_none_passthrough():
    assert crypto.encrypt("") == ""
    assert crypto.decrypt("") == ""
    assert crypto.decrypt(None) is None


def test_garbage_ciphertext_fails_open():
    # a corrupted enc:v1: value must never raise — it returns the raw stored value.
    garbage = "enc:v1:not-a-real-fernet-token"
    assert crypto.decrypt(garbage) == garbage


def test_two_encryptions_differ_but_both_decrypt():
    # Fernet embeds a random IV + timestamp, so ciphertexts differ; both decrypt correctly.
    a = crypto.encrypt("same-secret")
    b = crypto.encrypt("same-secret")
    assert a != b
    assert crypto.decrypt(a) == crypto.decrypt(b) == "same-secret"
