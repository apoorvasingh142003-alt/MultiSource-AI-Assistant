"""Bridge a tenant's registered external MCP servers into the LangGraph agent.

Each remote tool becomes a LangChain ``StructuredTool`` (string-typed args built from the
tool's declared inputSchema) whose call is recorded in the agent's step timeline like any
other tool. Everything is guarded: an unreachable or misbehaving server contributes no
tools rather than breaking the agent, and observations are truncated. Remote results are
OBSERVATIONS for the model — they are not added to the evidence list, so they can never
be cited as grounded evidence (the wall: only our own retrieval mints citations).
"""
from __future__ import annotations

import logging
import re

from app.mcp.client import MCPClient, MCPError
from app.mcp.registry import get_server, list_servers

log = logging.getLogger("aba.mcp.agent")

_MAX_TOOLS_PER_SERVER = 8
_OBS_MAX = 4000
_NAME_SAFE = re.compile(r"[^0-9A-Za-z_-]+")


def make_mcp_tools(ctx, user_id: str) -> list:
    """LangChain tools for every tool on every MCP server this tenant registered."""
    try:
        from langchain_core.tools import StructuredTool  # noqa: F401
    except Exception:
        return []
    tools: list = []
    for entry in list_servers(user_id):
        server = get_server(user_id, entry["id"])
        if not server:
            continue
        client = MCPClient(server["url"], auth_header=server["auth_header"])
        try:
            remote = client.list_tools()
        except Exception as exc:  # noqa: BLE001 — a dead server must not kill the agent
            log.warning("MCP server %s unreachable: %s", server["name"], exc)
            continue
        for rt in remote[:_MAX_TOOLS_PER_SERVER]:
            try:
                tools.append(_wrap_tool(ctx, client, server["name"], rt))
            except Exception:
                log.exception("could not wrap MCP tool %s", rt.get("name"))
    return tools


def _wrap_tool(ctx, client: MCPClient, server_name: str, rt: dict):
    from langchain_core.tools import StructuredTool
    from pydantic import Field, create_model

    tool_name = rt.get("name") or "tool"
    safe_server = _NAME_SAFE.sub("_", server_name.lower()).strip("_") or "mcp"
    safe_tool = _NAME_SAFE.sub("_", tool_name)
    lc_name = f"mcp_{safe_server}_{safe_tool}"[:64]

    schema = rt.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: dict = {}
    for pname, pdef in list(props.items())[:8]:
        desc = (pdef or {}).get("description", "")
        if pname in required:
            fields[pname] = (str, Field(description=desc))
        else:
            fields[pname] = (str, Field(default="", description=desc))
    args_model = create_model(f"{lc_name}_args", **fields) if fields else None

    def _call(**kwargs) -> str:
        arguments = {k: v for k, v in kwargs.items() if str(v).strip()}
        try:
            obs = client.call_tool_text(tool_name, arguments) or "(empty result)"
        except MCPError as exc:
            obs = f"MCP tool error: {exc}"
        obs = obs[:_OBS_MAX]
        ctx.steps.append({
            "iteration": len(ctx.steps) + 1, "tool": lc_name,
            "args": arguments, "observation": obs[:600], "evidence_ids": [],
        })
        return obs

    description = (
        f"[External MCP tool from '{server_name}'] {rt.get('description') or tool_name}. "
        "Results are third-party observations — do not cite them with [eN] ids."
    )
    return StructuredTool.from_function(
        _call, name=lc_name, description=description, args_schema=args_model,
    )
