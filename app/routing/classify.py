"""Intent classification & routing.

A hybrid router: a fast deterministic rule layer always runs (and is the offline
fallback), while Claude provides the primary, reasoned classification when available.

The router is *source-centric*, not *business-centric*: it asks "which uploaded source
could contain the answer?", never "does this sound like a business question?". Output
decides whether a question goes to documents, the database, both, or has insufficient
evidence in any source — and whether it needs the agentic SQL→entities→documents flow.
"""
from __future__ import annotations

from app.config import get_settings
from app.ingestion.pdf import detect_language
from app.llm.client import get_llm
from app.models import RouteDecision
from app.retrieval.intent import detect_intent

_ROUTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "route": {"type": "string", "enum": ["PDF", "SQL", "HYBRID", "NONE", "GENERAL_KNOWLEDGE"]},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
        "languages": {"type": "array", "items": {"type": "string"}},
        "document_subquery": {"type": "string"},
        "sql_subquery": {"type": "string"},
        "entity_hint": {"type": "string"},
        "agentic": {"type": "boolean"},
        "strategy_note": {"type": "string"},
    },
    "required": [
        "route", "reasoning", "confidence", "languages", "document_subquery",
        "sql_subquery", "entity_hint", "agentic", "strategy_note",
    ],
}

_SYSTEM = (
    "You are the query router for a multi-source knowledge assistant. Decide WHICH "
    "uploaded source(s) could contain the answer. Reason about evidence availability — "
    "where the answer could live — NOT about whether the question 'sounds like' a "
    "business or contract topic. Routes:\n"
    "- PDF: answerable from the uploaded DOCUMENTS — ANY information stated anywhere in "
    "their text or metadata. This includes names, parties, authors, recipients, "
    "signatories, dates, amounts, valuations, emails, phone numbers, contact details, "
    "organizations, universities, contracts, clauses, penalties, risks, definitions, "
    "summaries, recommendations, findings, and narrative content. If an uploaded document "
    "could plausibly contain the answer, route PDF — do NOT return NONE merely because the "
    "question is about a person, an author, a recipient, or metadata rather than a "
    "contract clause.\n"
    "- SQL: answerable purely from the structured DATABASE (counts, sums, dates, status).\n"
    "- HYBRID: needs BOTH (e.g. find rows in the DB, then read what the documents say).\n"
    "- NONE: the answer cannot be found in ANY uploaded source — insufficient evidence. "
    "Choose NONE only when NO listed document and NO database table could contain the "
    "information (e.g. employee headcount, office locations, HR/payroll, marketing, live "
    "weather) — do NOT force a lookup that cannot succeed. The test is evidence "
    "availability in the uploaded sources, never whether the topic is 'business-related'.\n"
    "Set agentic=true when the document step depends on the SQL results (e.g. 'which "
    "customers are overdue AND what do their contracts say' → query DB for the customers, "
    "then retrieve only those customers' contracts). Provide a focused document_subquery "
    "(what to look up in the documents) and sql_subquery (what to ask the database). "
    "Detect language(s) ('en','de').\n"
    "- GENERAL_KNOWLEDGE: the question is clearly answerable from general world knowledge "
    "(common facts, science, history, geography, etc.) but NONE of the uploaded sources "
    "contain the answer. Use this instead of NONE when the question IS answerable, just "
    "not from the indexed sources. Reserve NONE for truly unanswerable or nonsensical "
    "questions.\n"
    "Return JSON only."
)
# NOTE: this prompt is source-centric — PDF means "anything an uploaded document could
# state", so personal/author/recipient/metadata questions route PDF instead of NONE. The
# PDF and NONE *definitions* were broadened; the SQL/HYBRID definitions and the entire
# agentic sub-query paragraph below are preserved verbatim, because empirically even small
# wording changes to the sub-query guidance perturb the agentic HYBRID flow and once
# regressed a flagship demo (penalty clauses ev 9→4). This redesign was A/B-validated live
# against the full demo suite (scripts/eval.py) — the flagship HYBRID stays at ev=9. The
# deterministic document safety net remains as defence-in-depth. See docs/fix-design.md.

# --- deterministic rule layer (also the offline fallback) -------------------
# Contract/clause vocabulary — the "this reads like a contract" signals.
_DOC_KW = ["penalt", "suspension", "suspend", "clause", "terminat", "sla",
           "risk", "mitigation", "define", "definition", "mention", "what do",
           "what does", "agreement say", "contract say", "documentation", "brief"]
# Document-EVIDENCE vocabulary — facts that live in the body/metadata of an uploaded
# document but are NOT contract-clause terms: authors, recipients, parties, contact
# details, valuations, proposals. Source-centric routing means these are PDF lookups
# too — a document can state them even though they "don't sound like a contract".
_DOC_EVIDENCE_KW = [
    "author", "prepared", "recipient", "addressed to", "who is", "who signed",
    "signatory", "signed by", "who received", "who wrote", "who created",
    "which company", "which organization", "which organisation", "parties",
    "party to", "email", "phone", "contact", "valuation", "propos",
]
_SQL_KW = ["overdue", "invoice", "outstanding", "owe", "how many", "number of",
           "total ", "expire", "expir", "due ", "unpaid", "paid", "pending",
           "balance", "list all", "how much", "per customer"]
_DOMAIN = ["contract", "invoice", "project", "customer", "agreement", "payment",
           "penalt", "suspension", "sla", "risk", "overdue"]
# German contract/clause vocabulary — the German equivalents of the document signals
# (suspension/penalty/clause/cancellation/risk/service/agreement).
_DE_DOC = ["aussetzung", "kündigung", "vertragsstrafe", "strafe", "klausel", "risiko",
           "dienst", "vereinbarung", "vertrag", "kündig", "sagt"]


def rule_route(question: str) -> RouteDecision:
    q = question.lower()
    langs = ["de"] if detect_language(question) == "de" else ["en"]
    # A keyword document lookup ("find/which document contains X") is a PDF search even
    # when X is not a domain term — the deterministic layer must recognise it too, so the
    # offline path matches the live router instead of falling through to NONE.
    keyword_lookup = detect_intent(question).mode == "keyword"
    has_doc = (any(k in q for k in _DOC_KW) or any(k in q for k in _DOC_EVIDENCE_KW)
               or any(k in q for k in _DE_DOC) or keyword_lookup)
    has_sql = any(k in q for k in _SQL_KW)
    # A document-evidence term (author/recipient/email/valuation/…) keeps the question
    # in-domain even with no contract vocabulary — an uploaded document could answer it.
    in_domain = (any(k in q for k in _DOMAIN) or any(k in q for k in _DOC_EVIDENCE_KW)
                 or langs == ["de"] or any(k in q for k in _DE_DOC))

    agentic = False
    if "overdue" in q and (any(k in q for k in ["suspension", "suspend", "agreement", "contract", "say"])
                           or any(k in q for k in _DE_DOC)):
        route, agentic = "HYBRID", True
    elif ("expir" in q or "expire" in q) and any(k in q for k in ["penalt", "clause", "terminat"]):
        route, agentic = "HYBRID", True
    elif "project" in q and "risk" in q:
        route, agentic = "HYBRID", True
    elif keyword_lookup and not has_sql:
        route = "PDF"
    elif has_doc and has_sql:
        route = "HYBRID"
    elif has_sql:
        route = "SQL"
    elif has_doc:
        route = "PDF"
    elif in_domain:
        route = "PDF"
    else:
        route = "NONE"

    reasoning = {
        "PDF": "Document-evidence signals (a passage or metadata in the PDFs could state this); "
               "no structured lookup needed.",
        "SQL": "Structured-data signals (counts/dates/status); answerable from the database.",
        "HYBRID": "Needs both a database lookup and document evidence.",
        "NONE": "Insufficient evidence — no uploaded document or database source appears to "
                "contain what this question asks for.",
    }[route]
    return RouteDecision(
        route=route, reasoning=f"[rules] {reasoning}",
        confidence=0.55 if route not in ("NONE", "GENERAL_KNOWLEDGE") else 0.5,
        languages=langs,
        document_subquery=question, sql_subquery=question,
        entity_hint="entities returned by the SQL step" if agentic else "",
        agentic=agentic, strategy_note="deterministic rule layer",
    )


def _is_general_knowledge(question: str) -> bool:
    """Secondary classifier: can this NONE-routed question be answered from general
    world knowledge? Uses the LLM to decide. Falls back to False (keep NONE) on error."""
    s = get_settings()
    llm = get_llm()
    system = (
        "You are a classifier. Given a question, decide if it can be answered from "
        "general world knowledge (common facts, science, history, geography, math, "
        "definitions, etc.) without needing any specific uploaded document or database. "
        "Respond JSON only: {\"answerable\": true/false}"
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"answerable": {"type": "boolean"}},
        "required": ["answerable"],
    }
    try:
        data, _call = llm.structured(
            purpose="general_knowledge_check",
            model=s.model_router,
            system=system,
            user=f"Question: {question}",
            schema=schema,
            fallback=lambda: {"answerable": False},
        )
        return bool(data.get("answerable", False))
    except Exception:
        return False


def classify(question: str, capability_brief: str, agent_role: str | None = None,
             conversation_history: list[dict] | None = None):
    s = get_settings()
    llm = get_llm()
    fallback_decision = rule_route(question)

    def _fallback() -> dict:
        return fallback_decision.model_dump()

    # The agent's role can bias which source the router prefers (Section 2.1) — e.g. a
    # "legal analyst" leans toward contract PDFs. It is a hint, not an override.
    role_hint = (f"\n\nThe user is acting as: {agent_role}. If relevant, prefer the "
                 f"source most useful to that role, but only when it can actually answer."
                 if agent_role else "")
    # Prior turns help route follow-ups ("what about the second one?") to the same
    # source. Context only — routing stays deterministic (temperature 0).
    from app.conversation import format_history_block
    hist = format_history_block(conversation_history, max_chars=1500)
    hist_block = (f"\n\nConversation so far (context for resolving the question):\n{hist}"
                  if hist else "")
    user = (f"Available sources:\n{capability_brief}{hist_block}\n\n"
            f"Question: {question}{role_hint}")
    data, call = llm.structured(
        purpose="routing", model=s.model_router, system=_SYSTEM, user=user,
        schema=_ROUTE_SCHEMA, fallback=_fallback,
    )
    decision = RouteDecision(**data)
    if not decision.languages:
        decision.languages = fallback_decision.languages

    # Secondary classifier: upgrade NONE → GENERAL_KNOWLEDGE if answerable
    if decision.route == "NONE" and _is_general_knowledge(question):
        decision.route = "GENERAL_KNOWLEDGE"
        decision.reasoning += " [upgraded to GENERAL_KNOWLEDGE by secondary classifier]"
        decision.confidence = 0.75

    return decision, call
