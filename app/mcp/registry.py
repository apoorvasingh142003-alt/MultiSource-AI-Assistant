"""Per-tenant registry of external MCP servers the assistant consumes as tools.

Mirrors the integration-token pattern: rows live in the state DB, the (optional) auth
header is encrypted at rest, and every read/write is scoped to the owning user.
"""
from __future__ import annotations

import uuid

from app.crypto import decrypt, encrypt
from app.db.migrations import get_session_db


def add_server(user_id: str, name: str, url: str, auth_header: str = "") -> dict:
    name = (name or "").strip() or "MCP server"
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("The MCP server URL must be an http(s) endpoint.")
    sid = str(uuid.uuid4())
    db = get_session_db()
    try:
        db.execute(
            "INSERT INTO mcp_servers (id, user_id, name, url, auth_header) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, user_id, name, url, encrypt((auth_header or "").strip())),
        )
        db.commit()
    finally:
        db.close()
    return {"id": sid, "name": name, "url": url, "has_auth": bool(auth_header.strip())}


def list_servers(user_id: str) -> list[dict]:
    db = get_session_db()
    try:
        rows = db.execute(
            "SELECT id, name, url, auth_header, created_at FROM mcp_servers "
            "WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()
        return [
            {"id": r["id"], "name": r["name"], "url": r["url"],
             "has_auth": bool(decrypt(r["auth_header"])), "created_at": r["created_at"]}
            for r in rows
        ]
    finally:
        db.close()


def get_server(user_id: str, server_id: str) -> dict | None:
    """Full record including the DECRYPTED auth header — server-side use only."""
    db = get_session_db()
    try:
        r = db.execute(
            "SELECT id, name, url, auth_header FROM mcp_servers "
            "WHERE id = ? AND user_id = ?",
            (server_id, user_id),
        ).fetchone()
    finally:
        db.close()
    if not r:
        return None
    return {"id": r["id"], "name": r["name"], "url": r["url"],
            "auth_header": decrypt(r["auth_header"]) or ""}


def remove_server(user_id: str, server_id: str) -> bool:
    db = get_session_db()
    try:
        cur = db.execute(
            "DELETE FROM mcp_servers WHERE id = ? AND user_id = ?",
            (server_id, user_id),
        )
        db.commit()
        return cur.rowcount > 0
    finally:
        db.close()
