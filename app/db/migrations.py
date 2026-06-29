"""Startup migrations — create new tables for sessions, workspaces, memory, and workflows.

Called once at startup; each CREATE TABLE uses IF NOT EXISTS so it's safe to run
multiple times. Uses a separate `sessions.db` to avoid polluting the business data.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.config import get_settings

log = logging.getLogger("aba.migrations")

_SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    route TEXT,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspace_artifacts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    source_question TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_memory (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL DEFAULT 'fact',
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    schedule_cron TEXT,
    steps TEXT NOT NULL DEFAULT '[]',
    last_run TEXT,
    status TEXT NOT NULL DEFAULT 'idle'
);
"""


def _db_path() -> Path:
    return get_settings().data_path / "sessions.db"


_initialized = False


def get_session_db() -> sqlite3.Connection:
    """Get a connection to the sessions/workspaces database.

    Lazily ensures the schema exists on first use, so the session/workspace endpoints
    work even if the FastAPI ``startup`` hook hasn't run (e.g. under a bare TestClient
    or a serverless cold start). Idempotent and cheap after the first call.
    """
    global _initialized
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if not _initialized:
        conn.executescript(_SESSIONS_SCHEMA)
        # additive column migrations (safe/idempotent)
        for table, col, decl in (("messages", "edited_at", "TEXT"),):
            try:
                cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except Exception:
                pass
        conn.commit()
        _initialized = True
    return conn


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    conn = get_session_db()
    try:
        conn.executescript(_SESSIONS_SCHEMA)
        conn.commit()
        log.info("Session DB initialized at %s", _db_path())
    finally:
        conn.close()
