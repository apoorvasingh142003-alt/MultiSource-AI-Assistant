"""Workflow automation (Section 11) — manual + scheduled multi-step pipelines.

Each workflow is a list of steps; running it generates one artifact per step. A small
asyncio-based scheduler (no external dependency) wakes once a minute and runs any
``scheduled`` workflow whose 5-field cron expression matches the current minute. Manual
workflows are run on demand via the API.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from app.artifacts import generate_artifact_core
from app.db.migrations import get_session_db

log = logging.getLogger("aba.workflow")

_scheduler_task: asyncio.Task | None = None


# --------------------------------------------------------------------------- #
# Execution                                                                    #
# --------------------------------------------------------------------------- #
def execute_workflow(workspace_id: str, workflow_id: str) -> dict:
    """Run a workflow's steps sequentially, generating an artifact per step. Updates the
    workflow's status (running → idle/error) and last_run. Returns a small summary."""
    db = get_session_db()
    try:
        row = db.execute(
            "SELECT * FROM workflows WHERE id = ? AND workspace_id = ?",
            (workflow_id, workspace_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Workflow not found"}
        steps = json.loads(row["steps"] or "[]")
        db.execute(
            "UPDATE workflows SET status = 'running', last_run = datetime('now') WHERE id = ?",
            (workflow_id,),
        )
        db.commit()
    finally:
        db.close()

    status = "idle"
    produced = 0
    try:
        for step in steps:
            generate_artifact_core(
                workspace_id,
                step.get("question", ""),
                step.get("artifact_type", "summary"),
                step.get("output_to") or step.get("question", "")[:50] or "Result",
            )
            produced += 1
    except Exception:
        log.exception("workflow %s failed", workflow_id)
        status = "error"

    db = get_session_db()
    try:
        db.execute("UPDATE workflows SET status = ? WHERE id = ?", (status, workflow_id))
        db.commit()
    finally:
        db.close()
    return {"ok": status != "error", "steps_run": produced, "status": status}


# --------------------------------------------------------------------------- #
# Minimal 5-field cron matcher (min hour day-of-month month day-of-week)        #
# --------------------------------------------------------------------------- #
def _field_match(expr: str, value: int, lo: int, hi: int) -> bool:
    expr = expr.strip()
    if expr == "*":
        return True
    for part in expr.split(","):
        step = 1
        body = part
        if "/" in part:
            body, _, step_s = part.partition("/")
            step = int(step_s) if step_s.isdigit() else 1
        if body in ("*", ""):
            start, end = lo, hi
        elif "-" in body:
            a, _, b = body.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(body)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def cron_matches(cron: str, now: datetime) -> bool:
    """True if a 5-field cron expression matches ``now`` (to the minute)."""
    parts = (cron or "").split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    return (
        _field_match(minute, now.minute, 0, 59)
        and _field_match(hour, now.hour, 0, 23)
        and _field_match(dom, now.day, 1, 31)
        and _field_match(month, now.month, 1, 12)
        and _field_match(dow, now.weekday() + 1 if now.weekday() != 6 else 0, 0, 6)
    )


# --------------------------------------------------------------------------- #
# Scheduler                                                                     #
# --------------------------------------------------------------------------- #
def _due_scheduled_workflows(now: datetime) -> list[tuple[str, str]]:
    """Return (workspace_id, workflow_id) for scheduled, idle workflows whose cron is due."""
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT id, workspace_id, schedule_cron, status FROM workflows "
            "WHERE trigger_type = 'scheduled' AND schedule_cron IS NOT NULL"
        ).fetchall()
    finally:
        db.close()
    due = []
    for r in rows:
        if r["status"] == "running":
            continue
        if cron_matches(r["schedule_cron"], now):
            due.append((r["workspace_id"], r["id"]))
    return due


async def _scheduler_loop() -> None:
    """Wake each minute and run any due scheduled workflows (off the event loop thread)."""
    log.info("workflow scheduler started")
    last_minute = None
    while True:
        try:
            now = datetime.now()
            minute_key = now.strftime("%Y-%m-%d %H:%M")
            if minute_key != last_minute:
                last_minute = minute_key
                for ws_id, wf_id in _due_scheduled_workflows(now):
                    log.info("scheduler firing workflow %s", wf_id)
                    await asyncio.to_thread(execute_workflow, ws_id, wf_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(20)


def start_scheduler() -> None:
    """Start the background scheduler task (idempotent). Called from FastAPI startup."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
        _scheduler_task = loop.create_task(_scheduler_loop())
    except RuntimeError:
        log.warning("no running event loop — scheduler not started")
