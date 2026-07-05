"""Telegram channel: link codes, chat→tenant resolution, and inbound answering.

Network (Telegram Bot API) and the engine are stubbed, and the link DB is a temp file,
so this is hermetic and offline.
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")

import pytest  # noqa: E402

import app.channels.telegram as tg  # noqa: E402
import app.db.migrations as mig  # noqa: E402


@pytest.fixture
def sent(tmp_path, monkeypatch):
    # Temp link DB.
    monkeypatch.setattr(mig, "_db_path", lambda: tmp_path / "sessions.db")
    monkeypatch.setattr(mig, "_initialized", False, raising=False)
    mig.init_db()
    # Capture outbound Telegram API calls instead of hitting the network.
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(tg, "_api", lambda method, payload: calls.append((method, payload)) or {"ok": True})
    return calls


def _msg(chat_id: int, text: str) -> dict:
    return {"message": {"chat": {"id": chat_id}, "text": text}}


def test_link_code_roundtrip_binds_chat_to_user(sent):
    info = tg.create_link_code("alice")
    code = info["code"]
    assert len(code) == 8

    # Redeem from Telegram via /start <code>
    tg.handle_update(_msg(555, f"/start {code}"))
    assert tg.resolve_user(555) == "alice"
    assert tg.link_status("alice") == {"linked": True, "chats": 1}
    assert any("Linked" in p.get("text", "") for _, p in sent)

    # Code is single-use.
    tg.handle_update(_msg(666, f"/start {code}"))
    assert tg.resolve_user(666) is None


def test_unlinked_chat_gets_welcome_not_an_answer(sent, monkeypatch):
    called = {"ask": 0}

    class _Eng:
        def ask(self, *a, **k):
            called["ask"] += 1
            raise AssertionError("engine must not run for an unlinked chat")

    monkeypatch.setattr("app.engine.get_engine", lambda uid=None: _Eng())
    tg.handle_update(_msg(999, "what meds does the patient take?"))
    assert called["ask"] == 0
    assert any("isn't linked" in p.get("text", "") or "Connect" in p.get("text", "") for _, p in sent)


def test_linked_chat_answers_via_that_users_engine(sent, monkeypatch):
    seen = {}

    class _Route:
        route, confidence = "PDF", 0.9

    class _Trace:
        route = _Route()

    class _Resp:
        answer, trace = "Donepezil 10mg, Metformin.", _Trace()

    class _Eng:
        def ask(self, q, **k):
            seen["q"], seen["session"] = q, k.get("session_id")
            return _Resp()

    def _get_engine(uid=None):
        seen["uid"] = uid
        return _Eng()

    monkeypatch.setattr("app.engine.get_engine", _get_engine)

    tg.create_link_code("bob")
    code = tg.create_link_code("bob")["code"]   # latest code
    tg.handle_update(_msg(42, f"/start {code}"))
    tg.handle_update(_msg(42, "what meds?"))

    assert seen["uid"] == "bob"                    # ran bob's isolated engine
    assert seen["session"] == "tg:42"              # per-chat session
    assert any(p.get("text") == "Donepezil 10mg, Metformin." for _, p in sent)


def test_expired_code_is_rejected(sent, monkeypatch):
    info = tg.create_link_code("carol")
    # Force the stored code to be already expired.
    db = mig.get_session_db()
    db.execute("UPDATE channel_link_codes SET expires_at = '2000-01-01 00:00:00' WHERE code = ?",
               (info["code"],))
    db.commit()
    db.close()
    tg.handle_update(_msg(7, f"/start {info['code']}"))
    assert tg.resolve_user(7) is None
    assert any("invalid or expired" in p.get("text", "") for _, p in sent)


def test_unlink_removes_binding(sent):
    code = tg.create_link_code("dave")["code"]
    tg.handle_update(_msg(11, f"/start {code}"))
    assert tg.resolve_user(11) == "dave"
    tg.unlink("dave")
    assert tg.resolve_user(11) is None
    assert tg.link_status("dave")["linked"] is False
