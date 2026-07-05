"""Router robustness — make a weak local model route as reliably as a strong API model.

These cover the three defences added so a 7B local model can't silently send a
document-answerable question to the ungrounded parametric path (the nursing-home incident):

1. ``_coerce_route`` tolerates malformed / partial JSON instead of crashing or mis-routing.
2. A low-confidence parametric route is reconciled toward the grounded route the rule layer
   found (GENERAL_KNOWLEDGE/NONE → PDF/SQL/HYBRID, never the reverse).
3. A high-confidence genuine general-knowledge route is still respected.

The robustness layer is live-only (``use_live_llm`` + ``call.mode == "live"``), so these
tests force a live-ish settings object and stub the LLM with ``mode="live"`` calls.

Run:  .venv/bin/python -m pytest tests/test_router_robustness.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

import pytest  # noqa: E402

import app.routing.classify as cl  # noqa: E402
from app.config import Settings  # noqa: E402
from app.models import LLMCall  # noqa: E402

_GK_FIELDS = {
    "reasoning": "answerable from world knowledge",
    "languages": ["en"], "document_subquery": "", "sql_subquery": "",
    "entity_hint": "", "agentic": False, "strategy_note": "",
}


def _live_settings() -> Settings:
    s = Settings()
    s.offline_mode = "never"        # forces use_live_llm True without a real key
    return s


class _StubLLM:
    """Returns a fixed routing payload, tagged mode='live' so the robustness path runs."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def structured(self, **kw):
        self.calls += 1
        return dict(self.payload), LLMCall(purpose=kw.get("purpose", "routing"),
                                           model="stub", mode="live")


# --- _coerce_route: malformed/partial payloads degrade gracefully --------------------
def test_coerce_route_fills_missing_fields_from_rule_layer():
    fb = cl.rule_route("Who prepared the proposal?")
    d = cl._coerce_route({"route": "PDF"}, fb)        # only `route`, every other field missing
    assert d.route == "PDF"
    assert 0.0 <= d.confidence <= 1.0
    assert d.languages                                # filled from the rule layer


@pytest.mark.parametrize("bad", [None, "not a dict", 42, {"route": "WAT"}, {"confidence": "high"}])
def test_coerce_route_never_crashes_on_garbage(bad):
    fb = cl.rule_route("How many invoices are overdue?")
    d = cl._coerce_route(bad, fb)
    assert d.route in cl._VALID_ROUTES                # a usable decision, not an exception
    if isinstance(bad, dict) and bad.get("route") not in cl._VALID_ROUTES:
        assert d.route == fb.route                    # invalid route → rule layer


def test_coerce_route_clamps_confidence():
    fb = cl.rule_route("x")
    assert cl._coerce_route({"route": "PDF", "confidence": 5.0}, fb).confidence == 1.0
    assert cl._coerce_route({"route": "PDF", "confidence": -3}, fb).confidence == 0.0


# --- reconciliation: a weak router can't bypass a grounded source --------------------
def test_low_confidence_general_knowledge_reconciled_to_grounded(monkeypatch):
    monkeypatch.setattr(cl, "get_settings", _live_settings)
    monkeypatch.setattr(cl, "_is_general_knowledge", lambda q: True)
    stub = _StubLLM({"route": "GENERAL_KNOWLEDGE", "confidence": 0.3, **_GK_FIELDS})
    monkeypatch.setattr(cl, "get_llm", lambda: stub)
    # rule_route sees "prepared"/"proposal" (document-evidence) → PDF; the 7B said GK@0.3.
    decision, _ = cl.classify("Who prepared this proposal document?", "documents + database")
    assert decision.route == "PDF", decision.reasoning
    assert stub.calls >= 2                              # retried once before reconciling


def test_high_confidence_general_knowledge_is_respected(monkeypatch):
    monkeypatch.setattr(cl, "get_settings", _live_settings)
    monkeypatch.setattr(cl, "_is_general_knowledge", lambda q: True)
    stub = _StubLLM({"route": "GENERAL_KNOWLEDGE", "confidence": 0.95, **_GK_FIELDS})
    monkeypatch.setattr(cl, "get_llm", lambda: stub)
    # genuine world-knowledge question (rule_route → NONE); a confident GK route stands.
    decision, _ = cl.classify("What is the capital of France?", "documents + database")
    assert decision.route == "GENERAL_KNOWLEDGE"


def test_malformed_routing_json_never_crashes(monkeypatch):
    monkeypatch.setattr(cl, "get_settings", _live_settings)
    monkeypatch.setattr(cl, "_is_general_knowledge", lambda q: False)
    monkeypatch.setattr(cl, "get_llm", lambda: _StubLLM({"totally": "broken"}))
    decision, _ = cl.classify("Who prepared this proposal document?", "documents + database")
    assert decision.route in cl._VALID_ROUTES
    assert decision.route == "PDF"                      # coerced to the rule-layer decision
