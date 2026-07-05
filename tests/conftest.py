"""Hermetic test environment.

Loaded by pytest before any test module (and therefore before the app is imported),
so pydantic ``Settings`` reads these values. We force auth OFF here because the
developer ``.env`` may enable it for production (ABA_AUTH_ENABLED=true) — without this,
endpoint tests would suddenly require a bearer token. Environment variables take
precedence over the .env file, so this wins.
"""
import os

# Force single-tenant/no-auth for the whole suite regardless of the local .env.
os.environ["ABA_AUTH_ENABLED"] = "false"

# Offline, deterministic floor (matches each module's own setdefaults; harmless if the
# CLI already set them).
os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")
