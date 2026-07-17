"""Phase 4 — deep research (agentic iterative retrieval).

Pins the retrieve → sufficiency-check → reformulate loop end to end, fully offline
(conftest forces hashing embeddings + basic parser), covering:

- the deterministic sufficiency heuristics (term coverage with inflection tolerance,
  generic-term filtering, multi-aspect splitting, corpus-spread detection),
- the bounded loop itself (rounds, stop reasons, research_trace shape, progress events),
- the tri-state wall: evidence spread across many documents stays grounded + cited,
  while an out-of-scope question still lands on the honest decline — the loop can
  never ground an answer in off-topic passages,
- API plumbing of the ``deep_research`` flag.

Run:  .venv/bin/python -m pytest tests/test_deep_research.py -q
"""
from __future__ import annotations

import pytest

from app.agent.sufficiency import (heuristic_verdict, split_aspects,
                                   wants_corpus_spread)
from app.agent.tools import AgentRunContext
from app.config import get_settings
from app.engine import Engine
from app.models import Evidence

# The evidence-spread flagship: answering well requires passages from several customer
# contracts, and offline round 1 does NOT satisfy the spread requirement — the loop
# must reformulate and search again (observed: 2 rounds, 5 documents).
SPREAD_Q = "Summarize the payment terms across every customer contract."
OUT_OF_SCOPE_Q = "What is our employee headcount in Berlin?"


@pytest.fixture(scope="module")
def eng():
    return Engine(user_id="deep-research-tests")


def _ev(i: int, content: str, document: str | None = "A.pdf") -> Evidence:
    return Evidence(id=f"e{i}", source_name="contracts_pdf", source_kind="documents",
                    content=content, citation_label=f"[{document} p.1]",
                    document=document, page=1)


# -- sufficiency heuristics --------------------------------------------------

def test_verdict_insufficient_with_no_evidence():
    v = heuristic_verdict("What are the penalty clauses?", [], None, get_settings())
    assert not v.sufficient and v.coverage == 0.0


def test_coverage_tolerates_inflection_and_ignores_generic_verbs():
    # "agreements" must match "Agreement", and meta-verbs like "say"/"across" must not
    # count against coverage (they never appear in a relevant passage).
    ev = [_ev(1, "This Agreement provides that Provider may suspend the service.")]
    v = heuristic_verdict("What do the agreements say about service suspension?",
                         ev, None, get_settings())
    assert v.coverage >= get_settings().research_min_coverage
    assert v.sufficient


def test_split_aspects_on_multipart_question():
    parts = split_aspects(
        "Which customers have overdue invoices, and what do their agreements say?")
    assert len(parts) == 2
    # noun-phrase "and" must NOT split
    assert split_aspects("What are the terms and conditions?") == []


def test_uncovered_aspect_becomes_next_query():
    ev = [_ev(1, "ACME and Globex have overdue invoices totalling $12,000.")]
    v = heuristic_verdict(
        "Which customers have overdue invoices, and what penalties do their contracts define?",
        ev, None, get_settings())
    assert not v.sufficient
    assert v.missing_aspects and any("penalt" in a for a in v.missing_aspects)
    assert any("penalt" in q.query for q in v.next_queries)


def test_corpus_spread_detection_and_per_document_queries():
    assert wants_corpus_spread("Compare the penalty clauses across all agreements")
    assert not wants_corpus_spread("What is the penalty clause?")

    target = ["A.pdf", "B.pdf", "C.pdf", "D.pdf", "E.pdf"]
    ev = [_ev(1, "Payment terms: net 30 for every invoice under the contract.", "A.pdf")]
    v = heuristic_verdict("Summarize the payment terms across all customer contracts.",
                         ev, target, get_settings())
    assert not v.sufficient                       # only 1 of ≥4 required docs covered
    assert set(v.missing_documents) == {"B.pdf", "C.pdf", "D.pdf", "E.pdf"}
    doc_targeted = [q for q in v.next_queries if q.documents]
    assert doc_targeted and all(len(q.documents) == 1 for q in doc_targeted)


def test_evidence_dedup_preserves_cross_document_provenance():
    # Contract boilerplate: the SAME clause text in two documents must stay two
    # evidence items (each citable), while a true re-retrieval still dedups.
    ctx = AgentRunContext(None, None, None)
    clause = "Provider may suspend the Services if invoices are unpaid."
    ctx.add_evidence([_ev(1, clause, "A.pdf")])
    ctx.add_evidence([_ev(1, clause, "B.pdf")])
    ctx.add_evidence([_ev(1, clause, "A.pdf")])   # duplicate — must not re-add
    assert len(ctx.evidence) == 2
    assert {e.document for e in ctx.evidence} == {"A.pdf", "B.pdf"}


# -- the loop, end to end (offline deterministic) ----------------------------

def test_spread_question_iterates_and_stays_grounded(eng):
    events: list[tuple[str, dict]] = []
    resp = eng.ask(SPREAD_Q, deep_research=True,
                   on_event=lambda e, d: events.append((e, d)))
    rt = resp.research_trace
    s = get_settings()

    # grounded + cited — the wall label and citation verification both hold
    assert resp.answer_state == "grounded" and not resp.insufficient
    assert resp.trace.citation_check and resp.trace.citation_check.verified
    assert resp.citations

    # evidence genuinely spread across many documents
    assert len(rt["documents_covered"]) >= s.research_spread_min_docs

    # the loop actually iterated (round 1 alone does not satisfy the spread) and
    # stopped within bounds for the right reason
    assert 2 <= rt["total_rounds"] <= s.research_max_rounds
    assert rt["stop_reason"] == "sufficient"

    # trace shape: every round records its actions; the assessed rounds carry verdicts
    assert rt["rounds"][0]["actions"]
    assert rt["rounds"][0]["verdict"] and rt["rounds"][0]["verdict"]["sufficient"] is False
    assert rt["rounds"][-1]["verdict"]["sufficient"] is True

    # mirrored on the trace for the inspector
    assert resp.trace.research_trace == rt

    # live progress: start → search(es) → assess(es) → done, all as research_step
    kinds = [d["kind"] for _e, d in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert kinds.count("search") >= 2 and kinds.count("assess") >= 2


def test_out_of_scope_question_still_declines(eng):
    # Deep research must never ground an answer in off-topic top-k passages: the
    # relevance gate hands the question to the classic pipeline's honest decline.
    resp = eng.ask(OUT_OF_SCOPE_Q, deep_research=True)
    assert resp.answer_state == "insufficient" and resp.insufficient
    assert resp.research_trace["stop_reason"] in ("off_topic", "no_progress", "exhausted")
    assert "insufficient evidence" in resp.answer.lower()


def test_rounds_and_latency_are_bounded(eng):
    resp = eng.ask("Compare risks and mitigation across every project brief and contract.",
                   deep_research=True)
    rt = resp.research_trace
    s = get_settings()
    assert rt["total_rounds"] <= s.research_max_rounds
    assert len(resp.trace.evidence) <= s.research_max_evidence + 5  # per-round searches may overshoot one batch
    assert rt["stop_reason"] in ("sufficient", "max_rounds", "time_budget",
                                 "no_progress", "evidence_cap", "exhausted", "off_topic")


def test_deep_research_flag_via_api():
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    r = c.post("/ask", json={"question": SPREAD_Q, "scope": "all", "deep_research": True})
    assert r.status_code == 200
    body = r.json()
    assert body["research_trace"] and body["research_trace"]["total_rounds"] >= 1
    assert body["trace"]["research_trace"] == body["research_trace"]
    assert body["answer_state"] == "grounded"


def test_classic_path_unaffected(eng):
    resp = eng.ask("What do our contracts say about service suspension?")
    assert resp.research_trace is None
    assert resp.trace.research_trace is None
