"""Agent-mode grounding-first — unit coverage for the trace/verification rebuild.

The live LangGraph agent needs langgraph + a live LLM, so it can't run hermetically. These
tests pin the two behaviours that fixed the agent-mode incident (fabricated staff / "citations
unverified"):

1. `_build_response` verifies an answer using the generator's DECLARED citations, not only
   inline `[eN]` markers — a weak model routinely supplies one or the other.
2. `_infer_route` maps "no tool was used" to GENERAL_KNOWLEDGE (the signal that triggers the
   classic grounding-first fallback in `run_agent`).

Run:  .venv/bin/python -m pytest tests/test_agent_grounding.py -q
"""
from __future__ import annotations

import os
import types

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

from app.agent.runner import _build_response, _infer_route  # noqa: E402
from app.models import Evidence  # noqa: E402


def _ctx(evidence, steps):
    return types.SimpleNamespace(
        evidence=evidence, sql_executions=[], document_retrieval=None, calls=[], steps=steps,
    )


def _ev(eid, content):
    return Evidence(id=eid, source_name="nursing_home_.pdf", source_kind="documents",
                    content=content, citation_label="[nursing_home_.pdf p.1]",
                    document="nursing_home_.pdf")


_DOC_STEP = [{"tool": "search_documents", "iteration": 1, "args": {}, "observation": "..."}]


def test_declared_citations_verify_without_inline_markers():
    """A grounded answer that carries declared (not inline) citations verifies — this is the
    fix for the agent's 'citations unverified' on a correct, grounded answer."""
    ctx = _ctx([_ev("e1", "Primary Nurse: Emily Roberts")], _DOC_STEP)
    resp = _build_response("Who is the nurse?", "The primary nurse is Emily Roberts.",
                           ctx, [], 1, None, "Standard Response", 0.0, declared_cited=["e1"])
    assert resp.trace.citation_check.verified is True
    assert not resp.insufficient


def test_uncited_grounded_answer_is_flagged_unverified():
    ctx = _ctx([_ev("e1", "Primary Nurse: Emily Roberts")], _DOC_STEP)
    resp = _build_response("Who is the nurse?", "The primary nurse is Emily Roberts.",
                           ctx, [], 1, None, "Standard Response", 0.0, declared_cited=None)
    assert resp.trace.citation_check.verified is False


def test_infer_route_no_tool_is_general_knowledge():
    # no tool used → GENERAL_KNOWLEDGE → triggers the classic grounding-first fallback
    assert _infer_route(types.SimpleNamespace(steps=[])) == "GENERAL_KNOWLEDGE"
    assert _infer_route(types.SimpleNamespace(steps=[{"tool": "search_documents"}])) == "PDF"
    assert _infer_route(types.SimpleNamespace(steps=[{"tool": "sql_query"}])) == "SQL"
    assert _infer_route(types.SimpleNamespace(
        steps=[{"tool": "sql_query"}, {"tool": "search_documents"}])) == "HYBRID"
