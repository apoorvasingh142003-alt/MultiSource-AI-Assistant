"""Tests for the agentic-chat upgrade: per-request temperature plumbing, multi-turn
conversation context, message edit/delete/regenerate, and agent-mode availability.

Hermetic and offline — forced to the offline floor before importing app, so no network
or API key is needed.

Run:  .venv/bin/python -m pytest tests/test_chat_upgrade.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.conversation import format_history_block, load_history  # noqa: E402
from app.llm.client import LLMClient  # noqa: E402
from app.main import app  # noqa: E402


# ---- temperature: cache key only changes for a non-zero override -------------
def test_temperature_cache_key_stable_at_zero():
    base = LLMClient._key("gen", "m", "sys", "user")
    same = LLMClient._key("gen", "m", "sys", "user", 0)        # temp 0 == default
    diff = LLMClient._key("gen", "m", "sys", "user", 0.7)      # real override
    assert base == same, "temperature 0 must not invalidate the existing cache"
    assert base != diff, "a non-zero temperature must produce a distinct cache key"


# ---- conversation history formatting ----------------------------------------
def test_format_history_block_roles_and_empty():
    assert format_history_block(None) == ""
    assert format_history_block([]) == ""
    block = format_history_block([
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ])
    assert "User: Hello" in block and "Assistant: Hi there" in block


def test_format_history_block_char_cap_keeps_recent():
    history = [{"role": "user", "content": f"line {i} " + "x" * 100} for i in range(50)]
    block = format_history_block(history, max_chars=300)
    assert len(block) <= 300
    assert "line 49" in block          # most-recent turns survive the cap


# ---- message edit / delete / regenerate -------------------------------------
def test_message_edit_delete_regenerate_roundtrip():
    c = TestClient(app)
    sid = c.post("/sessions").json()["id"]
    c.post("/ask", json={"question": "What is in the contracts?", "scope": "all", "session_id": sid})
    msgs = c.get(f"/sessions/{sid}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]

    user_id = msgs[0]["id"]
    assistant_id = msgs[1]["id"]

    # edit the user message
    edited = c.patch(f"/sessions/{sid}/messages/{user_id}", json={"content": "edited question"})
    assert edited.status_code == 200
    assert edited.json()["edited_at"]

    # regenerate the assistant turn
    regen = c.post(f"/sessions/{sid}/messages/{assistant_id}/regenerate", json={"scope": "all"})
    assert regen.status_code == 200
    assert regen.json()["answer"]

    # delete the user message
    assert c.delete(f"/sessions/{sid}/messages/{user_id}").status_code == 200
    remaining = c.get(f"/sessions/{sid}/messages").json()
    assert all(m["id"] != user_id for m in remaining)

    # 404 on unknown message
    assert c.patch(f"/sessions/{sid}/messages/nope", json={"content": "x"}).status_code == 404


def test_load_history_returns_turns_in_order():
    c = TestClient(app)
    sid = c.post("/sessions").json()["id"]
    c.post("/ask", json={"question": "First question?", "scope": "all", "session_id": sid})
    hist = load_history(sid)
    assert len(hist) >= 2
    assert hist[0]["role"] == "user" and hist[0]["content"] == "First question?"


# ---- agent mode degrades gracefully when offline ----------------------------
def test_agent_unavailable_offline():
    from app.agent.runner import agent_available
    # offline floor → no live LLM → agent must report unavailable (engine uses classic path)
    assert agent_available() is False


def test_ask_agent_mode_offline_falls_back():
    c = TestClient(app)
    r = c.post("/ask", json={"question": "What do contracts say about suspension?",
                             "scope": "all", "agent_mode": True})
    assert r.status_code == 200
    # classic path still answers (route is a normal route, not an error)
    assert r.json()["trace"]["route"]["route"] in ("PDF", "HYBRID", "SQL", "NONE", "GENERAL_KNOWLEDGE")
