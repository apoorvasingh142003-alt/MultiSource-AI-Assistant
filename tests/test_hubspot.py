"""HubSpot integration: token storage, paginated fetch, and import into a (stubbed)
per-user engine. HTTP and engine are stubbed; the token DB is a temp file. Hermetic.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("ABA_OFFLINE_MODE", "always")

import pytest  # noqa: E402

import app.db.migrations as mig  # noqa: E402
import app.integrations.hubspot as hs  # noqa: E402


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "_db_path", lambda: tmp_path / "sessions.db")
    monkeypatch.setattr(mig, "_initialized", False, raising=False)
    mig.init_db()
    return tmp_path


def test_token_storage_roundtrip(tmpdb):
    assert hs.get_token("alice") is None
    assert hs.status("alice") == {"connected": False}
    hs.save_token("alice", "pat-na2-abc")
    assert hs.get_token("alice") == "pat-na2-abc"
    assert hs.status("alice") == {"connected": True}
    hs.save_token("alice", "pat-na2-new")     # upsert
    assert hs.get_token("alice") == "pat-na2-new"
    hs.delete_token("alice")
    assert hs.get_token("alice") is None


def test_fetch_objects_paginates(monkeypatch):
    pages = [
        {"results": [{"id": "1", "properties": {"email": "a@b.com"}}],
         "paging": {"next": {"after": "100"}}},
        {"results": [{"id": "2", "properties": {"email": "c@d.com"}}]},  # no paging → stop
    ]
    calls = {"n": 0}

    def _get(url, token):
        i = calls["n"]; calls["n"] += 1
        return pages[i]

    monkeypatch.setattr(hs, "_get", _get)
    rows = hs.fetch_objects("tok", "contacts", ["email"])
    assert [r["id"] for r in rows] == ["1", "2"]
    assert rows[0]["email"] == "a@b.com"


def test_import_for_user_builds_crm_tables(tmp_path, monkeypatch):
    def _get(url, token):
        if "contacts" in url:
            return {"results": [{"id": "1", "properties": {"firstname": "Ada", "email": "ada@x.com"}}]}
        if "companies" in url:
            return {"results": [{"id": "2", "properties": {"name": "Acme"}}]}
        if "deals" in url:
            return {"results": [{"id": "3", "properties": {"dealname": "Big Deal", "amount": "1000"}}]}
        return {"results": []}

    monkeypatch.setattr(hs, "_get", _get)

    added = {}

    class _Info:
        status = "indexed"

    class _Eng:
        uploads_dir = tmp_path

        def add_database(self, name, path):
            added["name"], added["path"] = name, path
            return _Info()

    monkeypatch.setattr("app.engine.get_engine", lambda uid=None: _Eng())

    res = hs.import_for_user("alice", "tok")
    assert res["ok"]
    assert res["imported"] == {"contacts": 1, "companies": 1, "deals": 1}
    assert added["name"] == "HubSpot CRM"

    # all three tables materialised into one SQLite file
    conn = sqlite3.connect(str(added["path"]))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"hubspot_contacts", "hubspot_companies", "hubspot_deals"} <= tables


def test_connect_and_import_validates_then_stores(tmp_path, tmpdb, monkeypatch):
    monkeypatch.setattr(hs, "_get", lambda url, token: {"results": [
        {"id": "1", "properties": {"email": "a@b.com"}}]})

    class _Eng:
        uploads_dir = tmp_path
        def add_database(self, name, path):
            class I: status = "indexed"
            return I()

    monkeypatch.setattr("app.engine.get_engine", lambda uid=None: _Eng())
    hs.connect_and_import("bob", "pat-na2-xyz")
    assert hs.get_token("bob") == "pat-na2-xyz"   # stored after successful validate+import
