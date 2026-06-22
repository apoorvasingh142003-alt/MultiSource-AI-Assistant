"""Workspace artifact generation (Section 7) — shared by the API route and workflows.

Runs the full pipeline for an artifact request, applying the per-artifact-type directive
(Section 7.1) and this workspace's project memory (Section 9.1), then persists the result
as a ``workspace_artifacts`` row.
"""
from __future__ import annotations

import logging
import uuid

from app.db.migrations import get_session_db
from app.engine import get_engine
from app.memory import extract_and_store, get_memory_context

log = logging.getLogger("aba.artifacts")

# artifact_type → output_format (Section 7.1 ↔ Section 3.1)
_FORMAT_MAP: dict[str, str] = {
    "report": "prose", "ppt_content": "bullet_points", "table": "table",
    "json": "json", "summary": "executive_summary", "action_plan": "bullet_points",
}

# Per-artifact-type generation directives (Section 7.1), layered on the output format.
_ARTIFACT_DIRECTIVES: dict[str, str] = {
    "report": (
        "Produce a full structured report with these sections: Executive Summary; "
        "Findings (each with inline [eN] citations); Data Tables where useful; Conclusion."
    ),
    "ppt_content": (
        "Produce a slide-by-slide presentation outline. For each slide: 'Slide N — Title', "
        "3–5 concise bullet points, and a 'Speaker notes:' line."
    ),
    "action_plan": (
        "Produce a numbered action plan. Each item has: the action, an Owner placeholder, a "
        "Deadline placeholder, a Priority (High/Medium/Low), and the supporting [eN] citation."
    ),
    "summary": (
        "Produce an executive summary: one paragraph of key findings, then a 'Key Points' "
        "bulleted list, then a 'Recommended Actions' section."
    ),
}


def generate_artifact_core(
    workspace_id: str, question: str, artifact_type: str, title: str,
) -> dict:
    """Generate and persist one artifact; returns the stored row as a dict."""
    output_format = _FORMAT_MAP.get(artifact_type, "auto")
    directive = _ARTIFACT_DIRECTIVES.get(artifact_type)
    mem_context = get_memory_context(workspace_id)
    custom_prompt = "\n\n".join(p for p in (directive, mem_context) if p) or None

    try:
        resp = get_engine().ask(
            question, scope="all", output_format=output_format,
            custom_system_prompt=custom_prompt,
        )
        content = resp.answer
        try:
            extract_and_store(workspace_id, question, content)
        except Exception:
            log.exception("memory extraction failed for workspace=%s", workspace_id)
    except Exception:
        log.exception("artifact generation failed for workspace=%s", workspace_id)
        content = "Error generating artifact. Please try again."

    aid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content, source_question) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (aid, workspace_id, artifact_type, title, content, question),
        )
        db.commit()
        row = db.execute("SELECT * FROM workspace_artifacts WHERE id = ?", (aid,)).fetchone()
        return dict(row)
    finally:
        db.close()
