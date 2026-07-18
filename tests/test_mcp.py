"""MCP layer (Phase 6) — the engine as an MCP server + the MCP client/registry.

Server: JSON-RPC over the /mcp endpoint (initialize / ping / tools/list / tools/call,
notifications → 202, protocol errors as JSON-RPC errors), tenant-scoped and read-only.
Client: the minimal Streamable-HTTP client driven end-to-end against OUR OWN server via
an in-process transport (the "consume an external MCP server" flow with no sockets).
Registry: encrypted-at-rest auth headers + per-tenant isolation.

Run:  .venv/bin/python -m pytest tests/test_mcp.py -q
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.db.migrations as mig
from app.auth import User, get_current_user
from app.main import app
from app.mcp import registry
from app.mcp.client import MCPClient, MCPError
from app.mcp.server import handle_message


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "_db_path", lambda: tmp_path / "sessions.db")
    monkeypatch.setattr(mig, "_initialized", False, raising=False)
    mig.init_db()
    yield


@pytest.fixture
def client(state_db):
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Server (pure handler)
# --------------------------------------------------------------------------- #
def _rpc(method: str, params: dict | None = None, id_: int = 1) -> dict:
    msg: dict = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def test_initialize_negotiates_protocol_and_capabilities():
    res = handle_message(_rpc("initialize", {"protocolVersion": "2025-06-18"}), "default")
    r = res["result"]
    assert r["protocolVersion"] == "2025-06-18"
    assert r["serverInfo"]["name"] == "multisource-assistant"
    assert "tools" in r["capabilities"]
    # unknown requested version → we answer with our latest
    res2 = handle_message(_rpc("initialize", {"protocolVersion": "1999-01-01"}), "default")
    assert res2["result"]["protocolVersion"] == "2025-06-18"


def test_tools_list_and_notification_and_errors():
    tools = handle_message(_rpc("tools/list"), "default")["result"]["tools"]
    assert {t["name"] for t in tools} == {"search_documents", "sql_query", "list_sources"}
    assert all(t["inputSchema"]["type"] == "object" for t in tools)
    # a notification (no id) produces no response
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, "d") is None
    # protocol errors
    assert handle_message({"nope": 1}, "d")["error"]["code"] == -32600
    assert handle_message(_rpc("bogus/method"), "d")["error"]["code"] == -32601
    bad = handle_message(_rpc("tools/call", {"name": "rm_rf"}), "d")
    assert bad["error"]["code"] == -32602


def test_tools_call_search_documents_grounded():
    res = handle_message(_rpc("tools/call", {
        "name": "search_documents", "arguments": {"query": "service suspension"},
    }), "default")["result"]
    assert res["isError"] is False
    text = res["content"][0]["text"]
    assert "suspension" in text.lower() and ".pdf" in text


def test_tools_call_sql_query_read_only():
    res = handle_message(_rpc("tools/call", {
        "name": "sql_query",
        "arguments": {"question": "total outstanding invoice amount per customer"},
    }), "default")["result"]
    assert res["isError"] is False
    assert "SQL:" in res["content"][0]["text"]


def test_tools_call_list_sources_inventory():
    res = handle_message(_rpc("tools/call", {"name": "list_sources"}), "default")["result"]
    text = res["content"][0]["text"]
    assert "Documents" in text and "Databases" in text and "invoices" in text


# --------------------------------------------------------------------------- #
# HTTP endpoint
# --------------------------------------------------------------------------- #
def test_mcp_endpoint_roundtrip(client):
    r = client.post("/mcp", json=_rpc("tools/list"))
    assert r.status_code == 200
    assert {t["name"] for t in r.json()["result"]["tools"]} == {
        "search_documents", "sql_query", "list_sources"}
    # notification → 202, malformed body → -32700
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "x"}).status_code == 202
    bad = client.post("/mcp", content=b"{not json", headers={"Content-Type": "application/json"})
    assert bad.json()["error"]["code"] == -32700


def test_mcp_info_advertises_endpoint(client):
    info = client.get("/mcp/info").json()
    assert info["url"].endswith("/api/mcp") and info["transport"] == "streamable-http"
    assert len(info["tools"]) == 3


# --------------------------------------------------------------------------- #
# Client — self-consume our own server via an in-process transport
# --------------------------------------------------------------------------- #
def _asgi_transport(client: TestClient):
    def transport(url: str, data: bytes, headers: dict):
        resp = client.post("/mcp", content=data, headers=headers)
        return resp.status_code, dict(resp.headers), resp.content
    return transport


def test_client_end_to_end_against_own_server(client):
    mcp = MCPClient("http://in-process/mcp", transport=_asgi_transport(client))
    init = mcp.initialize()
    assert init["serverInfo"]["name"] == "multisource-assistant"
    assert mcp.protocol_version == "2025-06-18"
    tools = mcp.list_tools()
    assert {t["name"] for t in tools} == {"search_documents", "sql_query", "list_sources"}
    text = mcp.call_tool_text("search_documents", {"query": "service suspension"})
    assert "suspension" in text.lower()
    with pytest.raises(MCPError):
        mcp.call_tool("does_not_exist", {})


def test_client_parses_sse_response():
    def sse_transport(url, data, headers):
        req = json.loads(data)
        body = ("event: message\n"
                f'data: {json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": {"ok": True}})}'
                "\n\n").encode()
        return 200, {"Content-Type": "text/event-stream"}, body
    mcp = MCPClient("http://x/mcp", transport=sse_transport)
    mcp.protocol_version = "2025-06-18"  # skip initialize
    assert mcp._request("ping") == {"ok": True}


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_encrypts_auth_and_scopes_by_tenant(state_db):
    s = registry.add_server("u1", "QuickBooks", "https://qb.example/mcp", "Bearer tok-123")
    db = mig.get_session_db()
    try:
        row = db.execute("SELECT auth_header FROM mcp_servers WHERE id = ?", (s["id"],)).fetchone()
    finally:
        db.close()
    assert row["auth_header"].startswith("enc:v1:")
    assert registry.get_server("u1", s["id"])["auth_header"] == "Bearer tok-123"
    # tenant isolation
    assert registry.get_server("u2", s["id"]) is None
    assert registry.list_servers("u2") == []
    assert registry.remove_server("u2", s["id"]) is False
    assert registry.remove_server("u1", s["id"]) is True
    with pytest.raises(ValueError):
        registry.add_server("u1", "bad", "ftp://nope")


def test_registry_endpoints(client):
    app.dependency_overrides[get_current_user] = lambda: User(id="u1", email="u1@x.com")
    r = client.post("/mcp/servers", json={"name": "Self", "url": "https://self.example/mcp"})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert [s["id"] for s in client.get("/mcp/servers").json()] == [sid]
    assert client.delete(f"/mcp/servers/{sid}").json() == {"ok": True}
    assert client.delete(f"/mcp/servers/{sid}").status_code == 404


# --------------------------------------------------------------------------- #
# Agent bridge — graceful degradation
# --------------------------------------------------------------------------- #
def test_make_mcp_tools_skips_unreachable_servers(state_db):
    from app.agent.tools import AgentRunContext
    from app.mcp.agent_tools import make_mcp_tools
    registry.add_server("u9", "dead", "http://127.0.0.1:1/mcp")
    ctx = AgentRunContext(None, None, None)
    assert make_mcp_tools(ctx, "u9") == []


def test_wrapped_tool_records_step_and_never_mints_evidence(state_db, client):
    from app.agent.tools import AgentRunContext
    from app.mcp import agent_tools

    ctx = AgentRunContext(None, None, None)
    mcp = MCPClient("http://in-process/mcp", transport=_asgi_transport(client))
    tool = agent_tools._wrap_tool(ctx, mcp, "self", {
        "name": "search_documents",
        "description": "search",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"]},
    })
    obs = tool.func(query="service suspension")
    assert "suspension" in obs.lower()
    assert len(ctx.steps) == 1 and ctx.steps[0]["tool"].startswith("mcp_self_")
    assert ctx.steps[0]["evidence_ids"] == [] and ctx.evidence == []
