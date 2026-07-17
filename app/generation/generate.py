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


# --- Document-intelligence directive (Phase 5) --------------------------------
# Appended to the grounded system prompt when the question's reasoning mode is
# "analysis" (clause analysis, risk identification, assessment). This is grounded
# REASONING over retrieved evidence — organised, professional analysis in which every
# finding is cited — never invention: the tri-state wall is untouched (the answer
# stays grounded because every claim still traces to evidence).
_ANALYSIS_DIRECTIVE = (
    "DOCUMENT INTELLIGENCE MODE\n"
    "The user asked for an ANALYSIS of the record (clauses, risks, obligations, "
    "gaps, quality). Perform a structured professional analysis STRICTLY over the "
    "Evidence block:\n"
    "- Organise findings under clear markdown headings (by document, clause, or "
    "risk theme — whichever fits the question).\n"
    "- Every finding must quote or paraphrase the evidence and carry its [eN] "
    "citation. Analytical observations (e.g. 'this cap is one-sided') must be "
    "visibly derived from a cited passage.\n"
    "- Where the record is SILENT on an aspect the question implies, state exactly "
    "that — 'the record does not address X' — as a fact about the record only; "
    "never fill the gap from outside knowledge.\n"
    "- Do NOT give recommendations or external best-practice guidance in this mode; "
    "confine the answer to what the evidence supports."
)


def _get_system_prompt(
    role: Optional[str] = None,
    output_mode: str = "Standard Response",
    custom_system_prompt: Optional[str] = None,
    agent_role: Optional[str] = None,
    output_format: Optional[str] = "auto",
    reasoning_mode: Optional[str] = None,
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

    # Document-intelligence directive (Phase 5) — grounded analysis over the evidence.
    if reasoning_mode == "analysis":
        prompt += f"\n\n{_ANALYSIS_DIRECTIVE}"

    return prompt


# Models occasionally emit grouped citation markers ("[e1, e2, e3]" or "[e2; e5]")
# despite the prompt's "[e1] or [e2][e5]" examples. The strict [eN] marker regex used by
# verification, contribution analysis, and the UI's clickable-citation renderer would
# see NONE of those ids — a correctly grounded answer would then fail verification.
_CITE_GROUP = re.compile(r"\[(e\d+(?:\s*[,;/]\s*e\d+)+)\]")


def _normalize_citation_groups(text: str) -> str:
    """Rewrite grouped citation markers into the canonical adjacent form "[e1][e2][e3]"
    so every downstream [eN] consumer sees every cited id."""
    return _CITE_GROUP.sub(
        lambda m: "".join(f"[{t}]" for t in re.findall(r"e\d+", m.group(1))), text or ""
    )


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


def _build_user_message(question: str, evidence: list[Evidence],
                        conversation_history: Optional[list[dict]] = None) -> str:
    """Assemble the user message: optional conversation context (for reference
    resolution only) + the current question + the grounded evidence block."""
    from app.conversation import format_history_block
    parts: list[str] = []
    hist = format_history_block(conversation_history)
    if hist:
        parts.append(
            "Conversation so far (use ONLY to resolve references like pronouns or "
            "\"the second one\"; do NOT treat it as evidence — every fact must be "
            "grounded in the Evidence block below):\n" + hist
        )
    parts.append(f"Question: {question}")
    parts.append(f"Evidence:\n{_evidence_block(evidence)}")
    return "\n\n".join(parts)


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
                    output_format: Optional[str] = "auto",
                    temperature: Optional[float] = None,
                    conversation_history: Optional[list[dict]] = None,
                    reasoning_mode: Optional[str] = None):
    s = get_settings()
    llm = get_llm()
    system_prompt = _get_system_prompt(
        role, output_mode,
        custom_system_prompt=custom_system_prompt,
        agent_role=agent_role,
        output_format=output_format,
        reasoning_mode=reasoning_mode,
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

    user = _build_user_message(question, evidence, conversation_history)
    data, call = llm.structured(
        purpose="generation", model=s.model_generation, system=system_prompt, user=user,
        schema=_ANSWER_SCHEMA,
        fallback=lambda: _extractive_fallback(question, evidence, keyword_terms),
        max_tokens=1500, temperature=temperature,
    )
    answer = _normalize_citation_groups(
        (data.get("answer", "") or "").replace("\\n", "\n").strip()
    )
    return (
        answer,
        list(data.get("citations", [])),
        bool(data.get("insufficient", False)),
        call,
    )


def generate_answer_stream(question: str, evidence: list[Evidence],
                           on_token, role: Optional[str] = None,
                           output_mode: str = "Standard Response",
                           custom_system_prompt: Optional[str] = None,
                           agent_role: Optional[str] = None,
                           output_format: Optional[str] = "auto",
                           temperature: Optional[float] = None,
                           conversation_history: Optional[list[dict]] = None,
                           reasoning_mode: Optional[str] = None):
    """Streaming, prose-mode counterpart of ``generate_answer``.

    Streams the grounded answer token-by-token via ``on_token(delta)`` and returns
    ``(answer, citations, insufficient, call)``. Citations are recovered from the inline
    ``[eN]`` markers in the streamed text, so the verification step downstream is identical
    to the non-streaming path. Used only by ``/ask/stream``; ``/ask`` keeps JSON mode.
    """
    s = get_settings()
    llm = get_llm()

    if not evidence:
        data = _extractive_fallback(question, evidence)
        on_token(data["answer"])
        return data["answer"], data["citations"], True, None

    # keyword identification answers are deterministic — emit directly (no LLM variance)
    # handled by the caller before streaming; here we always generate prose.
    system_prompt = _get_system_prompt(
        role, output_mode, custom_system_prompt=custom_system_prompt,
        agent_role=agent_role, output_format=output_format,
        reasoning_mode=reasoning_mode,
    )
    # prose streaming: override the "Return JSON only." instruction
    system_prompt = system_prompt.replace("Return JSON only.", "").rstrip() + (
        "\n\nWrite the answer as well-structured prose (or the requested format). Cite "
        "every factual claim inline with the evidence id(s), e.g. [e1] or [e2][e5]. Do "
        "NOT output JSON or any wrapper object — just the answer text."
    )
    user = _build_user_message(question, evidence, conversation_history)

    def _fallback() -> str:
        return _extractive_fallback(question, evidence)["answer"]

    answer, call = llm.stream_text(
        purpose="generation_stream", model=s.model_generation, system=system_prompt,
        user=user, on_token=on_token, fallback=_fallback, max_tokens=1500,
        temperature=temperature,
    )
    answer = _normalize_citation_groups((answer or "").strip())
    cited = sorted(set(re.findall(r"\[(e\d+)\]", answer)), key=lambda x: int(x[1:]))
    return answer, cited, False, call


def generate_general_knowledge(
    question: str,
    role: Optional[str] = None,
    output_mode: str = "Standard Response",
    custom_system_prompt: Optional[str] = None,
    agent_role: Optional[str] = None,
    output_format: Optional[str] = "auto",
    temperature: Optional[float] = None,
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
            max_tokens=1500, temperature=temperature,
        )
        answer = (data.get("answer", "") or "").replace("\\n", "\n").strip()
        return answer, call
    except Exception:
        return _fallback()["answer"], None


# Begins PART 2 of every grounded-advice answer — the line the model is required to lead the
# guidance section with, so general (parametric) guidance is never mistaken for a grounded fact.
ADVICE_GUIDANCE_DISCLAIMER = (
    "⚠️ The following is general guidance from model knowledge, not from your uploaded "
    "sources, and may be inaccurate."
)


# Part-2 directive per reasoning mode (Phase 5). "advice" keeps the original guidance
# treatment; "design" turns Part 2 into a structured strategy/plan deliverable — still
# labelled, still citation-free, still anchored to the Part-1 facts in words.
_ADVICE_PART2_DIRECTIVES: dict[str, str] = {
    "advice": (
        "Then give accurate, well-established general guidance, relating it to the grounded "
        "facts from Part 1 where relevant. Do NOT attach [eN] citations to Part 2."
    ),
    "design": (
        "Then deliver the requested design / strategy / plan as a STRUCTURED deliverable "
        "with clear markdown headings — typically: Situation assessment (a short synthesis "
        "of the Part 1 facts, in words), Strategy & options (2–3 options with trade-offs), "
        "Recommendations (specific, per document/item where Part 1 supports it), Risks & "
        "mitigations, and Next steps. Anchor every recommendation to a Part 1 fact in words "
        "where one exists (e.g. 'given the 27% early-termination penalty noted above…'); "
        "where the record is silent, present the point explicitly as general practice, not "
        "as a fact about these documents. Do NOT attach [eN] citations to Part 2."
    ),
}


def _advice_fallback(evidence: list[Evidence], mode: str) -> str:
    """Deterministic two-part advice/design answer (offline / LLM-error path). PART 1 is
    a real extractive grounding of the retrieved passages (cited); PART 2 is the labelled
    disclaimer followed by honest method guidance — structured for design mode — that
    asserts nothing about the world beyond the cited record."""
    lines: list[str] = ["PART 1 — From the record:"]
    if evidence:
        for e in evidence[:6]:
            snippet = " ".join((e.content or "").split())
            snippet = snippet[:220] + ("…" if len(snippet) > 220 else "")
            where = (f"{e.document} (p.{e.page})" if e.document
                     else e.source_name)
            lines.append(f"- {where}: \"{snippet}\" [{e.id}]")
    else:
        lines.append("- The record contains no passages relevant to this question.")
    lines += ["", "PART 2 — General guidance (not from your sources):",
              ADVICE_GUIDANCE_DISCLAIMER]
    if mode == "design" and evidence:
        docs = []
        for e in evidence:
            d = e.document or e.source_name
            if d and d not in docs:
                docs.append(d)
        doc_str = ", ".join(docs[:5]) + ("…" if len(docs) > 5 else "")
        lines += [
            "A structured way to build this from the grounded record:",
            f"1. **Baseline the current terms** — work item-by-item through the cited "
            f"passages above ({doc_str}) and list the operative terms each one sets.",
            "2. **Set objectives** — decide what the design must achieve (e.g. retention, "
            "risk reduction, better terms) and rank them.",
            "3. **Draft options against the record** — for each objective, sketch 2–3 "
            "options and check each against the cited terms for conflicts.",
            "4. **Identify risks and mitigations** — note where the record is silent or "
            "restrictive, and plan around it.",
            "5. **Agree next steps and owners** — convert the chosen option into dated "
            "actions, and validate the result with a qualified professional.",
        ]
    else:
        lines.append(
            "Weigh the grounded facts above with a qualified professional before acting. "
            "The live advisory model is unavailable, so no specific recommendation is "
            "generated in offline mode."
            if evidence else
            "The record does not cover this topic and the live advisory model is "
            "unavailable, so no specific guidance can be generated right now."
        )
    return "\n".join(lines)


def generate_grounded_advice(
    question: str,
    evidence: list[Evidence],
    role: Optional[str] = None,
    output_mode: str = "Standard Response",
    custom_system_prompt: Optional[str] = None,
    agent_role: Optional[str] = None,
    output_format: Optional[str] = "auto",
    temperature: Optional[float] = None,
    conversation_history: Optional[list[dict]] = None,
    mode: str = "advice",
    on_token=None,
):
    """Answer a recommendation/advice or design/strategy question in TWO clearly-separated
    parts: PART 1 grounds the subject's relevant facts from ``evidence`` (cited, never
    invented); PART 2 gives clearly-labelled, disclaimed guidance — free-form for
    ``mode="advice"``, a structured strategy deliverable for ``mode="design"``. Streams
    via ``on_token`` when provided. Returns the standard ``(answer, citations,
    insufficient, call)`` tuple so the orchestrator finalises it like any grounded answer
    (real citation verification runs over PART 1)."""
    s = get_settings()
    llm = get_llm()
    role_obj = get_role(role)
    role_label = role_obj.label if role_obj.name != "default" else (
        "Solution Designer / Strategist" if mode == "design" else "Domain Advisor"
    )
    if agent_role:
        role_label = agent_role
    has_ctx = bool(evidence)
    ask_kind = ("a design / strategy / plan" if mode == "design"
                else "a recommendation / judgement / opinion")
    part2_directive = _ADVICE_PART2_DIRECTIVES.get(mode, _ADVICE_PART2_DIRECTIVES["advice"])

    system = (
        "You are Nexus AI, an Adaptive Multi-Domain Intelligence Agent.\n"
        f"Assigned Role: {role_label}\n"
        f"Output Mode: {output_mode or 'Standard Response'}\n\n"
        f"The user asked for {ask_kind}. Answer in TWO clearly "
        "separated, labelled parts and NEVER blur them:\n\n"
        "PART 1 — From the record:\n"
        "Use ONLY the Evidence block. State the facts about the subject that are relevant to "
        "the question, each with its [eN] citation. If the Evidence does not address the "
        "topic, say plainly that the record does not mention it. NEVER invent names, dates, "
        "doses, diagnoses, events, or citations — if it is not in the Evidence, it is not a "
        "fact about this subject.\n\n"
        "PART 2 — General guidance (not from your sources):\n"
        f"Begin this part with EXACTLY this sentence: \"{ADVICE_GUIDANCE_DISCLAIMER}\"\n"
        f"{part2_directive}\n\n"
        "Write in the language of the question. Output ONLY the two-part answer as plain "
        "text — do NOT wrap it in JSON or any object."
    )
    if agent_role:
        system = f"You are {agent_role}.\n\n{system}"
    if custom_system_prompt:
        system = f"{custom_system_prompt}\n\n{system}"

    if has_ctx:
        user = _build_user_message(question, evidence, conversation_history)
    else:
        user = (f"Question: {question}\n\nEvidence:\n(The record returned no passages relevant "
                "to this question — state that in Part 1, then give Part 2 guidance.)")

    def _fallback() -> str:
        return _advice_fallback(evidence, mode)

    # Prose, not JSON: free-form two-part text avoids weak-model JSON-wrapping artifacts.
    try:
        if on_token is not None:
            answer, call = llm.stream_text(
                purpose="grounded_advice_generation", model=s.model_generation,
                system=system, user=user, on_token=on_token, fallback=_fallback,
                max_tokens=1500, temperature=temperature,
            )
        else:
            answer, call = llm.text(
                purpose="grounded_advice_generation", model=s.model_generation,
                system=system, user=user, fallback=_fallback,
                max_tokens=1500, temperature=temperature,
            )
        answer = (answer or "").replace("\\n", "\n").strip()
    except Exception:
        answer = _fallback()
        call = None
    answer = _normalize_citation_groups(answer)
    # Safety net: if the model omitted (or paraphrased) the exact disclaimer sentence,
    # force it in — directly under the Part 2 header when one exists, so the label sits
    # in front of the guidance it disclaims, not orphaned at the bottom of the answer.
    if ADVICE_GUIDANCE_DISCLAIMER not in answer:
        m = re.search(r"^.*PART\s*2\b[^\n]*$", answer, re.M | re.I)
        if m:
            answer = (answer[:m.end()] + "\n" + ADVICE_GUIDANCE_DISCLAIMER
                      + answer[m.end():])
        else:
            answer = (answer + "\n\n" if answer else "") + ADVICE_GUIDANCE_DISCLAIMER
    cited = sorted(set(re.findall(r"\[(e\d+)\]", answer)), key=lambda x: int(x[1:]))
    return answer, cited, False, call
