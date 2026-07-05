"""Grounding-first guarantee — the core fix for the nursing-home fabrication incident.

The incident: running on a weak local model, the router returned GENERAL_KNOWLEDGE for
"what medication does he take?" and the engine answered from model training data,
fabricating medications and staff that contradict the uploaded PDF.

These tests force the router to return GENERAL_KNOWLEDGE (simulating the weak local model)
and assert the engine STILL grounds in the document — and that any genuinely ungrounded
answer is loudly disclaimed, never silently presented as fact.

Run:  .venv/bin/python -m pytest tests/test_grounding_first.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

import app.routing.orchestrator as orch  # noqa: E402
from app.config import ROOT, get_settings  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.models import LLMCall, RouteDecision  # noqa: E402

NURSING = ROOT / "data" / "preserved" / "nursing_home_.pdf"

# Values the model fabricated across incidents — they must never come from grounding.
FABRICATED = ["omeprazole", "aspirin", "sarah thompson", "maria rodriguez", "john lee",
              "aisha", "al-sheikh", "fatima hassan", "ali ahmed", "nystatin"]


@pytest.fixture(scope="module")
def engine():
    if not NURSING.exists():
        pytest.skip("nursing_home_.pdf not present in data/preserved")
    get_settings.cache_clear()
    eng = Engine()
    info = eng.add_pdf("nursing_home_.pdf", NURSING)
    assert info.status == "indexed", f"upload failed: {info.error}"
    return eng


def _force_general_knowledge(*_a, **_k):
    """Stand in for a weak local router that wrongly returns GENERAL_KNOWLEDGE @ low conf."""
    return (
        RouteDecision(route="GENERAL_KNOWLEDGE", reasoning="weak router said GK",
                      confidence=0.4, languages=["en"], document_subquery="",
                      sql_subquery="", entity_hint="", agentic=False, strategy_note=""),
        LLMCall(purpose="routing", model="stub", mode="stub"),
    )


@pytest.mark.parametrize("question,must_contain", [
    ("What is the dose of Donepezil?", "donepezil"),
    ("Who is the primary care physician?", "feldman"),
    ("Who is the attending surgeon?", "hall"),
])
def test_general_knowledge_never_overrides_document_evidence(engine, monkeypatch, question, must_contain):
    """Even when the router says GENERAL_KNOWLEDGE, an in-scope document answer is grounded."""
    monkeypatch.setattr(orch, "classify", _force_general_knowledge)
    resp = engine.ask(question)

    assert resp.trace.evidence, "grounding-first must recover document evidence"
    assert not resp.insufficient
    # the answer is grounded — not the ungrounded parametric path
    assert "not grounded" not in resp.answer.lower()
    txt = " ".join(e.content for e in resp.trace.evidence).lower()
    assert must_contain in txt, f"expected {must_contain!r} in grounded evidence"
    # fabricated incident values must never surface from grounded evidence
    for bogus in FABRICATED:
        assert bogus not in txt, f"fabricated value {bogus!r} leaked into grounded evidence"


def test_correct_medication_doses_are_grounded(engine, monkeypatch):
    """The real Donepezil dose (10mg) is grounded — not the fabricated 5mg from the incident.
    The page-7 medication-list chunk also carries the other real drugs."""
    monkeypatch.setattr(orch, "classify", _force_general_knowledge)
    resp = engine.ask("What is the dose of Donepezil?")
    txt = " ".join(e.content for e in resp.trace.evidence).lower()
    assert "donepezil" in txt and "10" in txt
    assert "metformin" in txt and "lisinopril" in txt        # same medication-list passage


def test_out_of_scope_question_is_declined_or_loudly_disclaimed(engine, monkeypatch):
    """A forced-GK question with no on-topic evidence is EITHER honestly declined OR carries
    the loud 'not grounded' disclaimer — it is never silently presented as a cited fact."""
    monkeypatch.setattr(orch, "classify", _force_general_knowledge)
    resp = engine.ask("Who won the 2018 FIFA World Cup final?")
    grounded_lie = (not resp.insufficient
                    and "not grounded" not in resp.answer.lower()
                    and resp.hallucination_risk_score and resp.hallucination_risk_score < 0.5)
    assert not grounded_lie, f"ungrounded answer presented as grounded: {resp.answer[:200]}"
