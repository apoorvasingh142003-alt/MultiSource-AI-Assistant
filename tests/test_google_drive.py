"""Google Drive connector (Phase 6): link parsing, listing, and import into a per-user
engine (HTTP stubbed). Plus the /mcp/token personal-access-token flow. Hermetic, offline.

Run:  .venv/bin/python -m pytest tests/test_google_drive.py -q
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import app.integrations.google_drive as gd
from app.auth import User, get_current_user, mint_token, verify_jwt
from app.main import app

PDF_BYTES = b"%PDF-1.4 fake body"
FILE_ID = "1AbC_dEfG-hijkLMNOpqrstuvwxyz012345"


def test_parse_file_id_variants():
    assert gd.parse_file_id(f"https://drive.google.com/file/d/{FILE_ID}/view") == FILE_ID
    assert gd.parse_file_id(f"https://docs.google.com/document/d/{FILE_ID}/edit") == FILE_ID
    assert gd.parse_file_id(f"https://drive.google.com/open?id={FILE_ID}") == FILE_ID
    assert gd.parse_file_id(FILE_ID) == FILE_ID
    with pytest.raises(gd.DriveError):
        gd.parse_file_id("not a drive link")


def test_list_documents_maps_kinds(monkeypatch):
    monkeypatch.setattr(gd, "_get_json", lambda url, token: {"files": [
        {"id": "a", "name": "Contract.pdf", "mimeType": "application/pdf",
         "modifiedTime": "2026-07-01T00:00:00Z", "size": "1234"},
        {"id": "b", "name": "Notes", "mimeType": "application/vnd.google-apps.document",
         "modifiedTime": "2026-07-02T00:00:00Z"},
    ]})
    files = gd.list_documents("tok")
    assert [(f["id"], f["kind"], f["size"]) for f in files] == [
        ("a", "pdf", 1234), ("b", "gdoc", None)]


class _StubEngine:
    """Captures what import_file_for_user hands to the engine."""

    def __init__(self, tmp_path):
        self.uploads_dir = tmp_path
        self.added: list[tuple[str, bytes]] = []

    def add_pdf(self, name, path):
        from app.models import IngestedDocumentInfo
        self.added.append((name, path.read_bytes()))
        return IngestedDocumentInfo(name=name, origin="uploaded", status="indexed",
                                    chunks_indexed=4, pages=2)


@pytest.fixture
def stub_engine(tmp_path, monkeypatch):
    eng = _StubEngine(tmp_path)
    import app.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda uid=None: eng)
    return eng


def test_import_native_pdf(stub_engine, monkeypatch):
    monkeypatch.setattr(gd, "_get_json", lambda url, token: {
        "id": FILE_ID, "name": "MSA (final).pdf", "mimeType": "application/pdf", "size": "18"})
    monkeypatch.setattr(gd, "_get_bytes", lambda url, token: PDF_BYTES)
    res = gd.import_file_for_user("u1", "tok", f"https://drive.google.com/file/d/{FILE_ID}/view")
    assert res["ok"] and res["source"] == "pdf" and res["chunks_indexed"] == 4
    (name, data), = stub_engine.added
    assert name.endswith(".pdf") and data == PDF_BYTES


def test_import_google_doc_exports_pdf(stub_engine, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(gd, "_get_json", lambda url, token: {
        "id": FILE_ID, "name": "Strategy Notes",
        "mimeType": "application/vnd.google-apps.document"})

    def _bytes(url, token):
        calls.append(url)
        return PDF_BYTES
    monkeypatch.setattr(gd, "_get_bytes", _bytes)
    res = gd.import_file_for_user("u1", "tok", FILE_ID)
    assert res["ok"] and res["source"] == "gdoc"
    assert "/export?" in calls[0] and "application%2Fpdf" in calls[0]


def test_import_rejects_other_types_and_non_pdf_bytes(stub_engine, monkeypatch):
    monkeypatch.setattr(gd, "_get_json", lambda url, token: {
        "id": FILE_ID, "name": "photo.png", "mimeType": "image/png"})
    with pytest.raises(gd.DriveError):
        gd.import_file_for_user("u1", "tok", FILE_ID)
    monkeypatch.setattr(gd, "_get_json", lambda url, token: {
        "id": FILE_ID, "name": "x.pdf", "mimeType": "application/pdf"})
    monkeypatch.setattr(gd, "_get_bytes", lambda url, token: b"<html>login page</html>")
    with pytest.raises(gd.DriveError):
        gd.import_file_for_user("u1", "tok", FILE_ID)
    assert stub_engine.added == []


def test_drive_endpoints_require_google_token():
    client = TestClient(app)
    assert client.get("/drive/files").status_code == 400
    assert client.post("/drive/import", json={"url": "x"}).status_code == 400


# --------------------------------------------------------------------------- #
# MCP personal access tokens
# --------------------------------------------------------------------------- #
def test_mint_token_roundtrips_through_verify(monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "auth_secret", "unit-test-secret")
    token, exp = mint_token(User(id="u42", email="u@x.com", name="U"), days=7)
    assert exp > time.time() + 6 * 86400
    claims = verify_jwt(token, "unit-test-secret")
    assert claims["sub"] == "u42" and claims["kind"] == "pat"
    # tampering breaks it
    with pytest.raises(ValueError):
        verify_jwt(token[:-4] + "AAAA", "unit-test-secret")


def test_mcp_token_endpoint_auth_off_hint():
    client = TestClient(app)
    r = client.post("/mcp/token", json={"days": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is False and body["token"] is None


def test_mcp_token_endpoint_auth_on(monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "auth_enabled", True)
    monkeypatch.setattr(s, "auth_secret", "unit-test-secret")
    app.dependency_overrides[get_current_user] = lambda: User(id="u1", email="u1@x.com")
    try:
        client = TestClient(app)
        r = client.post("/mcp/token", json={"days": 9999})
        assert r.status_code == 200
        body = r.json()
        assert body["auth_enabled"] is True and body["days"] == 365   # clamped
        assert verify_jwt(body["token"], "unit-test-secret")["sub"] == "u1"
    finally:
        app.dependency_overrides.clear()
