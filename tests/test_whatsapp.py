"""WhatsApp channel: webhook verification, link codes, chat→tenant resolution, answering.
Sends and the engine are stubbed; the link DB is a temp file. Hermetic and offline.
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")

import pytest  # noqa: E402

import app.channels.whatsapp as wa  # noqa: E402
import app.db.migrations as mig  # noqa: E402


@pytest.fixture
def sent(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "_db_path", lambda: tmp_path / "sessions.db")
    monkeypatch.setattr(mig, "_initialized", False, raising=False)
    mig.init_db()
    out: list[tuple[str, str]] = []
    monkeypatch.setattr(wa, "send_message", lambda wa_id, text: out.append((wa_id, text)))
    return out


def _inbound(wa_id: str, text: str) -> dict:
    return {"entry": [{"changes": [{"value": {"messages": [
        {"type": "text", "from": wa_id, "text": {"body": text}}]}}]}]}


def test_verify_webhook(monkeypatch):
    class _S:
        whatsapp_verify_token = "v-secret"
    monkeypatch.setattr(wa, "get_settings", lambda: _S())
    assert wa.verify_webhook("subscribe", "v-secret", "challenge-123") == "challenge-123"
    assert wa.verify_webhook("subscribe", "wrong", "x") is None
    assert wa.verify_webhook(None, None, "x") is None


def test_link_code_roundtrip(sent):
    code = wa.create_link_code("alice")["code"]
    wa.handle_webhook(_inbound("15551230000", f"LINK {code}"))
    assert wa.resolve_user("15551230000") == "alice"
    assert wa.link_status("alice") == {"linked": True, "chats": 1}
    assert any("Linked" in t for _, t in sent)


def test_bare_code_without_prefix_also_links(sent):
    code = wa.create_link_code("carol")["code"]
    wa.handle_webhook(_inbound("15551231111", code))   # no "LINK " prefix
    assert wa.resolve_user("15551231111") == "carol"


def test_unlinked_gets_welcome(sent, monkeypatch):
    monkeypatch.setattr("app.engine.get_engine",
                        lambda uid=None: (_ for _ in ()).throw(AssertionError("must not run")))
    wa.handle_webhook(_inbound("999", "what are my overdue invoices?"))
    assert any("isn't linked" in t or "Connect WhatsApp" in t for _, t in sent)


def test_linked_answers_via_that_users_engine(sent, monkeypatch):
    seen = {}

    class _Route:
        route, confidence = "SQL", 0.8

    class _Trace:
        route = _Route()

    class _Resp:
        answer, trace = "You have 3 overdue invoices.", _Trace()

    class _Eng:
        def ask(self, q, **k):
            seen["uid_q"] = (k.get("session_id"), q)
            return _Resp()

    def _get_engine(uid=None):
        seen["uid"] = uid
        return _Eng()

    monkeypatch.setattr("app.engine.get_engine", _get_engine)

    code = wa.create_link_code("dave")["code"]
    wa.handle_webhook(_inbound("42", f"LINK {code}"))
    wa.handle_webhook(_inbound("42", "how many overdue invoices?"))

    assert seen["uid"] == "dave"
    assert seen["uid_q"][0] == "wa:42"
    assert any(t == "You have 3 overdue invoices." for _, t in sent)
