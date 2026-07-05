"""Multi-tenancy isolation + auth dependency (Increment 1).

Two concerns:
  1. Ownership scoping — with two different users, one tenant's sessions/workspaces are
     invisible and un-mutable to the other (no cross-tenant read/delete by guessing an id).
  2. The auth dependency — when ABA_AUTH_ENABLED, a valid HS256 identity JWT is required
     and verified; a missing/tampered token is rejected.

Isolation without env pollution: we drive the real routes but (a) point the session DB at a
temp file and (b) override the get_current_user dependency to act as a chosen user. This
exercises the actual WHERE user_id = ? scoping the routes now enforce.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.auth as auth  # noqa: E402
import app.db.migrations as mig  # noqa: E402
from app.auth import User, get_current_user, verify_jwt  # noqa: E402
from app.main import app  # noqa: E402


def _mint(claims: dict, secret: str) -> str:
    b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
    head, payload = b({"alg": "HS256", "typ": "JWT"}), b(claims)
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{head}.{payload}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{head}.{payload}.{sig}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate the session DB to a fresh temp file and force a clean schema init.
    monkeypatch.setattr(mig, "_db_path", lambda: tmp_path / "sessions.db")
    monkeypatch.setattr(mig, "_initialized", False, raising=False)
    mig.init_db()
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    from app.engine import _engine_for
    _engine_for.cache_clear()  # don't leak per-user engines built during the test


def _as(uid: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: User(id=uid, email=f"{uid}@x.com")


def test_sessions_are_isolated_per_user(client):
    _as("alice")
    sid = client.post("/sessions").json()["id"]
    assert any(s["id"] == sid for s in client.get("/sessions").json())

    _as("bob")
    assert all(s["id"] != sid for s in client.get("/sessions").json())   # invisible
    assert client.get(f"/sessions/{sid}/messages").status_code == 404     # unreadable
    assert client.delete(f"/sessions/{sid}").status_code == 404           # un-deletable
    assert client.patch(f"/sessions/{sid}", json={"title": "hijack"}).status_code == 404

    _as("alice")
    assert client.delete(f"/sessions/{sid}").status_code == 200           # owner can


def test_workspaces_are_isolated_per_user(client):
    _as("alice")
    wid = client.post("/workspaces", json={"name": "A"}).json()["id"]
    assert any(w["id"] == wid for w in client.get("/workspaces").json())

    _as("bob")
    assert all(w["id"] != wid for w in client.get("/workspaces").json())
    assert client.get(f"/workspaces/{wid}/artifacts").status_code == 404
    assert client.delete(f"/workspaces/{wid}").status_code == 404
    assert client.post(f"/workspaces/{wid}/memory",
                       json={"key": "k", "value": "v"}).status_code == 404


def test_auth_dependency_requires_valid_token_when_enabled(monkeypatch):
    class _S:
        auth_enabled = True
        auth_secret = "sek"
        default_user_id = "default"
        default_user_email = "local@localhost"

    monkeypatch.setattr(auth, "get_settings", lambda: _S())
    monkeypatch.setattr(auth, "upsert_user", lambda *a, **k: None)  # no real DB write

    with pytest.raises(HTTPException) as missing:
        get_current_user(authorization=None)
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as bad:
        get_current_user(authorization="Bearer not.a.jwt")
    assert bad.value.status_code == 401

    tok = _mint({"sub": "u1", "email": "u1@x.com", "exp": time.time() + 60}, "sek")
    user = get_current_user(authorization=f"Bearer {tok}")
    assert user.id == "u1" and user.email == "u1@x.com"


def test_auth_disabled_yields_default_user(monkeypatch):
    class _S:
        auth_enabled = False
        auth_secret = None
        default_user_id = "default"
        default_user_email = "local@localhost"

    monkeypatch.setattr(auth, "get_settings", lambda: _S())
    user = get_current_user(authorization=None)   # no token needed
    assert user.id == "default"


def test_engines_are_isolated_per_user():
    from app.engine import get_engine, _engine_for
    from app.models import IngestedDocumentInfo
    _engine_for.cache_clear()
    a, b = get_engine("alice"), get_engine("bob")
    assert a is not b                       # distinct per-tenant engines
    assert a is get_engine("alice")         # cached per user
    assert a.uploads_dir != b.uploads_dir   # per-user upload dirs
    assert "alice" in str(a.uploads_dir) and "bob" in str(b.uploads_dir)

    # A document in alice's inventory/index must never appear for bob…
    a._documents.append(IngestedDocumentInfo(name="alice-secret.pdf", origin="uploaded"))
    assert "alice-secret.pdf" in {d.name for d in a.inventory().documents}
    assert "alice-secret.pdf" not in {d.name for d in b.inventory().documents}
    # …but the shared sample corpus is visible to both tenants.
    assert any(d.origin == "sample" for d in b.inventory().documents)
    _engine_for.cache_clear()


def test_inventory_endpoint_is_per_tenant(client):
    from app.engine import get_engine
    from app.models import IngestedDocumentInfo

    _as("alice")
    get_engine("alice")._documents.append(
        IngestedDocumentInfo(name="alice-upload.pdf", origin="uploaded"))
    inv_a = client.get("/inventory").json()
    assert any(d["name"] == "alice-upload.pdf" for d in inv_a["documents"])

    _as("bob")
    inv_b = client.get("/inventory").json()
    assert all(d["name"] != "alice-upload.pdf" for d in inv_b["documents"])   # isolated
    assert any(d["origin"] == "sample" for d in inv_b["documents"])           # demo shared


def test_jwt_rejects_tampering():
    tok = _mint({"sub": "u1"}, "right-secret")
    assert verify_jwt(tok, "right-secret")["sub"] == "u1"
    with pytest.raises(ValueError):
        verify_jwt(tok, "wrong-secret")
    with pytest.raises(ValueError):
        verify_jwt(tok + "x", "right-secret")   # corrupted signature
