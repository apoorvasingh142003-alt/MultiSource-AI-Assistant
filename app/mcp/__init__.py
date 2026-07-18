"""MCP (Model Context Protocol) layer — Phase 6.

Two directions, both over MCP's Streamable HTTP transport (JSON-RPC 2.0):

- **Server** (`server.py`): the engine's READ tools (`search_documents`, `sql_query`,
  `list_sources`) exposed at ``POST /mcp`` so the client's other AI tools (Claude
  Desktop, their agents, n8n's MCP nodes) can query the tenant's knowledge base.
- **Client** (`client.py` + `registry.py`): consume a tenant's registered external MCP
  servers as extra tools (surfaced to the LangGraph agent and callable via the API).

Implemented on the stdlib (no ``mcp`` SDK dependency): the subset of the protocol we
speak — initialize / ping / tools/list / tools/call over single-JSON HTTP responses — is
small, spec-legal for a stateless server, and keeps the offline test suite hermetic.
"""
