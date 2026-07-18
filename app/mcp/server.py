"""The engine as an MCP **server** — read tools over Streamable HTTP (JSON-RPC 2.0).

``handle_message`` is transport-agnostic (the FastAPI route in ``app/api/routes.py`` is a
thin shell), tenant-scoped (every tool runs against the caller's isolated engine), and
strictly read-only: `sql_query` goes through the same NL→SQL→sqlglot-validation chokepoint
as the chat pipeline — an MCP caller can never write to or escape the tenant's data.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

log = logging.getLogger("aba.mcp")

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "multisource-assistant", "version": "0.1.0"}
INSTRUCTIONS = (
    "Read-only tools over this tenant's knowledge base: hybrid document search, "
    "validated SQL over the business database, and a source inventory. Every result "
    "carries provenance (document/page or table/rows)."
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_documents",
        "description": "Search the tenant's uploaded documents (PDFs) with hybrid dense + "
                       "keyword retrieval. Returns the most relevant passages with "
                       "document/page provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to find in the documents."},
                "documents": {"type": "array", "items": {"type": "string"},
                              "description": "Optional list of document names to restrict to."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "sql_query",
        "description": "Ask the tenant's business database a question in natural language. "
                       "SQL is generated, validated read-only (SELECT-only, allow-listed "
                       "tables, row-limited), executed, and returned with the SQL used.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string",
                             "description": "Natural-language description of what to fetch."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "list_sources",
        "description": "List everything indexed for this tenant: documents (with chunk "
                       "counts) and database tables (with row counts).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _result(id_: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _text_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle_message(payload: Any, user_id: str) -> Optional[dict]:
    """Process one JSON-RPC message. Returns the response object, or None for a
    notification (the HTTP layer answers 202)."""
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request: expected a JSON-RPC 2.0 object.")
    method = payload.get("method")
    id_ = payload.get("id")
    if id_ is None:  # notification (e.g. notifications/initialized) — no response body
        return None
    params = payload.get("params") or {}

    try:
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if requested in SUPPORTED_VERSIONS else PROTOCOL_VERSION
            return _result(id_, {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
                "instructions": INSTRUCTIONS,
            })
        if method == "ping":
            return _result(id_, {})
        if method == "tools/list":
            return _result(id_, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name") or ""
            arguments = params.get("arguments") or {}
            if name not in {t["name"] for t in TOOLS}:
                return _error(id_, -32602, f"Unknown tool '{name}'.")
            return _result(id_, _call_tool(name, arguments, user_id))
        return _error(id_, -32601, f"Method '{method}' not found.")
    except Exception as exc:  # noqa: BLE001 — protocol errors, never stack traces
        log.exception("mcp %s failed", method)
        return _error(id_, -32603, f"Internal error: {exc}")


# --------------------------------------------------------------------------- #
# Tool implementations (tenant-scoped, read-only)
# --------------------------------------------------------------------------- #
def _call_tool(name: str, arguments: dict, user_id: str) -> dict:
    from app.engine import get_engine
    eng = get_engine(user_id)

    if name == "search_documents":
        query = (arguments.get("query") or "").strip()
        if not query:
            return _text_result("The 'query' argument is required.", is_error=True)
        filters: dict = {}
        docs = arguments.get("documents")
        if isinstance(docs, list) and docs:
            filters["documents"] = [str(d) for d in docs]
        ev, _dtrace = eng.document_source.retrieve(query, filters=filters)
        if not ev:
            return _text_result("No relevant passages found in the documents.")
        passages = "\n\n".join(f"{e.citation_label}\n{e.content}" for e in ev)
        return _text_result(f"Found {len(ev)} passage(s):\n\n{passages}")

    if name == "sql_query":
        question = (arguments.get("question") or "").strip()
        if not question:
            return _text_result("The 'question' argument is required.", is_error=True)
        ev, strace, _call = eng.relational_source.run(question, purpose="mcp")
        if not strace.valid:
            return _text_result(f"SQL could not be run: {strace.validation_error}",
                                is_error=True)
        rows = "\n".join(e.content for e in ev) or "(no rows)"
        return _text_result(
            f"SQL: {strace.validated_sql or strace.generated_sql}\n"
            f"Rows returned: {strace.row_count}\n\n{rows}"
        )

    # list_sources
    inv = eng.inventory()
    lines = [f"Documents ({len(inv.documents)}):"]
    for d in inv.documents:
        lines.append(f"- {d.name} ({d.origin}, {d.chunks_indexed} chunk(s), "
                     f"languages: {', '.join(d.languages) or 'n/a'})")
    lines.append(f"\nDatabases ({len(inv.databases)}):")
    for db in inv.databases:
        for t in db.tables:
            lines.append(f"- {t.name} ({t.rows} row(s); columns: {', '.join(t.columns)})")
    return _text_result("\n".join(lines))


def parse_body(raw: bytes) -> Any:
    """Parse the HTTP body; a JSON parse failure maps to the JSON-RPC -32700 error."""
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None
