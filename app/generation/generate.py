"""Grounded generation.

The model is instructed to answer ONLY from the supplied evidence and to cite each
claim with an evidence id like [e1]. If the evidence is insufficient it must say so
rather than guess. Offline, a deterministic extractive generator composes a grounded,
cited answer directly from the evidence — so the grounding/citation behaviour is
demonstrable even with no API key.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.config import get_settings
from app.llm.client import get_llm
from app.models import Evidence, LLMCall
from app.roles import get_role

_ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
        "insufficient": {"type": "boolean"},
    },
    "required": ["answer", "citations", "insufficient"],
}

_BASE_SYSTEM = (
    "You are Nexus AI, an Adaptive Multi-Domain Intelligence Agent. Today's date is "
    "2026-06-08.\n\n"
    "MISSION\n"
    "Analyze information from any domain, profession, or industry using ONLY the "
    "evidence provided by the system.\n\n"
    "ROLE ENGINE\n"
    "Assigned Role: {role_label}\n"
    "If a role is provided, fully adopt that role's expertise, reasoning framework, "
    "terminology, methodology, priorities, standards, and decision-making process. "
    "If no specific role is provided, infer the most appropriate expert perspective "
    "or combination of expert perspectives required for the task.\n\n"
    "OUTPUT ENGINE\n"
    "Output Mode: {output_mode}\n"
    "Supported modes include Standard Response, Executive Summary, Timeline, "
    "Detailed Report, Comparison Table, Risk Assessment, Dashboard Summary, SWOT "
    "Analysis, Audit Report, Research Report, Action Plan, Decision Matrix, Legal "
    "Review, Financial Review, and Medical Assessment.\n\n"
    "MULTI-DOMAIN REASONING\n"
    "Before answering, understand the objective, identify the domain(s), identify "
    "relevant expertise, evaluate the evidence, detect uncertainty, and produce the "
    "best professional response.\n\n"
    "EVIDENCE FRAMEWORK\n"
    "Never claim certainty without evidence. Classify support as Strong Evidence, "
    "Moderate Evidence, Limited Evidence, or No Supporting Evidence when confidence "
    "or evidence quality is relevant. High confidence requires strong evidence; "
    "medium confidence requires moderate evidence; low confidence requires limited "
    "evidence; unknown confidence means evidence is absent. Never output 100% "
    "confidence if evidence is insufficient.\n\n"
    "GROUNDING RULES\n"
    "Use ONLY the provided evidence. Never use outside knowledge or assumptions. "
    "Never invent facts or evidence. Distinguish facts from assumptions. Cite every "
    "factual claim inline with the evidence id(s), e.g. [e1] or [e2][e5]. "
    "The 'citations' JSON field must list the evidence ids actually used.\n"
    "Database rows in the evidence have already been filtered to satisfy the "
    "question's constraints, so treat them as authoritative and do NOT re-derive "
    "or second-guess them.\n"
    "If the question asks WHICH or WHAT document contains, mentions, or references "
    "a term, answer in a complete sentence that names the document and page(s). "
    "Never answer with a bare filename alone.\n"
    "If the evidence genuinely does not contain enough to answer, set "
    "insufficient=true and briefly say what is missing. Do NOT fabricate.\n"
    "Write the answer in the language of the QUESTION. Be concise, specific, "
    "professional, visually structured when useful, and suitable for commercial use. "
    "Return JSON only."
)

# --- Output format directives (Section 3) ------------------------------------
_OUTPUT_FORMAT_DIRECTIVES: dict[str, str] = {
    "table": (
        "Present your answer as a well-structured markdown table. Use clear column "
        "headers. If data has a time dimension, add a Date/Period column as the first "
        "column. Sort rows chronologically or by relevance."
    ),
    "timeline_table": (
        "Present your answer as a timeline table with columns: Date/Period | "
        "Event/Milestone | Details | Source. Highlight key dates."
    ),
    "json": (
        "Return your answer as a valid JSON object. No prose outside the JSON block."
    ),
    "bullet_points": (
        "Present your answer as a concise bulleted list. Each bullet is one claim "
        "with its citation."
    ),
    "executive_summary": (
        "Present your answer as an executive summary: one paragraph of key findings, "
        "followed by a 'Key Points' bulleted list, followed by a 'Recommended "
        "Actions' section."
    ),
    "prose": "",  # default behavior — no change
    "auto": "",   # let the LLM decide
}


def _get_system_prompt(
    role: Optional[str] = None,
    output_mode: str = "Standard Response",
    custom_system_prompt: Optional[str] = None,
    agent_role: Optional[str] = None,
    output_format: Optional[str] = "auto",
) -> str:
    """Build system prompt with optional role-specific adaptation, custom prompts,
    and output format directives (Sections 2 & 3)."""
    role_obj = get_role(role)
    role_label = role_obj.label if role_obj.name != "default" else "Auto-selected / Business Analyst"

    # If agent_role is provided (Section 2), use it as the role label
    if agent_role:
        role_label = agent_role

    prompt = _BASE_SYSTEM.format(
        role_label=role_label,
        output_mode=output_mode or "Standard Response",
    )

    # Prepend role-specific instructions from the roles registry
    if role_obj.name != "default":
        prompt = f"{role_obj.system_instruction}\n\n{prompt}"

    # Prepend agent_role as a first line if set (Section 2)
    if agent_role:
        prompt = f"You are {agent_role}.\n\n{prompt}"

    # Override or append custom_system_prompt if set (Section 2)
    if custom_system_prompt:
        # Always preserve grounding rules — append custom prompt before them
        prompt = f"{custom_system_prompt}\n\n{prompt}"

    # Inject output format directive (Section 3)
    fmt = (output_format or "auto").lower().strip()
    directive = _OUTPUT_FORMAT_DIRECTIVES.get(fmt, "")
    if directive:
        prompt += f"\n\nOUTPUT FORMAT INSTRUCTION\n{directive}"

    return prompt


def _clean_row(content: str) -> str:
    """Drop internal id columns from a 'k=v; k=v' row for a more readable offline answer."""
    fields = [f.strip() for f in content.split(";")]
    kept = [f for f in fields if f and not re.match(r"^\w*_?id=", f, re.I)]
    return "; ".join(kept) or content


def _evidence_block(evidence: list[Evidence]) -> str:
    lines = []
    for e in evidence:
        prov = e.citation_label
        lines.append(f"{e.id} {prov}\n{e.content}")
    return "\n\n".join(lines)


def _humanize_doc(name: str) -> str:
    """A cleaner display name for a document — strips an upload timestamp/hash suffix
    and the extension, without inventing a title."""
    base = re.sub(r"\.(pdf|txt)$", "", name, flags=re.I)
    # drop a trailing "-2026-06-02-07-29-09-289628" style upload stamp
    base = re.sub(r"[-_](?:\d{2,4})(?:[-_]\d{1,6}){2,}$", "", base)
    base = base.replace("_", " ").replace("-", " ").strip()
    return base or name


def _keyword_answer(terms: list[str], evidence: list[Evidence]) -> dict[str, Any]:
    """Deterministic, professional answer for a 'which document contains X' lookup."""
    docs: dict[str, list[Evidence]] = {}
    for e in evidence:
        docs.setdefault(e.document or e.source_name, []).append(e)
    term_str = ", ".join(f'"{t}"' for t in terms) if terms else "the term"
    lead = "keyword" if len(terms) <= 1 else "keywords"
    parts = []
    for doc, evs in docs.items():
        pages = sorted({e.page for e in evs if e.page is not None})
        cites = "".join(f"[{e.id}]" for e in evs)
        page_str = (
            f" (page {pages[0]})" if len(pages) == 1
            else f" (pages {', '.join(map(str, pages))})" if pages else ""
        )
        parts.append(f"{_humanize_doc(doc)} — {doc}{page_str} {cites}".strip())
    if len(parts) == 1:
        answer = f"The {lead} {term_str} appears in {parts[0]}."
    else:
        answer = (f"The {lead} {term_str} appears in {len(parts)} documents: "
                  + "; ".join(parts) + ".")
    return {"answer": answer, "citations": [e.id for e in evidence], "insufficient": False}


def _extractive_fallback(
    question: str, evidence: list[Evidence], keyword_terms: list[str] | None = None
) -> dict[str, Any]:
    if not evidence:
        return {
            "answer": "Insufficient evidence: no relevant records or document passages were "
                      "retrieved from the available sources to answer this question.",
            "citations": [], "insufficient": True,
        }
    if keyword_terms and all(e.source_kind == "documents" for e in evidence):
        return _keyword_answer(keyword_terms, evidence)
    rel = [e for e in evidence if e.source_kind == "relational"]
    doc = [e for e in evidence if e.source_kind == "documents"]
    parts: list[str] = []
    if rel:
        rows = "; ".join(f"{_clean_row(e.content)} {e.id}" for e in rel[:6])
        parts.append(f"From the business database — {rows}.")
    if doc:
        for e in doc[:3]:
            snippet = " ".join(e.content.split())
            snippet = snippet[:260] + ("…" if len(snippet) > 260 else "")
            parts.append(f"From {e.document} (p.{e.page}): \"{snippet}\" {e.id}.")
    answer = " ".join(parts)
    return {"answer": answer, "citations": [e.id for e in evidence], "insufficient": False}


def generate_answer(question: str, evidence: list[Evidence],
                    keyword_terms: list[str] | None = None,
                    role: Optional[str] = None,
                    output_mode: str = "Standard Response",
                    custom_system_prompt: Optional[str] = None,
                    agent_role: Optional[str] = None,
                    output_format: Optional[str] = "auto"):
    s = get_settings()
    llm = get_llm()
    system_prompt = _get_system_prompt(
        role, output_mode,
        custom_system_prompt=custom_system_prompt,
        agent_role=agent_role,
        output_format=output_format,
    )
    
    if not evidence:
        data = _extractive_fallback(question, evidence)
        return data["answer"], data["citations"], True, None

    # Keyword document lookups ("which document contains X") are a deterministic
    # identification task — answer them directly from the matched evidence. This
    # guarantees a professional, fully-grounded sentence with the exact document and
    # page(s), with zero LLM variance and no possibility of a bare-filename or
    # hallucinated response.
    if keyword_terms and all(e.source_kind == "documents" for e in evidence):
        data = _keyword_answer(keyword_terms, evidence)
        return data["answer"], data["citations"], data["insufficient"], None

    user = f"Question: {question}\n\nEvidence:\n{_evidence_block(evidence)}"
    data, call = llm.structured(
        purpose="generation", model=s.model_generation, system=system_prompt, user=user,
        schema=_ANSWER_SCHEMA,
        fallback=lambda: _extractive_fallback(question, evidence, keyword_terms),
        max_tokens=1500,
    )
    answer = (data.get("answer", "") or "").replace("\\n", "\n").strip()
    return (
        answer,
        list(data.get("citations", [])),
        bool(data.get("insufficient", False)),
        call,
    )


def generate_general_knowledge(
    question: str,
    role: Optional[str] = None,
    output_mode: str = "Standard Response",
    custom_system_prompt: Optional[str] = None,
    agent_role: Optional[str] = None,
    output_format: Optional[str] = "auto",
) -> tuple[str, Optional[LLMCall]]:
    """Generate an answer from the LLM's general/parametric knowledge (no indexed
    evidence). Used when the router classifies a question as GENERAL_KNOWLEDGE —
    answerable from world knowledge but not from any uploaded source.

    Returns (answer_text, llm_call_or_none).
    """
    s = get_settings()
    llm = get_llm()

    # Build a system prompt for general knowledge — no evidence grounding rules
    role_obj = get_role(role)
    role_label = role_obj.label if role_obj.name != "default" else "General Assistant"
    if agent_role:
        role_label = agent_role

    system = (
        f"You are Nexus AI, an Adaptive Multi-Domain Intelligence Agent.\n"
        f"Assigned Role: {role_label}\n"
        f"Output Mode: {output_mode or 'Standard Response'}\n\n"
        f"You are answering a question from your general knowledge. No indexed "
        f"documents or databases are available for this question. Answer accurately, "
        f"concisely, and professionally from your training knowledge.\n"
        f"Write the answer in the language of the QUESTION.\n"
        f"Return JSON only."
    )

    if agent_role:
        system = f"You are {agent_role}.\n\n{system}"
    if custom_system_prompt:
        system = f"{custom_system_prompt}\n\n{system}"

    # Inject output format directive
    fmt = (output_format or "auto").lower().strip()
    directive = _OUTPUT_FORMAT_DIRECTIVES.get(fmt, "")
    if directive:
        system += f"\n\nOUTPUT FORMAT INSTRUCTION\n{directive}"

    gk_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
        },
        "required": ["answer"],
    }

    def _fallback() -> dict:
        return {"answer": "I can answer this from general knowledge, but the LLM "
                          "service is currently unavailable. Please try again."}

    try:
        data, call = llm.structured(
            purpose="general_knowledge_generation",
            model=s.model_generation,
            system=system,
            user=f"Question: {question}",
            schema=gk_schema,
            fallback=_fallback,
            max_tokens=1500,
        )
        answer = (data.get("answer", "") or "").replace("\\n", "\n").strip()
        return answer, call
    except Exception:
        return _fallback()["answer"], None
