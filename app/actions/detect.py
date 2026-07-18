"""Deterministic action-command detection + parameter extraction.

Same philosophy as ``app/retrieval/intent.py``: a fully offline, word-bounded regex floor
that behaves identically with or without an LLM. A chat message is an *action command*
only when it carries an explicit imperative cue ("create a lead for …", "escalate this to
a human", "raise an invoice for …") — a factual question that merely mentions leads or
invoices ("total outstanding invoice amount per customer") must never trip it.

Extraction is best-effort: whatever the regexes miss stays editable in the ActionCard
before the user confirms, so an imperfect parse degrades to a pre-filled form — never to
a wrong dispatch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- cues (imperative verb required; word-bounded) ---------------------------
# The create-verb must precede the object noun within the same sentence, so
# "Which invoices were issued in March?" (noun before verb) can never match.
_LEAD_CUE = re.compile(
    r"\b(create|add|capture|log|register|save|open)\b[^.?!\n]{0,80}?\blead\b"
    r"|\badd\b[^.?!\n]{0,80}?\bto\s+(?:the\s+|our\s+)?crm\b",
    re.I,
)
_INVOICE_CUE = re.compile(
    r"\b(create|raise|issue|generate|send)\b[^.?!\n]{0,80}?\binvoice\b"
    r"(?!\s+(?:report|summary|list|table|history|breakdown))",
    re.I,
)
_ESCALATE_CUE = re.compile(
    r"\bescalate\b"
    r"|\bhand\s+(?:this\s+|it\s+|the\s+\w+\s+)?(?:off\s+|over\s+)?to\s+a\s+(?:human|person|agent)\b"
    r"|\b(?:talk|speak|connect(?:\s+me)?)\s+(?:to|with)\s+a\s+(?:human|person|agent|rep|representative)\b"
    r"|\bhuman\s+(?:agent|handoff|takeover)\b",
    re.I,
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A run of 1–4 Capitalized tokens (allows ALL-CAPS ids like ACME and "&" in company names).
_PROPER = r"[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3}"
_LEAD_NAME = re.compile(rf"\b(?:lead\s+for|for)\s+({_PROPER})")
_COMPANY = re.compile(rf"\b(?:at|from)\s+({_PROPER})")
_CUSTOMER = re.compile(rf"\b(?:for|to)\s+({_PROPER})")
_AMOUNT_SYM = re.compile(r"([$€£₪])\s*(\d[\d,]*(?:\.\d+)?)")
_AMOUNT_CODE = re.compile(r"\b(USD|EUR|GBP|ILS|NIS)\s*(\d[\d,]*(?:\.\d+)?)"
                          r"|(\d[\d,]*(?:\.\d+)?)\s*(USD|EUR|GBP|ILS|NIS|dollars|euros)\b", re.I)
_NOTE_SPLIT = re.compile(r"\s+[—–]\s+|:\s+")

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "₪": "ILS",
             "dollars": "USD", "euros": "EUR", "nis": "ILS"}


@dataclass
class ActionCommand:
    """A detected action command: which action, and the params extracted from the text."""

    action: str
    params: dict[str, str] = field(default_factory=dict)
    reason: str = ""                       # plain-English explanation for the trace


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip(" .,;—–-")


def _extract_lead(text: str) -> dict[str, str]:
    params: dict[str, str] = {}
    m = _EMAIL.search(text)
    if m:
        params["email"] = m.group(0)
    m = _LEAD_NAME.search(text)
    if m:
        params["name"] = _clean(m.group(1))
    m = _COMPANY.search(text)
    if m and _clean(m.group(1)) != params.get("name"):
        params["company"] = _clean(m.group(1))
    parts = _NOTE_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        params["note"] = _clean(parts[1])
    return params


def _extract_invoice(text: str) -> dict[str, str]:
    params: dict[str, str] = {}
    m = _AMOUNT_SYM.search(text)
    if m:
        params["currency"] = _CURRENCY.get(m.group(1), "USD")
        params["amount"] = m.group(2).replace(",", "")
    else:
        m = _AMOUNT_CODE.search(text)
        if m:
            code = (m.group(1) or m.group(4) or "USD").lower()
            params["currency"] = _CURRENCY.get(code, code.upper())
            params["amount"] = (m.group(2) or m.group(3) or "").replace(",", "")
    m = _CUSTOMER.search(text)
    if m:
        params["customer"] = _clean(m.group(1))
    parts = _NOTE_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        params["description"] = _clean(parts[1])
    return params


def detect_action_command(question: str) -> ActionCommand | None:
    """Classify a chat message as an explicit action command, or None (a normal question).

    Priority: the specific writes (lead / invoice) before the generic escalate, so
    "create a lead and escalate if urgent" proposes the lead (the concrete ask)."""
    q = question or ""
    if _LEAD_CUE.search(q):
        return ActionCommand(
            action="create_lead", params=_extract_lead(q),
            reason="Explicit lead-capture command detected — proposing create_lead "
                   "(no retrieval; nothing is sent until confirmed).",
        )
    if _INVOICE_CUE.search(q):
        return ActionCommand(
            action="create_invoice", params=_extract_invoice(q),
            reason="Explicit invoice command detected — proposing create_invoice "
                   "(no retrieval; nothing is sent until confirmed).",
        )
    if _ESCALATE_CUE.search(q):
        return ActionCommand(
            action="escalate", params={"reason": _clean(q)},
            reason="Explicit escalation request detected — proposing a human handoff "
                   "(nothing is sent until confirmed).",
        )
    return None
