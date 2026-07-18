# Phase 6 plan — Actions & integrations (n8n, MCP, code-exec)

Roadmap: [03-ROADMAP.md](../03-ROADMAP.md) Phase 6 · Backlog: [04-BACKLOG.md](../04-BACKLOG.md)

## Exit criteria being satisfied

> A support-assistant demo answers from docs, **escalates when unsure**, and **writes a
> lead to a CRM via n8n** — end to end. Plus: MCP **server** exposing the engine's read
> tools; MCP **client** consuming an external MCP server; sandboxed **code execution**
> gated to analysis intents, shown in the panel.

Deliberately deferred (per the roadmap's own "last, demand-driven" note): **Google Drive
connector** and **live WhatsApp validation** (the channel code exists; validating the Meta
Cloud webhook needs real Meta credentials + a business number — a client-driven task).

## Design (wall-safe by construction)

### 1. Action-tool framework (`app/actions/`) — the read→act upgrade

The engine *reads/reasons*; **n8n acts**. Three built-in action tools whose implementation
POSTs to a per-tenant n8n webhook: `create_lead` (CRM write), `escalate` (human handoff),
`create_invoice` (vertical write). The client owns the n8n workflow; we own the tool contract.

**Propose → confirm → execute.** An action NEVER fires from a chat message alone:

- `app/actions/detect.py` — deterministic, word-bounded cues classify a message as an
  *action command* ("create a lead for Jane Smith (jane@acme.com) at Acme", "escalate this
  to a human", "raise an invoice for ACME for $1,200") and extract params (email/name/
  company/amount regexes). Must NOT fire on the demo suite ("total outstanding **invoice**
  amount" has no create-verb → safe).
- A pure action command short-circuits retrieval: `Engine.ask` returns a deterministic
  procedural acknowledgment + `AskResponse.actions=[ProposedAction]` (`origin="command"`,
  `action_only=True`). The UI renders an **ActionCard** — editable params, an explicit
  "sends to your n8n workflow" label, and a **Confirm** button. Nothing is sent until
  confirm (`POST /actions/execute`).
- **Escalate when unsure:** in `Engine._finalize`, an `insufficient` answer additionally
  carries a *suggested* `escalate` proposal (`origin="suggested"`) — the honest decline
  stays the honest decline (chip + label unchanged), with a one-click human handoff under it.
- Dispatch (`app/actions/service.py`): POST JSON `{action, params, user_id, session_id,
  requested_at}` to the configured webhook (stdlib urllib, 10 s timeout), optional
  `X-ABA-Signature` HMAC-SHA256 header from a per-action secret. **No webhook configured →
  status `simulated`** (recorded in `action_log`, demo-able fully offline). Never raises.
- Per-tenant config in `sessions.db`: `action_configs` (webhook_url + secret **encrypted at
  rest** via `app/crypto.py`), `action_log` (audit). Endpoints: `GET /actions`,
  `POST /actions/config`, `POST /actions/execute`, `GET /actions/log`.

**The wall:** an action turn makes no knowledge claims — the ack is procedural, cites
nothing, and the UI suppresses the tri-state chip for `action_only` turns (the ActionCard
is its own clearly-labeled surface: an external write, not an answer). Grounded / reasoned /
insufficient labeling of real answers is untouched; a suggested escalation never upgrades
an insufficient answer's label.

### 2. MCP server (`app/mcp/server.py` + `POST /api/mcp`)

Expose the engine as an MCP server (Streamable HTTP, JSON-RPC 2.0) — **hand-rolled, no new
dependency** (the `mcp` SDK isn't in the image; the server side of the protocol is small and
a stdlib implementation keeps offline determinism + hermetic tests). Methods: `initialize`,
`ping`, `tools/list`, `tools/call`; notifications → HTTP 202. Single JSON responses
(spec-legal for a stateless server). Tools, per-tenant via the same `CurrentUser` auth:

- `search_documents(query, documents?)` — hybrid retrieval → cited passages.
- `sql_query(question)` — NL → generated SQL → **sqlglot-validated read-only** → rows.
- `list_sources()` — inventory summary.

Advertised in the UI (Sources tab) as `<origin>/api/mcp` so Claude Desktop / other agents
can consume the tenant's knowledge base.

### 3. MCP client (`app/mcp/client.py` + registry)

Minimal Streamable-HTTP MCP client (initialize / tools/list / tools/call; parses both
`application/json` and `text/event-stream` responses; injectable transport for tests).
Per-tenant registry of external MCP servers (`mcp_servers` table, auth header encrypted).
Endpoints: `GET/POST/DELETE /mcp/servers`, `GET /mcp/servers/{id}/tools`,
`POST /mcp/servers/{id}/call`. The LangGraph agent (agent mode, live-LLM only) picks up a
tenant's registered MCP tools as extra LangChain tools — the "consume one external MCP
server" criterion; verified in tests by self-consuming our own `/mcp` endpoint over an
in-process transport.

### 4. Sandboxed code execution (`app/code_exec.py`)

Gated, deterministic, visible:

- **Gate:** `detect_compute_intent()` — statistical cues (mean/average, median, std,
  variance, percentile, correlation, growth rate, CAGR, percent change) AND a **grounded**
  answer with SQL rows in the trace. Reasoned/insufficient answers never run code.
- **Codegen:** deterministic script over the retrieved rows' numeric columns (count / sum /
  mean / median / stdev / min / max). No LLM required → offline/CI identical.
- **Sandbox:** AST-validated (imports only `math`/`statistics`/`json`; no dunder access;
  whitelisted builtins) then executed in a `python -I -S` subprocess with rlimits
  (CPU 2 s, 512 MB AS, 1 MB FSIZE) and a hard 5 s wall-clock kill. Rows go in via stdin
  JSON; results come out as stdout JSON.
- **Surface:** `Trace.code_execution = {code, stdout, ok, duration_ms}` renders as a
  "Sandboxed computation" panel in the inspector Trace tab; the answer gains a clearly
  labeled "Computed from the cited rows (sandboxed)" block. Derived from grounded rows →
  stays grounded; the block is additive, never a new unlabeled stream.

## Changes

### Backend
1. `app/db/migrations.py` — `action_configs`, `action_log`, `mcp_servers` tables (additive).
2. `app/actions/` — `catalog.py` (tool contracts), `detect.py` (cues + param extraction),
   `service.py` (config store, dispatch, log).
3. `app/models.py` — `ProposedAction`, `ActionResult`; `AskResponse.actions` +
   `AskResponse.action_only`; `Trace.actions`, `Trace.code_execution` (all additive).
4. `app/engine.py` — action-command short-circuit; `_finalize` gains escalate-on-
   insufficient suggestion + gated code-exec step.
5. `app/mcp/` — `server.py` (JSON-RPC handler + tools), `client.py`, `registry.py`.
6. `app/agent/runner.py` / `tools.py` — optional extra MCP tools (guarded, live-only).
7. `app/api/routes.py` — `/actions*`, `/mcp`, `/mcp/servers*` sections.
8. `app/code_exec.py` — gate, codegen, AST validation, subprocess sandbox.

### Frontend
9. `ui/lib/types.ts` + `ui/lib/api.ts` — new types + endpoints.
10. `ui/components/ActionCard.tsx` — proposed/suggested/executed/simulated/error states,
    editable params, Confirm; distinct "external write" identity (violet), never the
    tri-state palette.
11. `ui/components/ChatThread.tsx` — render `resp.actions`; suppress tri-state chip on
    `action_only` turns.
12. `ui/components/Workspace.tsx` (Sources tab) — "Actions & automations" config section
    (per-action webhook + enable), MCP server address + external MCP servers manager.
13. `ui/components/Inspector.tsx` — Actions panel + Sandboxed-computation panel in Trace tab.

### Eval & tests
14. `scripts/eval.py` — Phase-6 block (offline): action command → proposal only (nothing
    dispatched); demo suite never trips action detection; insufficient answer carries a
    suggested escalation and stays `insufficient`; execute without webhook → `simulated` +
    logged; MCP `tools/list`/`tools/call` grounded round-trip; compute question → sandboxed
    stats present on a grounded SQL answer.
15. `tests/test_actions.py`, `tests/test_mcp.py`, `tests/test_code_exec.py`.

## Status

- [x] Plan written
- [x] DB migrations + action framework (catalog / detect / service)
- [x] Engine wiring (command short-circuit, escalate-on-insufficient, code-exec)
- [x] MCP server + client + registry + agent wiring
- [x] Sandboxed code execution
- [x] API routes + UI (ActionCard, config UI in Sources tab, inspector Actions +
      Sandboxed-computation panels)
- [x] Tests + eval green offline — pytest 269 passed / 10 skipped (38 new Phase-6
      checks in `test_actions.py` / `test_mcp.py` / `test_code_exec.py`);
      `scripts/eval.py` **22/22 offline** (17 prior + 5 Phase-6)
- [x] tsc + next build green (via the /home clone workflow)
- [x] **Middleware fix shipped with this phase:** `ui/middleware.ts` no longer strips a
      client-supplied `Authorization` header when there is no Google session — the
      backend verifies the HS256 signature itself, and without pass-through the entire
      production MCP-server story (external clients on `/api/mcp`) was dead on arrival.
      The Google access token is still only ever set server-side from the session.
- [x] Live verification (2026-07-18), stack rebuilt + restarted, tunnel up:
      https://assistant.lazysnail.xyz loads (200) and `/api/health` is `ok`. Exercised
      the deployed system over the same HTTP flows the UI makes (auth ON, live LLM):
      * "Create a lead for Jane Smith (jane.smith@acme.com) at Acme Corp — …" →
        `action_only`, one `create_lead` proposal with name/email/company/note all
        extracted, nothing dispatched, no grounding chip semantics. Verified on both
        `/api/ask` and `/api/ask/stream` (the `done` event carries the proposal).
      * `/api/actions/execute` (no webhook configured) → `simulated` + visible in
        `/api/actions/log` (audit trail).
      * "What is our employee headcount in Berlin?" → honest `insufficient` decline
        PLUS a suggested `escalate` proposal (the wall label untouched).
      * `/api/mcp` through the tunnel with a bearer token: initialize (2025-06-18) →
        tools/list (3 tools) → tools/call `search_documents("service suspension")`
        returns cited contract passages.
      * "average and median invoice amount…" (live LLM) → `grounded`, sandboxed
        computation ran (`code_execution.ok`), labeled "Computed from the cited rows"
        block in the answer.
      * The deployed JS bundle serves the new surfaces (ActionCard "External action" +
        Sources-tab "Actions & automations" strings confirmed in the served chunk).
      Not verified live: a real n8n workflow receiving the webhook (no n8n instance on
      prod yet — covered by the HMAC-verified local-HTTP test in `test_actions.py`;
      going live is pasting the webhook URL in Sources → Actions & automations), and
      in-browser click-through (no browser in this environment — flows exercised at the
      HTTP layer the UI uses, bundle presence confirmed).
