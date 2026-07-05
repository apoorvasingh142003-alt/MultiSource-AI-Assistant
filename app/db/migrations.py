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
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    picture TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now'))
);

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

-- Messaging channels (Telegram now, WhatsApp later). A channel_link binds an external
-- chat/phone to a tenant; a channel_link_code is a short-lived one-time code a signed-in
-- user redeems from the channel to create that binding.
CREATE TABLE IF NOT EXISTS channel_links (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,                 -- 'telegram' | 'whatsapp'
    external_id TEXT NOT NULL,             -- telegram chat id / whatsapp phone
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(channel, external_id)
);

CREATE TABLE IF NOT EXISTS channel_link_codes (
    code TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- Per-user credentials for third-party integrations (HubSpot private-app token, etc.).
CREATE TABLE IF NOT EXISTS integration_tokens (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,               -- 'hubspot' | ...
    token TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, provider)
);
"""


def _db_path() -> Path:
    s = get_settings()
    state = s.state_path
    # Migrate a legacy sessions.db (older layout kept it directly under data/) into the
    # new persistent state/ dir on first run, so existing history isn't stranded.
    legacy = s.data_path / "sessions.db"
    target = state / "sessions.db"
    if legacy.exists() and not target.exists():
        try:
            state.mkdir(parents=True, exist_ok=True)
            for suffix in ("", "-wal", "-shm"):
                src = legacy.parent / f"sessions.db{suffix}"
                if src.exists():
                    target.with_name(f"sessions.db{suffix}").write_bytes(src.read_bytes())
        except Exception:
            pass
    return target


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
        # additive column migrations (safe/idempotent). Adding user_id here (rather than in
        # the CREATE TABLE) lets existing databases upgrade in place without a rebuild.
        for table, col, decl in (
            ("messages", "edited_at", "TEXT"),
            ("sessions", "user_id", "TEXT"),
            ("workspaces", "user_id", "TEXT"),
        ):
            try:
                cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except Exception:
                pass
        _seed_and_backfill_tenancy(conn)
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id, created_at)",
        ):
            try:
                conn.execute(stmt)
            except Exception:
                pass
        conn.commit()
        _initialized = True
    return conn


def _seed_and_backfill_tenancy(conn: sqlite3.Connection) -> None:
    """Ensure the default user exists and no user-owned row is left orphaned.

    When auth is disabled every request resolves to ``default_user_id`` (see app/auth.py),
    so all pre-existing sessions/workspaces are attributed to that user. Idempotent.
    """
    s = get_settings()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, name) VALUES (?, ?, ?)",
            (s.default_user_id, s.default_user_email, "Local User"),
        )
        conn.execute(
            "UPDATE sessions SET user_id = ? WHERE user_id IS NULL OR user_id = ''",
            (s.default_user_id,),
        )
        conn.execute(
            "UPDATE workspaces SET user_id = ? WHERE user_id IS NULL OR user_id = ''",
            (s.default_user_id,),
        )
    except Exception:
        pass


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    conn = get_session_db()
    try:
        conn.executescript(_SESSIONS_SCHEMA)
        conn.commit()
        log.info("Session DB initialized at %s", _db_path())
    finally:
        conn.close()
