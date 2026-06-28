"""Conversation history — turns a stored chat session into context the engine can use.

The answering pipeline is stateless per call; this module is the single place that
loads prior turns for a session and formats them into a compact block that the router
and the generator use ONLY to resolve references (pronouns, "the second one", "that
contract"). It is deliberately NOT a new evidence source — every factual claim must
still be grounded in retrieved evidence. See ``app/generation/generate.py``.
"""
from __future__ import annotations

from typing import Optional

from app.db.migrations import get_session_db

# How many of the most recent turns to carry, and a hard character cap so a long
# conversation can never blow up the prompt or leak the whole history into context.
_DEFAULT_MAX_TURNS = 12
_DEFAULT_MAX_CHARS = 4000


def load_history(session_id: Optional[str],
                 max_turns: int = _DEFAULT_MAX_TURNS) -> list[dict]:
    """Load the most recent ``max_turns`` messages for a session, oldest-first.

    Returns a list of ``{"role": "user"|"assistant", "content": str}`` dicts.
    Best-effort: any error (missing session, cold DB) yields an empty history so the
    caller simply behaves as a fresh, single-shot question.
    """
    if not session_id:
        return []
    db = get_session_db()
    try:
        # rowid is the tiebreaker: created_at has only second resolution, so two messages
        # saved in the same second must still order by insertion order.
        rows = db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (session_id, max_turns),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception:
        return []
    finally:
        db.close()


def format_history_block(history: Optional[list[dict]],
                         max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """Render conversation history as a compact transcript block, newest turns kept.

    Returns "" when there is no history. The block is trimmed from the front so the
    most recent (most relevant) turns survive the character cap.
    """
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        role = turn.get("role", "user")
        speaker = "User" if role == "user" else "Assistant"
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{speaker}: {content}")
    if not lines:
        return ""
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[-max_chars:]
        # don't start mid-line
        nl = block.find("\n")
        if nl != -1:
            block = block[nl + 1:]
    return block
