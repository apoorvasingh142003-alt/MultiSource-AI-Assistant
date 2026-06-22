"""Tests for the upgrade features (spec §13): the GENERAL_KNOWLEDGE routing path, SQL
validation, and cross-source contradiction detection.

Hermetic and offline — settings are forced to the offline floor before importing app, so
these need no engine warm-up, network, or API key.

Run:  .venv/bin/python -m pytest tests/test_upgrade_features.py -q
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

import pytest  # noqa: E402

from app.generation.analysis import (compute_contributions, compute_hallucination_risk,  # noqa: E402
                                     detect_contradictions)
from app.models import CitationCheck, Evidence, LLMCall  # noqa: E402
from app.sql.validate import SQLValidationError, validate_select  # noqa: E402


# ----------------------------------------------------------------------------- #
# Section 0 — GENERAL_KNOWLEDGE routing path                                     #
# ----------------------------------------------------------------------------- #
def _doc_ev(eid: str, content: str) -> Evidence:
    return Evidence(id=eid, source_name="contracts_pdf", source_kind="documents",
                    content=content, citation_label=f"[doc {eid}]", document="d.pdf")


def _row_ev(eid: str, content: str) -> Evidence:
    return Evidence(id=eid, source_name="business_db", source_kind="relational",
                    content=content, citation_label=f"[db {eid}]", table="invoices")


def test_route_enum_includes_general_knowledge():
    from app.models import Route  # Literal type
    assert "GENERAL_KNOWLEDGE" in getattr(Route, "__args__", ())


def test_secondary_classifier_upgrades_none_to_general_knowledge(monkeypatch):
    """When the router returns NONE but the secondary classifier says the question is
    answerable from world knowledge, the route is upgraded to GENERAL_KNOWLEDGE (0.75)."""
    import app.routing.classify as cl
    monkeypatch.setattr(cl, "_is_general_knowledge", lambda q: True)
    # A question the rule layer routes to NONE (no indexed source could hold it); the
    # secondary classifier then upgrades it.
    decision, _call = cl.classify("What is the weather forecast for tomorrow?", "No sources.")
    assert decision.route == "GENERAL_KNOWLEDGE"
    assert decision.confidence == 0.75


def test_general_knowledge_not_triggered_when_unanswerable(monkeypatch):
    import app.routing.classify as cl
    monkeypatch.setattr(cl, "_is_general_knowledge", lambda q: False)
    decision, _call = cl.classify("What is the weather forecast for tomorrow?", "No sources.")
    assert decision.route == "NONE"


# ----------------------------------------------------------------------------- #
# Section 0 — SQL validation                                                     #
# ----------------------------------------------------------------------------- #
TABLES = {"invoices", "customers", "projects"}


def test_select_is_allowed_and_limit_injected():
    out = validate_select("SELECT customer, amount FROM invoices", TABLES, row_limit=50)
    assert out.upper().startswith("SELECT")
    assert "LIMIT 50" in out.upper()


def test_existing_limit_is_preserved():
    out = validate_select("SELECT * FROM customers LIMIT 5", TABLES)
    assert "LIMIT 5" in out.upper()


@pytest.mark.parametrize("bad", [
    "DROP TABLE invoices",
    "DELETE FROM invoices",
    "UPDATE invoices SET amount = 0",
    "INSERT INTO invoices (id) VALUES (1)",
])
def test_ddl_dml_rejected(bad):
    with pytest.raises(SQLValidationError):
        validate_select(bad, TABLES)


def test_unknown_table_rejected():
    with pytest.raises(SQLValidationError):
        validate_select("SELECT * FROM salaries", TABLES)


def test_multiple_statements_rejected():
    with pytest.raises(SQLValidationError):
        validate_select("SELECT 1; SELECT 2", TABLES)


# ----------------------------------------------------------------------------- #
# Section 6.1 — contribution scoring & Section 8.1 — hallucination risk          #
# ----------------------------------------------------------------------------- #
def test_contribution_percentage_from_markers():
    ev = [_row_ev("e1", "a"), _doc_ev("e2", "b")]
    compute_contributions("Claim one [e1]. Claim two [e2]. More [e1].", ev)
    # e1 cited twice of 3 markers ≈ 66.7%, e2 once ≈ 33.3%
    assert ev[0].contribution_percentage == pytest.approx(66.7, abs=0.2)
    assert ev[1].contribution_percentage == pytest.approx(33.3, abs=0.2)


def test_hallucination_risk_formula():
    check = CitationCheck(verified=False, cited_ids=["e1", "e2"], unknown_ids=["e2"])
    # 1 unverified of 2 → 0.5 * (1/2) = 0.25 ; no contradictions → +0
    assert compute_hallucination_risk(check, [], 0) == 0.25
    # + 1 major contradiction over 1 pair → 0.5*(1/2) + 0.5*(1/1) = 0.25 + 0.5 = 0.75
    contradictions = [{"severity": "major"}]
    assert compute_hallucination_risk(check, contradictions, 1) == 0.75


# ----------------------------------------------------------------------------- #
# Section 8.1 — cross-source contradiction detection                            #
# ----------------------------------------------------------------------------- #
def test_no_contradiction_check_for_single_source():
    ev = [_doc_ev("e1", "x"), _doc_ev("e2", "y")]  # both documents → one source kind
    for e in ev:
        e.used = True
    contradictions, warning, pairs = detect_contradictions("Both [e1] and [e2].", ev, [])
    assert contradictions == [] and warning is None and pairs == 0


def test_cross_source_contradiction_detected(monkeypatch):
    """Two evidence items from different sources cited in one sentence are checked, and a
    major contradiction surfaces a verification warning."""
    import app.generation.analysis as an

    class _StubLLM:
        def structured(self, **kw):
            return ({"contradiction": True, "severity": "major",
                     "explanation": "Amounts disagree."},
                    LLMCall(purpose="contradiction_check", model="stub", mode="stub"))

    monkeypatch.setattr(an, "get_llm", lambda: _StubLLM())
    ev = [_row_ev("e1", "Acme owes $60,000"), _doc_ev("e2", "Acme owes $10,000")]
    for e in ev:
        e.used = True
    calls: list[LLMCall] = []
    contradictions, warning, pairs = detect_contradictions(
        "Acme's balance is disputed [e1][e2].", ev, calls)
    assert pairs == 1
    assert len(contradictions) == 1 and contradictions[0]["severity"] == "major"
    assert warning is not None
    assert len(calls) == 1  # the contradiction-check LLM call was counted
