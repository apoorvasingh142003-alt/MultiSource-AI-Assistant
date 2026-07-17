"""Generative components (Phase 3) — deterministic, grounded, cited.

Every answer can carry a small list of inline UI components (a cited table, a bar chart,
a timeline, or a document/clause artifact). They are built *from the trace* (SQL rows /
retrieved passages), never invented, and — critically — only ever for a GROUNDED answer,
so the tri-state wall is never dressed up as a confident chart. These tests pin the pure
builder + its intent selection and the end-to-end wiring through the engine, offline and
deterministic (conftest forces auth off + hashing embeddings).

Run:  .venv/bin/python -m pytest tests/test_components.py -q
"""
from __future__ import annotations

from app.generation.components import build_components
from app.models import Evidence, RouteDecision, SqlExecutionTrace, Trace
from app.retrieval.intent import detect_component_intent


def _sql_trace(purpose="sql_main", **kw) -> SqlExecutionTrace:
    rows = kw.pop("rows", [
        {"name": "Acme", "outstanding": 1200.0},
        {"name": "Globex", "outstanding": 800.0},
        {"name": "Initech", "outstanding": 300.0},
    ])
    cols = kw.pop("columns", list(rows[0].keys()) if rows else [])
    base = dict(purpose=purpose, natural_language="q", generated_sql="SELECT …",
                validated_sql="SELECT …", valid=True, columns=cols, rows=rows,
                row_count=len(rows), tables=["invoices"])
    base.update(kw)
    return SqlExecutionTrace(**base)


def _sql_evidence(n=3) -> list[Evidence]:
    return [Evidence(id=f"e{i+1}", source_name="business_db", source_kind="relational",
                     content="row", citation_label=f"[db {i}]", table="invoices",
                     row_ids=[i]) for i in range(n)]


def _doc_evidence() -> list[Evidence]:
    return [Evidence(id="e1", source_name="contracts", source_kind="documents",
                     content="Provider may suspend the Service upon 30 days notice.",
                     citation_label="[ACME_MSA_2025.pdf p.4]", document="ACME_MSA_2025.pdf",
                     page=4, used=True)]


# -- intent detection --------------------------------------------------------

def test_intent_chart():
    assert detect_component_intent("Chart the outstanding amount by customer") == "chart"
    assert detect_component_intent("Compare revenue across industries") == "chart"


def test_intent_timeline():
    assert detect_component_intent("Show a timeline of contract expirations") == "timeline"
    assert detect_component_intent("What contracts expire in the next 90 days?") == "timeline"


def test_intent_table():
    assert detect_component_intent("total outstanding invoice amount per customer") == "table"
    assert detect_component_intent("list all overdue invoices") == "table"


def test_intent_none():
    assert detect_component_intent("What does the contract say about suspension?") == ""


# -- the wall: no data component for a non-grounded answer -------------------

def test_no_components_for_reasoned():
    trace = Trace(question="q", sql_executions=[_sql_trace()])
    assert build_components("chart it by customer", "reasoned", trace, _sql_evidence()) == []


def test_no_components_for_insufficient():
    trace = Trace(question="q", sql_executions=[_sql_trace()])
    assert build_components("chart it", "insufficient", trace, _sql_evidence()) == []


def test_no_components_for_parametric_only_evidence():
    trace = Trace(question="q")
    para = [Evidence(id="e1", source_name="LLM", source_kind="documents", content="x",
                     citation_label="[ungrounded]", extra={"type": "parametric"})]
    assert build_components("chart it", "grounded", trace, para) == []


# -- table (the default structured component for any SQL answer) -------------

def test_table_built_for_sql_answer():
    trace = Trace(question="q", sql_executions=[_sql_trace()])
    comps = build_components("total outstanding per customer", "grounded", trace, _sql_evidence())
    tables = [c for c in comps if c.kind == "table"]
    assert len(tables) == 1
    t = tables[0]
    assert t.columns == ["name", "outstanding"]
    assert len(t.rows) == 3
    assert t.rows[0] == ["Acme", "1200"]           # float→int formatting
    assert t.evidence_ids == ["e1", "e2", "e3"]    # links back to the cited rows


def test_entity_link_step_is_ignored():
    # An internal SQL→document linking query must never become the visible table.
    trace = Trace(question="q", sql_executions=[
        _sql_trace(purpose="entity_link", rows=[{"customer": "Acme", "pdf_file": "a.pdf"}]),
        _sql_trace(purpose="sql_step"),
    ])
    comps = build_components("list per customer", "grounded", trace, _sql_evidence())
    table = next(c for c in comps if c.kind == "table")
    assert table.columns == ["name", "outstanding"]


# -- chart -------------------------------------------------------------------

def test_chart_built_on_chart_intent():
    trace = Trace(question="q", sql_executions=[_sql_trace()])
    comps = build_components("chart outstanding by customer", "grounded", trace, _sql_evidence())
    charts = [c for c in comps if c.kind == "chart"]
    assert len(charts) == 1
    ch = charts[0]
    assert ch.chart_kind == "bar"
    assert [p["label"] for p in ch.points] == ["Acme", "Globex", "Initech"]
    assert [p["value"] for p in ch.points] == [1200.0, 800.0, 300.0]
    # the underlying cited table is always shown alongside the chart
    assert any(c.kind == "table" for c in comps)


def test_no_chart_without_numeric_column():
    rows = [{"name": "Acme", "status": "active"}, {"name": "Globex", "status": "overdue"}]
    trace = Trace(question="q", sql_executions=[_sql_trace(rows=rows)])
    comps = build_components("chart by customer", "grounded", trace, _sql_evidence(2))
    assert not any(c.kind == "chart" for c in comps)   # no numbers → table only
    assert any(c.kind == "table" for c in comps)


# -- timeline ----------------------------------------------------------------

def test_timeline_built_on_timeline_intent():
    rows = [
        {"customer": "Acme", "expires": "2026-09-01", "penalty": "2%"},
        {"customer": "Globex", "expires": "2026-08-15", "penalty": "5%"},
    ]
    trace = Trace(question="q", sql_executions=[_sql_trace(rows=rows)])
    comps = build_components("timeline of contract expirations", "grounded", trace, _sql_evidence(2))
    tls = [c for c in comps if c.kind == "timeline"]
    assert len(tls) == 1
    tl = tls[0]
    # chronological order (earliest first)
    assert [e["date"] for e in tl.events] == ["2026-08-15", "2026-09-01"]
    assert tl.events[0]["title"] == "Globex"


# -- artifact ----------------------------------------------------------------

def test_artifact_built_for_clause_question():
    trace = Trace(question="q")
    comps = build_components("What do our contracts say about suspension?", "grounded",
                             trace, _doc_evidence())
    arts = [c for c in comps if c.kind == "artifact"]
    assert len(arts) == 1
    a = arts[0]
    assert a.body.startswith("Provider may suspend")
    assert a.evidence_ids == ["e1"]
    assert "ACME_MSA_2025.pdf" in a.subtitle


def test_no_artifact_without_document_evidence():
    trace = Trace(question="q", sql_executions=[_sql_trace()])
    comps = build_components("show me the clause", "grounded", trace, _sql_evidence())
    assert not any(c.kind == "artifact" for c in comps)


# -- end to end through the engine -------------------------------------------

def test_engine_sql_answer_carries_cited_table():
    from app.engine import get_engine
    resp = get_engine().ask("What is the total outstanding invoice amount per customer?")
    assert resp.answer_state == "grounded"
    tables = [c for c in resp.components if c.kind == "table"]
    assert tables, "a grounded SQL answer should carry a cited table component"
    assert tables[0].evidence_ids, "table links back to the cited evidence"


def test_engine_insufficient_answer_has_no_components():
    from app.engine import get_engine
    resp = get_engine().ask("What is our employee headcount in Berlin?")
    assert resp.answer_state == "insufficient"
    assert resp.components == []
