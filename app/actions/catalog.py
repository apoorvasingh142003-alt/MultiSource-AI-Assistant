"""The built-in action-tool contracts.

Three actions cover the buyer stories from the job posts: capture a lead to a CRM,
escalate a conversation to a human, and a vertical write (create an invoice). Adding an
action is a new catalog entry + (optionally) detection cues — the dispatch, config,
audit-log, and UI machinery are shared.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionSpec:
    """One action-tool contract: what it does, what it needs, how the UI labels it."""

    name: str                              # stable id ("create_lead")
    title: str                             # human label ("Create lead")
    description: str                       # what confirming this action does
    params: list[str] = field(default_factory=list)      # ordered param names
    required: list[str] = field(default_factory=list)    # subset that must be non-empty


ACTIONS: dict[str, ActionSpec] = {
    "create_lead": ActionSpec(
        name="create_lead",
        title="Create lead",
        description="Write a new lead to your CRM via your n8n workflow.",
        params=["name", "email", "company", "note"],
        required=["name"],
    ),
    "escalate": ActionSpec(
        name="escalate",
        title="Escalate to a human",
        description="Hand this conversation off to a human via your n8n workflow "
                    "(e.g. notify support, open a ticket).",
        params=["reason", "context"],
        required=["reason"],
    ),
    "create_invoice": ActionSpec(
        name="create_invoice",
        title="Create invoice",
        description="Create an invoice in your accounting system (e.g. QuickBooks) "
                    "via your n8n workflow.",
        params=["customer", "amount", "currency", "description"],
        required=["customer", "amount"],
    ),
}


def get_action(name: str) -> ActionSpec | None:
    return ACTIONS.get(name)
