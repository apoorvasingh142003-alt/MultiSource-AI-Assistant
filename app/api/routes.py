"""API routes: /health, /config, /examples, /sources, /roles, /inventory, /ask,
ingestion, sessions, workspaces, memory, workflows."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.artifacts import generate_artifact_core
from app.config import get_settings
from app.db.migrations import get_session_db
from app.engine import get_engine
from app.models import (AskRequest, AskResponse, ExampleQuestion, IngestResult,
                        Inventory, RouteDecision, SourceInfo, Trace)
from app.roles import list_roles
from app.workflow import execute_workflow

router = APIRouter()
log = logging.getLogger("aba.api")

_MAX_PDF_BYTES = 30 * 1024 * 1024      # 30 MB per PDF
_MAX_DB_BYTES = 100 * 1024 * 1024      # 100 MB per SQLite file
_SAFE_NAME = re.compile(r"[^0-9A-Za-z._-]+")


def _safe_filename(name: str, fallback: str) -> str:
    base = Path(name or "").name
    base = _SAFE_NAME.sub("_", base).strip("._") or fallback
    return base


@router.get("/health")
def health() -> dict:
    eng = get_engine()
    return {
        "status": "ok",
        "documents": len(eng.document_source.documents),
        "chunks": eng.document_source.index.n_chunks,
        "tables": eng.relational_source.schema.table_names(),
    }


@router.get("/config")
def config() -> dict:
    s = get_settings()
    eng = get_engine()
    return {
        "mode": "live" if s.use_live_llm else "offline",
        "provider": s.llm_provider,
        "models": {
            "generation": s.model_generation,
            "router": s.model_router,
            "sql": s.model_sql,
        },
        "embedding_backend": eng.document_source.index.embedder.backend,
        "vector_backend": eng.document_source.index.store.backend,
        "reranker_backend": (
            eng.document_source.index.reranker.backend
            if eng.document_source.index.reranker else "disabled"
        ),
        "has_api_key": s.has_api_key,
    }


@router.get("/examples", response_model=list[ExampleQuestion])
def examples() -> list[ExampleQuestion]:
    return get_engine().examples


@router.get("/sources", response_model=list[SourceInfo])
def sources() -> list[SourceInfo]:
    return get_engine().sources


@router.get("/roles")
def roles() -> list[dict]:
    """Get available roles for dynamic role adaptation."""
    return [
        {
            "name": role.name,
            "label": role.label,
            "description": role.description,
        }
        for role in list_roles()
    ]


@router.get("/inventory", response_model=Inventory)
def inventory() -> Inventory:
    return get_engine().inventory()


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(400, "Please enter a question.")
    try:
        resp = get_engine().ask(
            question, scope=req.scope, role=req.role, output_mode=req.output_mode,
            custom_system_prompt=req.custom_system_prompt,
            agent_role=req.agent_role,
            output_format=req.output_format,
            session_id=req.session_id,
            multi_agent=req.multi_agent,
        )
    except Exception:  # never leak a stack trace — fail gracefully and honestly
        log.exception("ask() failed for question=%r", question)
        return AskResponse(
            question=question,
            answer="We hit an unexpected error while processing this question. "
                   "Please try rephrasing it, or try again in a moment.",
            insufficient=True,
            citations=[],
            trace=Trace(
                question=question,
                route=RouteDecision(route="NONE", reasoning="Engine error.", confidence=0.0),
                notes=["The engine encountered an unexpected error; no answer was grounded."],
                mode="error",
            ),
        )

    # Persist the turn to chat history (Section 5.1). Best-effort: a persistence
    # failure must never break answering.
    if req.session_id:
        try:
            route = resp.trace.route.route if resp.trace.route else None
            confidence = resp.trace.route.confidence if resp.trace.route else None
            save_message(req.session_id, "user", question)
            save_message(req.session_id, "assistant", resp.answer, route, confidence)
        except Exception:
            log.exception("failed to persist chat turn for session=%s", req.session_id)
    return resp


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/ask/stream")
async def ask_stream(req: AskRequest) -> StreamingResponse:
    """Server-Sent Events variant of /ask (Section 12.3). Runs the full pipeline off the
    event loop, then streams the answer word-by-word followed by the complete payload."""
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(400, "Please enter a question.")

    async def gen():
        yield _sse("status", {"stage": "processing"})
        try:
            resp = await asyncio.to_thread(
                get_engine().ask, question,
                scope=req.scope, role=req.role, output_mode=req.output_mode,
                custom_system_prompt=req.custom_system_prompt, agent_role=req.agent_role,
                output_format=req.output_format, session_id=req.session_id,
                multi_agent=req.multi_agent,
            )
        except Exception:
            log.exception("ask_stream failed for question=%r", question)
            yield _sse("error", {"message": "Engine error while processing the question."})
            return

        if req.session_id:
            try:
                route = resp.trace.route.route if resp.trace.route else None
                conf = resp.trace.route.confidence if resp.trace.route else None
                save_message(req.session_id, "user", question)
                save_message(req.session_id, "assistant", resp.answer, route, conf)
            except Exception:
                log.exception("stream persist failed for session=%s", req.session_id)

        yield _sse("route", {"route": resp.trace.route.route if resp.trace.route else None})
        words = (resp.answer or "").split(" ")
        buf = ""
        for i, w in enumerate(words):
            buf += w + " "
            if i % 4 == 3:
                yield _sse("delta", {"text": buf})
                buf = ""
                await asyncio.sleep(0.015)
        if buf:
            yield _sse("delta", {"text": buf})
        yield _sse("done", json.loads(resp.model_dump_json()))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# -- ingestion ---------------------------------------------------------------

@router.post("/ingest/pdf", response_model=IngestResult)
async def ingest_pdf_endpoint(files: list[UploadFile] = File(...)) -> IngestResult:
    eng = get_engine()
    dest_dir = get_settings().data_path / "uploads" / "pdfs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, f in enumerate(files):
        name = _safe_filename(f.filename or "", f"upload_{i}.pdf")
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        data = await f.read()
        if len(data) > _MAX_PDF_BYTES:
            raise HTTPException(413, f"“{name}” exceeds the {_MAX_PDF_BYTES // (1024*1024)} MB per-file limit.")
        if not data:
            raise HTTPException(400, f"“{name}” is empty — nothing to ingest.")
        if data[:5] != b"%PDF-":
            raise HTTPException(400, f"“{name}” is not a valid PDF file.")
        dest = dest_dir / name
        dest.write_bytes(data)
        results.append(eng.add_pdf(name, dest))
    return IngestResult(
        ok=all(r.status == "indexed" for r in results),
        documents=results, inventory=eng.inventory(),
        message=f"Indexed {sum(r.chunks_indexed for r in results)} chunk(s) "
                f"from {len(results)} PDF(s).",
    )


@router.post("/ingest/sqlite", response_model=IngestResult)
async def ingest_sqlite_endpoint(files: list[UploadFile] = File(...)) -> IngestResult:
    eng = get_engine()
    dest_dir = get_settings().data_path / "uploads" / "db"
    dest_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, f in enumerate(files):
        name = _safe_filename(f.filename or "", f"upload_{i}.db")
        data = await f.read()
        if len(data) > _MAX_DB_BYTES:
            raise HTTPException(413, f"“{name}” exceeds the {_MAX_DB_BYTES // (1024*1024)} MB per-file limit.")
        if not data:
            raise HTTPException(400, f"“{name}” is empty — nothing to register.")
        if data[:16] != b"SQLite format 3\x00":
            raise HTTPException(400, f"Unsupported SQLite format — “{name}” is not a valid SQLite database.")
        dest = dest_dir / name
        dest.write_bytes(data)
        results.append(eng.add_database(name, dest))
    total_tables = sum(len(r.tables) for r in results)
    return IngestResult(
        ok=all(r.status == "indexed" for r in results),
        databases=results, inventory=eng.inventory(),
        message=f"Registered {total_tables} table(s) from {len(results)} database(s).",
    )


@router.post("/reset", response_model=Inventory)
def reset() -> Inventory:
    eng = get_engine()
    eng.reset()
    return eng.inventory()


# ==============================================================================
# Sessions (Section 5)
# ==============================================================================

@router.get("/sessions")
def list_sessions() -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT s.id, s.title, s.created_at, "
            "(SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count "
            "FROM sessions s ORDER BY s.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("/sessions", status_code=201)
def create_session() -> dict:
    sid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
        db.commit()
        row = db.execute("SELECT id, title, created_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        return {**dict(row), "message_count": 0}
    finally:
        db.close()


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str) -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT id, session_id, role, content, route, confidence, created_at "
            "FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    db = get_session_db()
    try:
        db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        db.commit()
        return {"ok": True}
    finally:
        db.close()


class SessionUpdate(BaseModel):
    title: str


@router.patch("/sessions/{session_id}")
def update_session(session_id: str, body: SessionUpdate) -> dict:
    db = get_session_db()
    try:
        db.execute("UPDATE sessions SET title = ? WHERE id = ?", (body.title, session_id))
        db.commit()
        row = db.execute("SELECT id, title, created_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        return {**dict(row), "message_count": 0}
    finally:
        db.close()


def save_message(
    session_id: str, role: str, content: str,
    route: str | None = None, confidence: float | None = None,
) -> None:
    """Auto-save a message to the session (called after /ask)."""
    db = get_session_db()
    try:
        # Ensure the session row exists (API clients may pass a session_id without
        # having created it first; the UI creates it via POST /sessions).
        db.execute("INSERT OR IGNORE INTO sessions (id) VALUES (?)", (session_id,))
        mid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO messages (id, session_id, role, content, route, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mid, session_id, role, content, route, confidence),
        )
        # Auto-generate session title from first user question
        if role == "user":
            existing_title = db.execute(
                "SELECT title FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing_title and not existing_title["title"]:
                title = content[:60].strip()
                db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        db.commit()
    finally:
        db.close()


# ==============================================================================
# Workspaces (Section 7)
# ==============================================================================

@router.get("/workspaces")
def list_workspaces() -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT w.id, w.name, w.description, w.created_at, "
            "(SELECT COUNT(*) FROM workspace_artifacts a WHERE a.workspace_id = w.id) AS artifact_count "
            "FROM workspaces w ORDER BY w.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""


@router.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceCreate) -> dict:
    wid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO workspaces (id, name, description) VALUES (?, ?, ?)",
            (wid, body.name, body.description),
        )
        db.commit()
        row = db.execute("SELECT * FROM workspaces WHERE id = ?", (wid,)).fetchone()
        return {**dict(row), "artifact_count": 0}
    finally:
        db.close()


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str) -> dict:
    db = get_session_db()
    try:
        db.execute("DELETE FROM workspace_artifacts WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM project_memory WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM workflows WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/workspaces/{workspace_id}/artifacts")
def list_artifacts(workspace_id: str) -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT * FROM workspace_artifacts WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}")
def get_artifact(workspace_id: str, artifact_id: str) -> dict:
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT * FROM workspace_artifacts WHERE id = ? AND workspace_id = ?",
            (artifact_id, workspace_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Artifact not found")
        return dict(row)
    finally:
        db.close()


class ArtifactGenerate(BaseModel):
    question: str
    artifact_type: str
    title: str


@router.post("/workspaces/{workspace_id}/generate", status_code=201)
def generate_artifact(workspace_id: str, body: ArtifactGenerate) -> dict:
    # Runs the full pipeline with the right output_format + per-type directive +
    # injected workspace memory, and persists the artifact (Sections 7.1 & 9.1).
    return generate_artifact_core(
        workspace_id, body.question, body.artifact_type, body.title
    )


@router.delete("/workspaces/{workspace_id}/artifacts/{artifact_id}")
def delete_artifact(workspace_id: str, artifact_id: str) -> dict:
    db = get_session_db()
    try:
        db.execute(
            "DELETE FROM workspace_artifacts WHERE id = ? AND workspace_id = ?",
            (artifact_id, workspace_id)
        )
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ==============================================================================
# Project Memory (Section 9)
# ==============================================================================

@router.get("/workspaces/{workspace_id}/memory")
def list_memory(workspace_id: str) -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT * FROM project_memory WHERE workspace_id = ? ORDER BY last_used DESC",
            (workspace_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


class MemoryCreate(BaseModel):
    memory_type: str = "fact"
    key: str
    value: str


@router.post("/workspaces/{workspace_id}/memory", status_code=201)
def add_memory(workspace_id: str, body: MemoryCreate) -> dict:
    mid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO project_memory (id, workspace_id, memory_type, key, value) "
            "VALUES (?, ?, ?, ?, ?)",
            (mid, workspace_id, body.memory_type, body.key, body.value),
        )
        db.commit()
        row = db.execute("SELECT * FROM project_memory WHERE id = ?", (mid,)).fetchone()
        return dict(row)
    finally:
        db.close()


@router.delete("/workspaces/{workspace_id}/memory/{memory_id}")
def delete_memory(workspace_id: str, memory_id: str) -> dict:
    db = get_session_db()
    try:
        db.execute(
            "DELETE FROM project_memory WHERE id = ? AND workspace_id = ?",
            (memory_id, workspace_id)
        )
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ==============================================================================
# Workflows (Section 11)
# ==============================================================================

class WorkflowCreate(BaseModel):
    name: str
    trigger_type: str = "manual"
    steps: list[dict] = []
    schedule_cron: str | None = None


@router.get("/workspaces/{workspace_id}/workflows")
def list_workflows(workspace_id: str) -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT * FROM workflows WHERE workspace_id = ? ORDER BY name",
            (workspace_id,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d.get("steps", "[]"))
            results.append(d)
        return results
    finally:
        db.close()


@router.post("/workspaces/{workspace_id}/workflows", status_code=201)
def create_workflow(workspace_id: str, body: WorkflowCreate) -> dict:
    wid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO workflows (id, workspace_id, name, trigger_type, schedule_cron, steps) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wid, workspace_id, body.name, body.trigger_type, body.schedule_cron,
             json.dumps(body.steps)),
        )
        db.commit()
        row = db.execute("SELECT * FROM workflows WHERE id = ?", (wid,)).fetchone()
        d = dict(row)
        d["steps"] = json.loads(d.get("steps", "[]"))
        return d
    finally:
        db.close()


@router.post("/workspaces/{workspace_id}/workflows/{workflow_id}/run")
def run_workflow(workspace_id: str, workflow_id: str) -> dict:
    result = execute_workflow(workspace_id, workflow_id)
    if not result.get("ok") and result.get("error") == "Workflow not found":
        raise HTTPException(404, "Workflow not found")
    return result
