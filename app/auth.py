"""Authentication & tenant identity.

A single FastAPI dependency, :func:`get_current_user`, resolves the caller to a
``User`` on every request. Two modes, chosen by ``ABA_AUTH_ENABLED``:

* **disabled (default)** — single-tenant/dev/CI. Every request is the configured
  ``default_user_id``; the whole deterministic test suite runs unchanged and owns
  all (backfilled) data. No token required.
* **enabled (production)** — a short-lived identity JWT (HS256) minted by the
  Next.js auth layer from the verified Google session is required in the
  ``Authorization: Bearer <jwt>`` header. We verify it against the shared
  ``ABA_AUTH_SECRET``, upsert the user, and return it.

JWT verification is implemented with the standard library (hmac/base64/json) so
the backend gains no new dependency; the Next.js side owns the Google OAuth flow.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException

from app.config import get_settings
from app.db.migrations import get_session_db


@dataclass(frozen=True)
class User:
    id: str
    email: str = ""
    name: str = ""


# ---------------------------------------------------------------------------
# Minimal HS256 JWT verification (no external dependency)
# ---------------------------------------------------------------------------
def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def verify_jwt(token: str, secret: str) -> dict:
    """Verify an HS256 JWT and return its claims. Raises ValueError on any problem."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:  # not three segments
        raise ValueError("malformed token") from exc

    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "HS256":
        raise ValueError("unexpected alg")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
        raise ValueError("bad signature")

    claims = json.loads(_b64url_decode(payload_b64))
    exp = claims.get("exp")
    if exp is not None and time.time() > float(exp) + 30:  # 30s leeway
        raise ValueError("token expired")
    return claims


# ---------------------------------------------------------------------------
# User persistence
# ---------------------------------------------------------------------------
def upsert_user(user_id: str, email: str = "", name: str = "", picture: str = "") -> None:
    """Create the user if new, else refresh profile + last_seen. Idempotent, best-effort."""
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO users (id, email, name, picture) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  email=excluded.email, name=excluded.name, picture=excluded.picture, "
            "  last_seen=datetime('now')",
            (user_id, email or "", name or "", picture or ""),
        )
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Token minting (Phase 6): personal access tokens for programmatic clients
# ---------------------------------------------------------------------------
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def mint_token(user: "User", days: int = 90) -> tuple[str, float]:
    """Mint a long-lived HS256 identity JWT for THIS user, signed with the same
    ``ABA_AUTH_SECRET`` that ``verify_jwt`` checks. This is how a signed-in user gets a
    bearer token for programmatic clients — above all external MCP clients on ``/api/mcp``
    — without an admin touching the server secret. The token carries only the caller's
    own identity, so it grants exactly what their session already grants.

    Returns (token, exp_epoch_seconds). Raises ValueError when no secret is configured.
    """
    s = get_settings()
    secret = (s.auth_secret or "").strip()
    if not secret:
        raise ValueError("ABA_AUTH_SECRET is not configured — cannot mint tokens.")
    exp = time.time() + max(1, int(days)) * 86400
    head = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user.id, "email": user.email, "name": user.name,
        "iat": int(time.time()), "exp": int(exp), "kind": "pat",
    }).encode())
    sig = _b64url_encode(
        hmac.new(secret.encode(), f"{head}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{head}.{payload}.{sig}", exp


# ---------------------------------------------------------------------------
# The dependency every user-owned route depends on
# ---------------------------------------------------------------------------
def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> User:
    s = get_settings()

    if not s.auth_enabled:
        # Single-tenant fallback — the default user is seeded by the DB migration.
        return User(id=s.default_user_id, email=s.default_user_email, name="Local User")

    if not s.auth_secret:
        # Misconfiguration: auth is on but no secret to verify tokens against.
        raise HTTPException(500, "Auth is enabled but ABA_AUTH_SECRET is not configured.")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_jwt(token, s.auth_secret)
    except ValueError as exc:
        raise HTTPException(401, f"Invalid token: {exc}")

    # Google's stable subject id is the tenant key; fall back to email if absent.
    user_id = str(claims.get("sub") or claims.get("email") or "").strip()
    if not user_id:
        raise HTTPException(401, "Token has no subject.")
    email = str(claims.get("email") or "")
    name = str(claims.get("name") or "")
    upsert_user(user_id, email, name, str(claims.get("picture") or ""))
    return User(id=user_id, email=email, name=name)


# Convenience alias for route signatures: `user: CurrentUser`.
CurrentUser = Annotated[User, Depends(get_current_user)]
