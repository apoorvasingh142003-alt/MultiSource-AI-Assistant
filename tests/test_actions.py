"""Action-tool framework (Phase 6) — propose → confirm → execute, wall-safe.

Covers: the deterministic command detector (incl. a never-fires battery over the demo
suite), param extraction, the engine's action-command short-circuit, the suggested
escalation on an insufficient answer (label untouched), simulated + real n8n dispatch
(HMAC-signed), encrypted-at-rest config, per-tenant isolation of config/log, and the
API endpoints. Offline and hermetic (conftest forces auth off + hashing embeddings).

Run:  .venv/bin/python -m pytest tests/test_actions.py -q
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

import app.db.migrations as mig
from app.actions import service
from app.actions.detect import detect_action_command
from app.auth import User, get_current_user
from app.engine import EXAMPLES, get_engine
from app.main import app


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    """Point the state DB at a fresh temp file so action config/log are isolated."""
    monkeypatch.setattr(mig, "_db_path", lambda: tmp_path / "sessions.db")
    monkeypatch.setattr(mig, "_initialized", False, raising=False)
    mig.init_db()
    yield tmp_path / "sessions.db"


@pytest.fixture
def client(state_db):
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _as(uid: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: User(id=uid, email=f"{uid}@x.com")


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def test_detects_create_lead_with_params():
    cmd = detect_action_command(
        "Create a lead for Jane Smith (jane.smith@acme.com) at Acme Corp — she asked about onboarding."
    )
    assert cmd is not None and cmd.action == "create_lead"
    assert cmd.params["name"] == "Jane Smith"
    assert cmd.params["email"] == "jane.smith@acme.com"
    assert cmd.params["company"] == "Acme Corp"
    assert "onboarding" in cmd.params.get("note", "")


def test_detects_escalate_variants():
    for q in ("Escalate this to a human please",
              "I want to talk to a human agent",
              "Hand this over to a person"):
        cmd = detect_action_command(q)
        assert cmd is not None and cmd.action == "escalate", q
        assert cmd.params["reason"]


def test_detects_create_invoice_with_amount():
    cmd = detect_action_command("Raise an invoice for ACME Corp for $1,200 — Q3 retainer.")
    assert cmd is not None and cmd.action == "create_invoice"
    assert cmd.params["customer"].startswith("ACME")
    assert cmd.params["amount"] == "1200"
    assert cmd.params["currency"] == "USD"


def test_never_fires_on_demo_suite_or_factual_questions():
    for ex in EXAMPLES:
        assert detect_action_command(ex.question) is None, ex.question
    # noun-before-verb and analytical mentions must not trip the cues
    for q in ("Which invoices were issued in March?",
              "Show the invoice breakdown per customer",
              "How many leads did we capture last quarter?"):
        assert detect_action_command(q) is None, q


# --------------------------------------------------------------------------- #
# Engine wiring
# --------------------------------------------------------------------------- #
def test_engine_action_command_short_circuits(state_db):
    resp = get_engine().ask("Create a lead for John Doe (john@doe.io) at Doe GmbH")
    assert resp.action_only is True
    assert len(resp.actions) == 1
    a = resp.actions[0]
    assert a.action == "create_lead" and a.origin == "command" and not a.missing
    # no retrieval ran, no knowledge claims, nothing dispatched
    assert resp.trace.evidence == [] and not resp.citations
    assert resp.trace.route and resp.trace.route.route == "NONE"
    assert "confirm" in resp.answer.lower()
    assert service.list_log(get_engine().user_id) == []
    # the proposal is mirrored into the trace for the inspector
    assert resp.trace.actions and resp.trace.actions[0]["action"] == "create_lead"


def test_insufficient_answer_carries_suggested_escalation(state_db):
    resp = get_engine().ask("What is our employee headcount in Berlin?")
    assert resp.insufficient and resp.answer_state == "insufficient"
    esc = [a for a in resp.actions if a.action == "escalate"]
    assert len(esc) == 1 and esc[0].origin == "suggested"
    assert esc[0].params["reason"]
    # the wall is untouched: still the honest decline, nothing executed
    assert service.list_log(get_engine().user_id) == []


def test_grounded_answer_gets_no_escalation(state_db):
    resp = get_engine().ask("What do our contracts say about service suspension?")
    assert resp.answer_state == "grounded"
    assert [a for a in resp.actions if a.origin == "suggested"] == []


# --------------------------------------------------------------------------- #
# Config store + dispatch
# --------------------------------------------------------------------------- #
def test_execute_without_webhook_is_simulated_and_logged(state_db):
    res = service.execute("u1", "escalate", {"reason": "cannot answer"}, session_id=None)
    assert res.status == "simulated"
    log = service.list_log("u1")
    assert len(log) == 1 and log[0]["action"] == "escalate" and log[0]["status"] == "simulated"


def test_execute_missing_required_param_errors(state_db):
    res = service.execute("u1", "create_invoice", {"customer": "Acme"})
    assert res.status == "error" and "amount" in res.detail


def test_unknown_and_disabled_actions_error(state_db):
    assert service.execute("u1", "rm_rf", {}).status == "error"
    service.set_config("u1", "create_lead", enabled=False)
    res = service.execute("u1", "create_lead", {"name": "X"})
    assert res.status == "error" and "disabled" in res.detail.lower()


def test_config_encrypted_at_rest_and_tenant_scoped(state_db):
    service.set_config("u1", "create_lead", webhook_url="https://n8n.example/hook", secret="s3cret")
    db = mig.get_session_db()
    try:
        row = db.execute(
            "SELECT webhook_url, secret FROM action_configs WHERE user_id='u1'"
        ).fetchone()
    finally:
        db.close()
    assert row["webhook_url"].startswith("enc:v1:")
    assert row["secret"].startswith("enc:v1:")
    # tenant isolation: u2 sees the default (unconfigured) state
    assert service.get_config("u2", "create_lead")["webhook_url"] == ""
    assert service.get_config("u1", "create_lead")["webhook_url"] == "https://n8n.example/hook"


def test_dispatch_posts_signed_payload_to_webhook(state_db):
    """A real n8n round-trip against a local HTTP server, HMAC verified."""
    received: dict = {}

    class Hook(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received["body"] = body
            received["signature"] = self.headers.get("X-ABA-Signature")
            received["action"] = self.headers.get("X-ABA-Action")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):  # keep test output clean
            pass

    server = HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/webhook/lead"
        service.set_config("u1", "create_lead", webhook_url=url, secret="topsecret")
        res = service.execute("u1", "create_lead",
                              {"name": "Jane", "email": "j@a.com"}, session_id="sess-1")
        assert res.status == "executed" and "HTTP 200" in res.detail
        payload = json.loads(received["body"])
        assert payload["action"] == "create_lead"
        assert payload["params"] == {"name": "Jane", "email": "j@a.com"}
        assert payload["user_id"] == "u1" and payload["session_id"] == "sess-1"
        expected = hmac.new(b"topsecret", received["body"], hashlib.sha256).hexdigest()
        assert received["signature"] == f"sha256={expected}"
        assert received["action"] == "create_lead"
        assert service.list_log("u1")[0]["status"] == "executed"
    finally:
        server.shutdown()


def test_dispatch_unreachable_webhook_is_logged_error(state_db):
    service.set_config("u1", "escalate", webhook_url="http://127.0.0.1:1/nope")
    res = service.execute("u1", "escalate", {"reason": "x"})
    assert res.status == "error"
    assert service.list_log("u1")[0]["status"] == "error"


# --------------------------------------------------------------------------- #
# API endpoints
# --------------------------------------------------------------------------- #
def test_actions_endpoints_roundtrip(client):
    _as("api-user")
    cat = client.get("/actions").json()
    assert {c["action"] for c in cat} == {"create_lead", "escalate", "create_invoice"}
    assert all(not c["configured"] and c["enabled"] for c in cat)

    r = client.post("/actions/config", json={"action": "create_lead",
                                             "webhook_url": "https://n8n.example/hook"})
    assert r.status_code == 200 and r.json()["configured"] is True
    assert client.post("/actions/config", json={"action": "nope"}).status_code == 400

    r = client.post("/actions/execute", json={"action": "escalate",
                                              "params": {"reason": "help"}})
    assert r.status_code == 200 and r.json()["status"] == "simulated"

    log = client.get("/actions/log").json()
    assert len(log) == 1 and log[0]["action"] == "escalate"

    # another tenant sees neither the config nor the log
    _as("other-user")
    assert all(not c["configured"] for c in client.get("/actions").json())
    assert client.get("/actions/log").json() == []
