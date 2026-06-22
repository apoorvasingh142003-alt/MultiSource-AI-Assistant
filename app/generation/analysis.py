"""Post-generation analysis — the data behind the Explainability & Verification panels.

This module turns a finished answer + its evidence into the explainability signals the
spec asks for (Sections 6.1 & 8.1):

* ``compute_contributions``  — what fraction of the answer each evidence item supports,
  by counting its ``[eN]`` citation markers.
* ``attach_trust_factors``   — per-evidence trust scores (retrieval / rerank ranks for
  documents, authoritative-row status for SQL, parametric for general knowledge).
* ``detect_contradictions``  — pairwise, cross-source contradiction detection via the LLM
  for evidence cited together in the same sentence.
* ``compute_hallucination_risk`` — a single 0..1 risk score combining unverified
  citations and major contradictions (per the spec formula).

Everything here is additive and degrades gracefully offline (no LLM → no contradictions,
deterministic trust summaries), so the pipeline still works with no API key.
"""
from __future__ import annotations

import re
from typing import Optional

from app.config import get_settings
from app.llm.client import get_llm
from app.models import (CitationCheck, DocumentRetrievalTrace, Evidence, LLMCall,
                        SqlExecutionTrace)

_MARKER = re.compile(r"\[(e\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")

# Cap on pairwise contradiction LLM calls per answer — bounds cost on answers that
# cite many sources together. Pairs beyond this are reported as "not evaluated".
_MAX_CONTRADICTION_PAIRS = 8


# --------------------------------------------------------------------------- #
# 6.1 — source contribution scoring                                            #
# --------------------------------------------------------------------------- #
def compute_contributions(answer: str, evidence: list[Evidence]) -> None:
    """Set ``contribution_percentage`` on each evidence item in place.

    Approximation per spec: for each evidence item, count how many ``[eN]`` markers in
    the answer reference it, divided by the total number of markers in the answer.
    (``used`` is set upstream from the citation check, which also unions declared ids.)
    """
    markers = _MARKER.findall(answer or "")
    total = len(markers)
    counts: dict[str, int] = {}
    for m in markers:
        counts[m] = counts.get(m, 0) + 1
    for e in evidence:
        n = counts.get(e.id, 0)
        e.contribution_percentage = round(100.0 * n / total, 1) if total else 0.0


# --------------------------------------------------------------------------- #
# 6.1 — per-source trust reasoning                                             #
# --------------------------------------------------------------------------- #
def attach_trust_factors(
    evidence: list[Evidence],
    doc_trace: Optional[DocumentRetrievalTrace],
    sql_executions: list[SqlExecutionTrace],
) -> None:
    """Populate ``trust_factors`` on each evidence item in place."""
    cand_by_chunk = {}
    if doc_trace:
        cand_by_chunk = {c.chunk_id: c for c in doc_trace.candidates}

    for e in evidence:
        if e.extra.get("type") == "parametric":
            e.trust_factors = {
                "recency_score": None,
                "retrieval_score": None,
                "rerank_score": None,
                "is_primary_source": False,
                "trust_summary": "Model parametric knowledge — not retrieved from any "
                                 "indexed document or database.",
            }
            continue

        if e.source_kind == "relational":
            e.trust_factors = {
                "recency_score": 1.0,
                "retrieval_score": 1.0,   # deterministic DB row matching the constraints
                "rerank_score": None,
                "is_primary_source": True,
                "trust_summary": (
                    f"Authoritative database row from table "
                    f"{e.table or e.source_name} — matches the query constraints exactly."
                ),
            }
            continue

        # documents — pull the full rank breakdown from the matching candidate
        cand = cand_by_chunk.get(e.chunk_id)
        if cand is not None:
            retrieval_score = cand.rrf_score if cand.rrf_score is not None else e.score
            rerank = cand.rerank_score
            bits = []
            if cand.bm25_rank is not None:
                bits.append(f"BM25 #{cand.bm25_rank}")
            if cand.dense_rank is not None:
                bits.append(f"dense #{cand.dense_rank}")
            if rerank is not None:
                bits.append(f"reranker {rerank:.2f}")
            summary = "High-confidence match: " + ", ".join(bits) if bits else \
                "Retrieved passage selected by hybrid search."
            e.trust_factors = {
                "recency_score": 1.0 if e.origin == "uploaded" else 0.8,
                "retrieval_score": retrieval_score,
                "rerank_score": rerank,
                "is_primary_source": True,
                "trust_summary": summary,
            }
        else:
            e.trust_factors = {
                "recency_score": 0.8,
                "retrieval_score": e.score,
                "rerank_score": None,
                "is_primary_source": True,
                "trust_summary": "Retrieved document passage.",
            }


# --------------------------------------------------------------------------- #
# 8.1 — cross-source contradiction detection                                   #
# --------------------------------------------------------------------------- #
_CONTRADICTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "contradiction": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]},
        "explanation": {"type": "string"},
    },
    "required": ["contradiction", "severity", "explanation"],
}


def _source_identity(e: Evidence) -> str:
    """A coarse 'which source' key. A PDF passage and a SQL row are different sources;
    so are two different PDF documents."""
    if e.source_kind == "documents":
        return f"doc::{e.document or e.source_name}"
    if e.source_kind == "relational":
        return f"db::{e.table or e.source_name}"
    return f"{e.source_kind}::{e.source_name}"


def detect_contradictions(
    answer: str, evidence: list[Evidence], calls: list[LLMCall]
) -> tuple[list[dict], Optional[str], int]:
    """Find contradictions between evidence items from *different* sources that are cited
    together in the same answer sentence.

    Returns ``(contradictions, verification_warning, pairs_evaluated)``. Appends any LLM
    calls made to ``calls`` (so they are counted in pricing). No-ops (returns empties)
    when fewer than two distinct sources are cited anywhere.
    """
    by_id = {e.id: e for e in evidence}
    distinct_sources = {_source_identity(e) for e in evidence if e.used}
    if len(distinct_sources) < 2:
        return [], None, 0

    # collect candidate cross-source pairs that co-occur in a sentence
    pairs: dict[frozenset, str] = {}      # {ids} -> sentence text (first seen)
    for sentence in _SENTENCE_SPLIT.split(answer or ""):
        ids = [m for m in dict.fromkeys(_MARKER.findall(sentence)) if m in by_id]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = by_id[ids[i]], by_id[ids[j]]
                if _source_identity(a) == _source_identity(b):
                    continue
                key = frozenset((a.id, b.id))
                pairs.setdefault(key, sentence.strip())

    if not pairs:
        return [], None, 0

    s = get_settings()
    llm = get_llm()
    contradictions: list[dict] = []
    evaluated = 0
    for key, sentence in list(pairs.items())[:_MAX_CONTRADICTION_PAIRS]:
        a_id, b_id = tuple(key)
        a, b = by_id[a_id], by_id[b_id]
        user = (
            f"Evidence A ({a.citation_label}) says: {a.content}\n\n"
            f"Evidence B ({b.citation_label}) says: {b.content}\n\n"
            f"They were cited together for this statement: \"{sentence}\""
        )
        data, call = llm.structured(
            purpose="contradiction_check",
            model=s.model_router,
            system=(
                "You check whether two pieces of evidence contradict each other on the "
                "SAME underlying fact. Differences in topic or detail are NOT "
                "contradictions. Respond strictly as JSON."
            ),
            user=user,
            schema=_CONTRADICTION_SCHEMA,
            fallback=lambda: {"contradiction": False, "severity": "none",
                              "explanation": "Offline — contradiction not evaluated."},
            max_tokens=300,
        )
        if call:
            calls.append(call)
        evaluated += 1
        if data.get("contradiction"):
            contradictions.append({
                "evidence_a": a_id,
                "evidence_b": b_id,
                "source_a": a.citation_label,
                "source_b": b.citation_label,
                "severity": data.get("severity", "minor"),
                "explanation": data.get("explanation", ""),
                "sentence": sentence,
            })

    warning = None
    if any(c["severity"] == "major" for c in contradictions):
        warning = ("Some sources contain conflicting information. "
                   "See the Explainability panel for details.")
    return contradictions, warning, evaluated


# --------------------------------------------------------------------------- #
# 8.1 — hallucination risk score                                               #
# --------------------------------------------------------------------------- #
def compute_hallucination_risk(
    check: Optional[CitationCheck],
    contradictions: list[dict],
    pairs_evaluated: int,
) -> float:
    """``(unverified/total citations)*0.5 + (major contradictions/pairs)*0.5`` → [0,1]."""
    total_cit = len(check.cited_ids) if check else 0
    unverified = len(check.unknown_ids) if check else 0
    cit_term = (unverified / total_cit) if total_cit else 0.0

    major = sum(1 for c in contradictions if c.get("severity") == "major")
    contra_term = (major / pairs_evaluated) if pairs_evaluated else 0.0

    return round(min(1.0, max(0.0, 0.5 * cit_term + 0.5 * contra_term)), 3)
