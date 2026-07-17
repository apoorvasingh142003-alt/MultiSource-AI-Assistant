"""Generative components (Phase 3) — deterministic, grounded, cited.

Turns an already-computed answer + its Trace into a small list of structured UI
components (a cited table, a bar chart, a timeline, a document/clause artifact) that
the chat renders inline with copy/export controls. This is the "generative UI" of the
roadmap, done the honest way:

- **Grounded only.** Data components (table/chart/timeline) are built ONLY when the
  answer_state is ``grounded`` and the evidence is real (non-parametric). A reasoned or
  insufficient answer gets no data component — the tri-state wall is never dressed up as
  a confident chart. This is enforced here, once, at the single finalize chokepoint.
- **From the evidence, not the prose.** Tables/charts/timelines are built from the SQL
  rows in the Trace (the exact rows already cited as evidence), never re-parsed from the
  model's free text — so every component traces to the same ``[eN]`` evidence the wall
  verified. The document artifact quotes the top cited passage verbatim.
- **Deterministic & offline.** No LLM call — pure inspection of the Trace. Component
  *selection* is cued by ``detect_component_intent`` but a component is only emitted when
  the data to back it actually exists, so a false cue never invents one.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.models import AnswerComponent, AnswerState, Evidence, SqlExecutionTrace, Trace
from app.retrieval.intent import detect_component_intent

# Column-name hints (case-insensitive substring match).
_NUMERIC_HINT = re.compile(
    r"amount|total|sum|count|revenue|balance|qty|quantity|number|value|price|cost|"
    r"outstanding|overdue|paid|due|score|rate|percent",
    re.I,
)
_DATE_HINT = re.compile(
    r"date|expir|period|start|end|due|created|signed|renew|deadline|when|year|month",
    re.I,
)
_LABEL_HINT = re.compile(r"name|customer|project|title|label|category|industry|status|type|event", re.I)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# How many rows a chart/timeline will visualise (tables keep them all).
_MAX_VIZ_ROWS = 24


def _is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v.replace(",", "").replace("$", "").strip())
            return True
        except (ValueError, AttributeError):
            return False
    return False


def _to_number(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").replace("$", "").strip())
        except ValueError:
            return None
    return None


def _looks_dateish(col: str, values: list[Any]) -> bool:
    if _DATE_HINT.search(col):
        return True
    for v in values:
        if isinstance(v, str) and _ISO_DATE.search(v):
            return True
    return False


def _primary_sql_trace(trace: Trace) -> Optional[SqlExecutionTrace]:
    """The main result set to visualise: the first valid, non-empty SQL execution that
    is not an internal entity-link step. Matches how the orchestrator cites rows."""
    candidates = [
        s for s in trace.sql_executions
        if s.valid and s.rows and s.purpose != "entity_link"
    ]
    if not candidates:
        return None
    # Prefer the explicit main/step query; else the first eligible one.
    for pref in ("sql_main", "sql_step", "sql"):
        for s in candidates:
            if s.purpose == pref:
                return s
    return candidates[0]


def _sql_evidence_ids(evidence: list[Evidence], table: Optional[str]) -> list[str]:
    """Evidence ids for the relational rows this component is built from — so the
    component's citation chips jump to the same [eN] passages in the inspector."""
    ids = [e.id for e in evidence if e.source_kind == "relational" and (not table or e.table == table)]
    return ids or [e.id for e in evidence if e.source_kind == "relational"]


def _pick_numeric_column(columns: list[str], rows: list[dict]) -> Optional[str]:
    """A column whose values are numeric — preferring an amount/total-like name."""
    numeric = [c for c in columns if all(_is_number(r.get(c)) for r in rows if r.get(c) is not None)
               and any(r.get(c) is not None for r in rows)]
    if not numeric:
        return None
    for c in numeric:
        if _NUMERIC_HINT.search(c):
            return c
    return numeric[0]


def _pick_label_column(columns: list[str], rows: list[dict], exclude: set[str]) -> Optional[str]:
    """A short text column to label bars/rows — preferring a name/customer-like name."""
    cands = [c for c in columns if c not in exclude]
    named = [c for c in cands if _LABEL_HINT.search(c)]
    for c in named:
        if any(not _is_number(r.get(c)) for r in rows if r.get(c) is not None):
            return c
    for c in cands:
        if any(not _is_number(r.get(c)) for r in rows if r.get(c) is not None):
            return c
    return cands[0] if cands else None


# Within a row that has several dates, the one a timeline is usually about is the
# forward-looking one (expiry / due / renewal / deadline) rather than a start date.
_DATE_PRIORITY = re.compile(r"expir|due|renew|deadline|end|maturit", re.I)


def _pick_date_column(columns: list[str], rows: list[dict]) -> Optional[str]:
    dateish = [c for c in columns
               if _looks_dateish(c, [r.get(c) for r in rows if r.get(c) is not None])
               and any(r.get(c) is not None for r in rows)]
    if not dateish:
        return None
    for c in dateish:                       # prefer a forward-looking date if present
        if _DATE_PRIORITY.search(c):
            return c
    return dateish[0]


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _build_table(s: SqlExecutionTrace, evidence: list[Evidence]) -> AnswerComponent:
    cols = s.columns or (list(s.rows[0].keys()) if s.rows else [])
    rows = [[_fmt(r.get(c)) for c in cols] for r in s.rows]
    return AnswerComponent(
        kind="table",
        title=f"{s.row_count} row(s) from the database",
        columns=cols,
        rows=rows,
        evidence_ids=_sql_evidence_ids(evidence, s.tables[0] if s.tables else None),
        caption="Live rows from the query the answer is grounded in — copy or export as CSV.",
    )


def _build_chart(s: SqlExecutionTrace, evidence: list[Evidence]) -> Optional[AnswerComponent]:
    cols = s.columns or (list(s.rows[0].keys()) if s.rows else [])
    if not cols:
        return None
    value_col = _pick_numeric_column(cols, s.rows)
    if not value_col:
        return None
    label_col = _pick_label_column(cols, s.rows, exclude={value_col})
    if not label_col:
        return None
    points = []
    for r in s.rows[:_MAX_VIZ_ROWS]:
        val = _to_number(r.get(value_col))
        if val is None:
            continue
        points.append({"label": _fmt(r.get(label_col)), "value": val})
    if len(points) < 2:
        return None
    return AnswerComponent(
        kind="chart",
        title=f"{value_col.replace('_', ' ').title()} by {label_col.replace('_', ' ').title()}",
        chart_kind="bar",
        x_label=label_col.replace("_", " ").title(),
        y_label=value_col.replace("_", " ").title(),
        points=points,
        evidence_ids=_sql_evidence_ids(evidence, s.tables[0] if s.tables else None),
        caption="Charted from the same database rows the answer cites.",
    )


def _build_timeline(s: SqlExecutionTrace, evidence: list[Evidence]) -> Optional[AnswerComponent]:
    cols = s.columns or (list(s.rows[0].keys()) if s.rows else [])
    date_col = _pick_date_column(cols, s.rows)
    if not date_col:
        return None
    title_col = _pick_label_column(cols, s.rows, exclude={date_col})
    detail_cols = [c for c in cols if c not in {date_col, title_col}]
    events = []
    for r in s.rows[:_MAX_VIZ_ROWS]:
        when = _fmt(r.get(date_col))
        if not when:
            continue
        title = _fmt(r.get(title_col)) if title_col else when
        details = " · ".join(f"{c.replace('_', ' ')}: {_fmt(r.get(c))}"
                             for c in detail_cols if r.get(c) is not None)
        events.append({"date": when, "title": title, "details": details})
    if len(events) < 1:
        return None
    # Chronological order (ISO dates sort lexically; leave others as-is).
    events.sort(key=lambda e: e["date"])
    return AnswerComponent(
        kind="timeline",
        title=f"Timeline by {date_col.replace('_', ' ').title()}",
        events=events,
        evidence_ids=_sql_evidence_ids(evidence, s.tables[0] if s.tables else None),
        caption="Ordered from the same database rows the answer cites.",
    )


def _build_artifact(question: str, evidence: list[Evidence]) -> Optional[AnswerComponent]:
    """A document/clause artifact: the single most relevant cited document passage,
    quoted verbatim, for questions that ask to see a clause/section. Grounded by
    construction (it IS a retrieved passage)."""
    doc_ev = [e for e in evidence if e.source_kind == "documents"
              and (e.extra or {}).get("type") != "parametric" and e.used]
    doc_ev = doc_ev or [e for e in evidence if e.source_kind == "documents"
                        and (e.extra or {}).get("type") != "parametric"]
    if not doc_ev:
        return None
    top = doc_ev[0]
    where = top.citation_label or (f"{top.document} p.{top.page}" if top.document else "document")
    return AnswerComponent(
        kind="artifact",
        title=top.document or "Document excerpt",
        subtitle=where,
        body=top.content,
        evidence_ids=[top.id],
        caption="Quoted verbatim from your document — open the inspector for full context.",
    )


_CLAUSE_CUE = re.compile(
    r"\b(clause|clauses|section|sections|quote|verbatim|exact\s+wording|excerpt|"
    r"what\s+do(?:es)?\s+.*\bsay\b|show\s+me\s+the)\b", re.I,
)


def build_components(
    question: str,
    answer_state: AnswerState,
    trace: Trace,
    evidence: list[Evidence],
) -> list[AnswerComponent]:
    """Assemble the inline generative components for an answer. Deterministic, offline,
    and gated on the grounding wall: data components require a grounded answer + real
    (non-parametric) evidence, so an ungrounded/insufficient answer never renders a
    confident-looking table or chart."""
    # The wall: no data component for a reasoned/insufficient answer.
    if answer_state != "grounded":
        return []
    if not evidence or all((e.extra or {}).get("type") == "parametric" for e in evidence):
        return []

    intent = detect_component_intent(question)
    components: list[AnswerComponent] = []
    s = _primary_sql_trace(trace)

    if s is not None:
        # Chart / timeline are the "headline" visual when the question asks for one; the
        # underlying cited table is always shown alongside so the numbers stay inspectable.
        if intent == "chart":
            chart = _build_chart(s, evidence)
            if chart:
                components.append(chart)
        elif intent == "timeline":
            tl = _build_timeline(s, evidence)
            if tl:
                components.append(tl)
        # A cited table for any SQL-backed answer (the default structured component).
        components.append(_build_table(s, evidence))

    # A document/clause artifact for "show me the clause / what does X say" questions.
    if _CLAUSE_CUE.search(question or ""):
        artifact = _build_artifact(question, evidence)
        if artifact:
            components.append(artifact)

    return components
