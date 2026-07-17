"""Sufficiency assessment + query reformulation for iterative (deep-research) retrieval.

The heart of Phase 4: after each retrieval round the engine asks "does the evidence
collected so far actually answer the question?" — and if not, WHAT is missing and WHERE
to look next. Two layers, mirroring the router's design:

- A **deterministic heuristic core** that always runs: term coverage of the question
  against the accumulated evidence, uncovered sub-aspects of a multi-part question, and
  corpus *spread* ("across all contracts" needs evidence from multiple documents, not
  three chunks of one). This is the offline path AND the fallback for the live path, so
  the loop is fully testable with no key.
- An optional **LLM refinement** (any provider, via the shared client) that can judge
  sufficiency semantically and propose sharper follow-up queries. It degrades to the
  heuristic verdict on any failure.

The verdict only ever steers *retrieval*. It never touches generation or the tri-state
grounding wall — an insufficient verdict means "search more", not "answer differently".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.config import get_settings
from app.llm.client import get_llm
from app.models import Evidence, LLMCall
from app.retrieval.intent import content_terms

# "Answer spread across many docs" cues: a quantifier/comparative + a corpus noun.
_SPREAD_CUE = re.compile(r"\b(all|each|every|across|compare|comparison|between|both)\b", re.I)
_SPREAD_NOUN = re.compile(
    r"\b(contracts?|agreements?|documents?|docs?|pdfs?|briefs?|reports?|files?|"
    r"customers?|projects?|sources?|vertr[aä]ge)\b",
    re.I,
)

# Meta-verbs and quantifiers that describe the QUESTION, not the answer ("what do the
# contracts SAY ACROSS all agreements") — they will never literally appear in a relevant
# passage, so counting them against coverage would make sufficiency unreachable.
_GENERIC = {
    "say", "says", "said", "state", "states", "stated", "specify", "specified",
    "describe", "describes", "described", "regarding", "according", "across",
    "between", "overall", "various", "different", "respective", "specific",
}

# Split a multi-part question into sub-aspects only at strong connectors followed by a
# fresh interrogative/imperative — never inside noun phrases ("terms and conditions").
_ASPECT_SPLIT = re.compile(
    r"(?:;|,?\s+and\s+(?=(?:what|which|how|who|whom|when|where|why|list|show|"
    r"summari[sz]e|compare|do(?:es)?\s|are\s|is\s)))",
    re.I,
)

_SUFFICIENCY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sufficient": {"type": "boolean"},
        "missing": {"type": "array", "items": {"type": "string"}},
        "next_queries": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["sufficient", "missing", "next_queries", "reasoning"],
}

_SUFFICIENCY_SYSTEM = (
    "You are the sufficiency checker inside an iterative retrieval loop. Given a user "
    "question and the evidence retrieved so far, decide whether the evidence is enough "
    "to answer the question fully and faithfully. If it is not, name what is missing and "
    "propose up to 3 focused follow-up search queries (short keyword-style, in the "
    "question's language) that would retrieve the missing evidence from the user's "
    "documents/database. Judge ONLY evidence coverage — never answer the question. "
    "Return JSON only."
)


@dataclass
class NextQuery:
    """One reformulated follow-up search the loop should run next."""

    query: str
    documents: Optional[list[str]] = None   # restrict retrieval to these documents
    reason: str = ""

    def as_dict(self) -> dict:
        d: dict = {"query": self.query, "reason": self.reason}
        if self.documents:
            d["documents"] = self.documents
        return d


@dataclass
class SufficiencyVerdict:
    sufficient: bool
    coverage: float                          # 0..1 question-term coverage
    missing_terms: list[str] = field(default_factory=list)
    missing_aspects: list[str] = field(default_factory=list)
    missing_documents: list[str] = field(default_factory=list)
    next_queries: list[NextQuery] = field(default_factory=list)
    reasoning: str = ""
    source: str = "heuristic"                # "heuristic" | "llm"
    call: Optional[LLMCall] = None

    def as_dict(self) -> dict:
        """JSON-safe shape for the research trace + SSE progress events."""
        return {
            "sufficient": self.sufficient,
            "coverage": round(self.coverage, 3),
            "missing_terms": self.missing_terms,
            "missing_aspects": self.missing_aspects,
            "missing_documents": self.missing_documents,
            "next_queries": [q.as_dict() for q in self.next_queries],
            "reasoning": self.reasoning,
            "source": self.source,
        }


def split_aspects(question: str) -> list[str]:
    """Break a multi-part question into sub-aspects ('…overdue invoices, and what do
    their agreements say…' → two). Returns [] when the question is single-aspect."""
    parts = [p.strip(" ,;?") for p in _ASPECT_SPLIT.split(question or "") if p and p.strip(" ,;?")]
    return parts if len(parts) > 1 else []


def wants_corpus_spread(question: str) -> bool:
    """True when the question asks about the corpus at large ('across all contracts',
    'each customer agreement', 'compare the documents') — one document's chunks cannot
    be sufficient no matter how relevant they score."""
    q = question or ""
    return bool(_SPREAD_CUE.search(q) and _SPREAD_NOUN.search(q))


def _covered(term: str, ev_text: str) -> bool:
    """Is this question term present in the evidence? Tolerates simple inflection
    ('agreements' matches 'Agreement', 'penalties' → 'penalt…') so a plural in the
    question doesn't spuriously keep the loop searching forever."""
    if term in ev_text:
        return True
    if len(term) > 3 and term.rstrip("s") in ev_text:
        return True
    return len(term) > 6 and term[:5] in ev_text


def heuristic_verdict(
    question: str,
    evidence: list[Evidence],
    target_documents: Optional[list[str]] = None,
    settings=None,
) -> SufficiencyVerdict:
    """The deterministic sufficiency core (offline path + live fallback)."""
    s = settings or get_settings()
    ev_text = " ".join(
        f"{e.content} {e.citation_label}" for e in evidence
    ).lower()

    terms = [t for t in content_terms(question) if t not in _GENERIC]
    missing_terms = [t for t in terms if not _covered(t, ev_text)]
    coverage = (len(terms) - len(missing_terms)) / len(terms) if terms else 1.0

    aspects = split_aspects(question)
    missing_aspects = []
    for a in aspects:
        a_terms = [t for t in content_terms(a) if t not in _GENERIC]
        if a_terms and not any(_covered(t, ev_text) for t in a_terms):
            missing_aspects.append(a)

    docs_seen = sorted({e.document for e in evidence if e.document})
    missing_documents: list[str] = []
    spread_blocking = False
    if target_documents and wants_corpus_spread(question):
        missing_documents = [d for d in target_documents if d not in docs_seen]
        required = min(len(target_documents), max(2, s.research_spread_min_docs))
        spread_blocking = len(docs_seen) < required

    sufficient = (
        bool(evidence)
        and coverage >= s.research_min_coverage
        and not missing_aspects
        and not spread_blocking
    )

    next_queries: list[NextQuery] = []
    for a in missing_aspects:
        next_queries.append(NextQuery(query=a, reason="uncovered sub-question"))
    if spread_blocking:
        for d in missing_documents:
            next_queries.append(NextQuery(
                query=question, documents=[d],
                reason=f"no evidence yet from {d}",
            ))
    if missing_terms and not next_queries:
        next_queries.append(NextQuery(
            query=" ".join(missing_terms[:6]),
            reason="terms of the question not present in any evidence",
        ))

    if not evidence:
        reasoning = "No evidence collected yet."
    elif sufficient:
        reasoning = (f"Evidence covers {coverage:.0%} of the question terms"
                     + (f" across {len(docs_seen)} document(s)" if docs_seen else "")
                     + " — sufficient to answer.")
    else:
        gaps = []
        if missing_aspects:
            gaps.append(f"{len(missing_aspects)} sub-question(s) uncovered")
        if spread_blocking:
            gaps.append(f"only {len(docs_seen)} of {len(target_documents or [])} "
                        f"in-scope document(s) represented")
        if missing_terms:
            gaps.append("missing terms: " + ", ".join(missing_terms[:6]))
        reasoning = f"Coverage {coverage:.0%} — " + "; ".join(gaps or ["below threshold"]) + "."

    return SufficiencyVerdict(
        sufficient=sufficient, coverage=coverage,
        missing_terms=missing_terms, missing_aspects=missing_aspects,
        missing_documents=missing_documents, next_queries=next_queries,
        reasoning=reasoning, source="heuristic",
    )


def assess_sufficiency(
    question: str,
    evidence: list[Evidence],
    target_documents: Optional[list[str]] = None,
    settings=None,
    allow_llm: bool = True,
) -> SufficiencyVerdict:
    """Full assessment: deterministic core, refined by the live LLM when available.

    The LLM may sharpen the verdict and the follow-up queries; the heuristic's
    document-targeted spread queries are preserved (the LLM cannot see the corpus
    inventory). Any LLM failure degrades to the heuristic verdict unchanged."""
    s = settings or get_settings()
    v = heuristic_verdict(question, evidence, target_documents, s)
    if not (allow_llm and s.use_live_llm and evidence):
        return v

    llm = get_llm()
    ev_lines = "\n".join(
        f"[{e.id}] {e.citation_label}: {e.content[:220]}" for e in evidence[:20]
    )
    user = (f"Question: {question}\n\nEvidence retrieved so far "
            f"({len(evidence)} item(s)):\n{ev_lines}")

    def _fallback() -> dict:
        return {
            "sufficient": v.sufficient,
            "missing": v.missing_terms + v.missing_aspects,
            "next_queries": [q.query for q in v.next_queries],
            "reasoning": v.reasoning,
        }

    try:
        data, call = llm.structured(
            purpose="sufficiency", model=s.model_router,
            system=_SUFFICIENCY_SYSTEM, user=user,
            schema=_SUFFICIENCY_SCHEMA, fallback=_fallback,
        )
    except Exception:
        return v
    if not isinstance(data, dict) or call.mode == "stub":
        v.call = call if call.mode != "stub" else v.call
        return v

    llm_queries = [NextQuery(query=str(q).strip(), reason="proposed by sufficiency LLM")
                   for q in (data.get("next_queries") or []) if str(q).strip()]
    doc_targeted = [q for q in v.next_queries if q.documents]
    missing = [str(m) for m in (data.get("missing") or []) if str(m).strip()]
    return SufficiencyVerdict(
        sufficient=bool(data.get("sufficient", v.sufficient)),
        coverage=v.coverage,
        missing_terms=missing or v.missing_terms,
        missing_aspects=v.missing_aspects,
        missing_documents=v.missing_documents,
        next_queries=(llm_queries + doc_targeted) or v.next_queries,
        reasoning=str(data.get("reasoning") or v.reasoning),
        source="llm", call=call,
    )
