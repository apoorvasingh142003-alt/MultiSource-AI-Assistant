"""A minimal MCP **client** over Streamable HTTP (JSON-RPC 2.0).

Speaks to any spec-compliant server: initialize → notifications/initialized →
tools/list / tools/call. Handles both response styles the transport allows — a single
``application/json`` object and a ``text/event-stream`` that carries the JSON-RPC
response as SSE ``data:`` frames — and echoes the negotiated ``MCP-Protocol-Version``
and any ``Mcp-Session-Id`` the server assigns.

The HTTP transport is injectable (``transport(url, data, headers) -> (status, headers,
body)``) so tests can drive the client against our own in-process server with no sockets;
the default uses stdlib urllib.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

log = logging.getLogger("aba.mcp.client")

Transport = Callable[[str, bytes, dict], tuple[int, dict, bytes]]

_TIMEOUT_S = 15
_CLIENT_INFO = {"name": "multisource-assistant", "version": "0.1.0"}
_PROTOCOL_VERSION = "2025-06-18"


class MCPError(Exception):
    pass


def _urllib_transport(url: str, data: bytes, headers: dict) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read() or b""


class MCPClient:
    def __init__(self, url: str, auth_header: str | None = None,
                 transport: Optional[Transport] = None) -> None:
        self.url = url
        self.auth_header = (auth_header or "").strip()
        self.transport = transport or _urllib_transport
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self._id = 0

    # -- plumbing -----------------------------------------------------------
    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.auth_header:
            h["Authorization"] = self.auth_header
        if self.protocol_version:
            h["MCP-Protocol-Version"] = self.protocol_version
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload: dict) -> Optional[dict]:
        body = json.dumps(payload).encode("utf-8")
        try:
            status, headers, raw = self.transport(self.url, body, self._headers())
        except Exception as exc:  # network layer
            raise MCPError(f"Could not reach the MCP server: {exc}")
        if sid := _header(headers, "mcp-session-id"):
            self.session_id = sid
        if status == 202:  # accepted notification
            return None
        if status >= 400:
            raise MCPError(f"MCP server returned HTTP {status}.")
        ctype = (_header(headers, "content-type") or "").lower()
        if "text/event-stream" in ctype:
            msg = _parse_sse(raw, payload.get("id"))
        else:
            try:
                msg = json.loads(raw.decode("utf-8"))
            except Exception:
                raise MCPError("MCP server returned a non-JSON response.")
        if msg is None:
            raise MCPError("MCP server stream carried no response for the request.")
        if "error" in msg:
            err = msg["error"] or {}
            raise MCPError(f"MCP error {err.get('code')}: {err.get('message')}")
        return msg.get("result", {})

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        payload: dict = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        result = self._post(payload)
        return result or {}

    # -- protocol -----------------------------------------------------------
    def initialize(self) -> dict:
        result = self._request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        })
        self.protocol_version = result.get("protocolVersion") or _PROTOCOL_VERSION
        # best-effort initialized notification (some servers require it, ours doesn't)
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except MCPError:
            pass
        return result

    def list_tools(self) -> list[dict]:
        if self.protocol_version is None:
            self.initialize()
        return list(self._request("tools/list").get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict:
        """Returns the raw tool result: {"content": [...], "isError": bool}."""
        if self.protocol_version is None:
            self.initialize()
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    def call_tool_text(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """The tool result's text content, flattened (raises on isError)."""
        result = self.call_tool(name, arguments)
        text = "\n".join(
            c.get("text", "") for c in (result.get("content") or [])
            if c.get("type") == "text"
        ).strip()
        if result.get("isError"):
            raise MCPError(text or "The MCP tool reported an error.")
        return text


def _header(headers: dict, name: str) -> str | None:
    for k, v in (headers or {}).items():
        if str(k).lower() == name:
            return v
    return None


def _parse_sse(raw: bytes, want_id: Any) -> Optional[dict]:
    """Extract the JSON-RPC response for ``want_id`` from an SSE body."""
    fallback = None
    for frame in raw.decode("utf-8", errors="replace").split("\n\n"):
        data = "".join(
            line[5:].strip() for line in frame.split("\n") if line.startswith("data:")
        )
        if not data:
            continue
        try:
            msg = json.loads(data)
        except Exception:
            continue
        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
            if msg.get("id") == want_id:
                return msg
            fallback = fallback or msg
    return fallback
