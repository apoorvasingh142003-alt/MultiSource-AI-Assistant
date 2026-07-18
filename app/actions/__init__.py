"""Action-tool framework (Phase 6) — the read→act layer.

The engine *reads and reasons*; **n8n acts**. Each action here is a tool contract whose
implementation POSTs to a per-tenant n8n webhook (the client owns/edits the workflow,
no-code; we own the contract). Actions are always propose → confirm → execute: a chat
message can only ever *propose* an action, and nothing is dispatched until the user
confirms it explicitly (`POST /actions/execute`).
"""
