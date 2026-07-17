"""The tri-state grounding wall (the product moat) — answer_state.

Every answer is labelled exactly one of three states — grounded / reasoned / insufficient —
and the three are never blended into one confident stream. These tests pin the pure
classifier (``compute_answer_state``) and its end-to-end wiring through the engine, offline
and deterministic (conftest forces auth off + hashing embeddings).

Run:  .venv/bin/python -m pytest tests/test_answer_state.py -q
"""
from __future__ import annotations

from app.models import Evidence, RouteDecision, compute_answer_state


def _ev(**kw) -> Evidence:
    base = dict(id="e1", source_name="s", source_kind="documents", content="x",
                citation_label="[x]")
    base.update(kw)
    return Evidence(**base)


# -- the pure classifier -----------------------------------------------------

def test_insufficient_wins_over_everything():
    r = RouteDecision(route="PDF", reasoning="", confidence=0.9)
    assert compute_answer_state("anything", r, [_ev()], insufficient=True) == "insufficient"


def test_grounded_when_evidence_and_not_insufficient():
    r = RouteDecision(route="PDF", reasoning="", confidence=0.9)
    assert compute_answer_state("Clause 4 says [e1].", r, [_ev()], insufficient=False) == "grounded"


def test_reasoned_on_general_knowledge_route():
    r = RouteDecision(route="GENERAL_KNOWLEDGE", reasoning="", confidence=0.5)
    assert compute_answer_state("The capital of France is Paris.", r, [], insufficient=False) == "reasoned"


def test_reasoned_on_parametric_synthetic_evidence():
    r = RouteDecision(route="PDF", reasoning="", confidence=0.5)
    ev = _ev(source_name="LLM general knowledge (ungrounded)", extra={"type": "parametric"})
    assert compute_answer_state("ungrounded body", r, [ev], insufficient=False) == "reasoned"


def test_reasoned_on_advice_disclaimer_marker():
    # A grounded-advice answer mixes cited facts + labelled general guidance → reasoned.
    r = RouteDecision(route="PDF", reasoning="", confidence=0.5)
    answer = ("PART 1 — the record says [e1].\n\n"
              "⚠️ The following is general guidance from model knowledge, not from your "
              "uploaded sources, and may be inaccurate.")
    assert compute_answer_state(answer, r, [_ev()], insufficient=False) == "reasoned"


# -- end to end through the engine -------------------------------------------

def test_engine_grounded_answer_is_labelled_grounded():
    from app.engine import get_engine
    resp = get_engine().ask("What do our contracts say about service suspension?")
    assert resp.answer_state == "grounded"
    assert not resp.insufficient


def test_engine_out_of_scope_is_labelled_insufficient():
    from app.engine import get_engine
    resp = get_engine().ask("What is our employee headcount in Berlin?")
    assert resp.answer_state == "insufficient"
    assert resp.insufficient
