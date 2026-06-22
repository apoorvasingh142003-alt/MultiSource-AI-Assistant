"""Project memory (Section 9) — a small, LLM-curated knowledge store per workspace.

After each workspace Q&A we run an extraction pass that pulls out durable facts,
entities, and preferences worth remembering ("Customer Tavor Systems has overdue
invoices", "User prefers table output", "Contract expiry threshold is 90 days"). On
each subsequent workspace question the relevant items are prepended to the generation
context so the assistant carries memory across turns.

Everything degrades gracefully: with no API key the extractor returns nothing (the
deterministic LLM fallback yields an empty list), so the rest of the pipeline is
unaffected and memory simply stays whatever was added manually via the API.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.config import get_settings
from app.db.migrations import get_session_db
from app.llm.client import get_llm
from app.models import LLMCall

log = logging.getLogger("aba.memory")

_MEMORY_TYPES = {"fact", "preference", "context", "entity"}

_EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "memory_type": {"type": "string",
                                    "enum": ["fact", "preference", "context", "entity"]},
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["memory_type", "key", "value", "confidence"],
            },
        }
    },
    "required": ["memories"],
}

_EXTRACT_SYSTEM = (
    "You extract durable, reusable knowledge from a single question/answer exchange so "
    "an assistant can remember it across a project. Extract ONLY persistent facts, named "
    "entities, and user preferences that would still be useful on a later, different "
    "question. Ignore one-off chit-chat and anything specific to only this answer. "
    "Each item: a short stable 'key' (e.g. 'overdue_customers', 'preferred_format'), a "
    "concise 'value', a memory_type of fact|preference|context|entity, and a confidence "
    "in [0,1]. Return an empty list if nothing is worth remembering. JSON only."
)


def extract_and_store(
    workspace_id: str, question: str, answer: str
) -> tuple[list[dict], Optional[LLMCall]]:
    """Run the extraction pass over a Q&A pair and persist new items.

    Returns ``(stored_items, llm_call)``. New items whose ``key`` already exists in the
    workspace are skipped (idempotent). Never raises — failures are logged and swallowed.
    """
    s = get_settings()
    llm = get_llm()
    try:
        data, call = llm.structured(
            purpose="memory_extraction",
            model=s.model_router,
            system=_EXTRACT_SYSTEM,
            user=f"Question: {question}\n\nAnswer: {answer}",
            schema=_EXTRACT_SCHEMA,
            fallback=lambda: {"memories": []},
            max_tokens=500,
        )
    except Exception:
        log.exception("memory extraction failed for workspace=%s", workspace_id)
        return [], None

    items = data.get("memories") or []
    if not items:
        return [], call

    stored: list[dict] = []
    db = get_session_db()
    try:
        existing = {
            r["key"].lower()
            for r in db.execute(
                "SELECT key FROM project_memory WHERE workspace_id = ?", (workspace_id,)
            ).fetchall()
        }
        for it in items:
            key = (it.get("key") or "").strip()
            value = (it.get("value") or "").strip()
            if not key or not value or key.lower() in existing:
                continue
            mtype = it.get("memory_type", "fact")
            if mtype not in _MEMORY_TYPES:
                mtype = "fact"
            conf = it.get("confidence", 0.6)
            try:
                conf = max(0.0, min(1.0, float(conf)))
            except (TypeError, ValueError):
                conf = 0.6
            mid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO project_memory (id, workspace_id, memory_type, key, value, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mid, workspace_id, mtype, key, value, conf),
            )
            existing.add(key.lower())
            stored.append({"id": mid, "memory_type": mtype, "key": key,
                           "value": value, "confidence": conf})
        db.commit()
    finally:
        db.close()
    if stored:
        log.info("stored %d memory item(s) for workspace=%s", len(stored), workspace_id)
    return stored, call


def get_memory_context(workspace_id: str, limit: int = 12) -> str:
    """Return a 'Known context from this workspace:' block for the most relevant memory
    items, and refresh their ``last_used`` timestamp. Empty string when there is none."""
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT id, memory_type, key, value FROM project_memory "
            "WHERE workspace_id = ? ORDER BY confidence DESC, last_used DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
        if not rows:
            return ""
        ids = [r["id"] for r in rows]
        db.execute(
            f"UPDATE project_memory SET last_used = datetime('now') "
            f"WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        db.commit()
    finally:
        db.close()

    lines = [f"- ({r['memory_type']}) {r['key']}: {r['value']}" for r in rows]
    return "Known context from this workspace:\n" + "\n".join(lines)
