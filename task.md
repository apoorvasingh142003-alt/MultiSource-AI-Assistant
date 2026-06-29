# Nexus AI — Enterprise Upgrade Task Tracker

> Branch `enterprise-upgrade`. `[x]` = implemented & verified. Full reasoning in `IMPLEMENTATION_PLAN.md`.
> Suite: **56 passed, 10 skipped** · UI `tsc` + `next build` clean.

## Backend

### B1 — Per-request temperature
- [x] `temperature` threaded `structured`/`text` → `_run` → `_dispatch` → `_call_openai`/`_call_anthropic`
- [x] Folded into cache key only when non-zero (temp-0 cache preserved)
- [x] Threaded through `generate_answer`/`generate_general_knowledge` → orchestrator → engine → `AskRequest`
- [x] Routing + SQL stay deterministic (temperature 0)

### B2 — Multi-turn conversation
- [x] `app/conversation.py`: `load_history` (rowid-ordered) + `format_history_block` (char cap, recent-first)
- [x] `AskRequest.conversation_history`; engine loads from `session_id` when omitted
- [x] History fed to `classify()` (reference-resolving routing) and `generate_answer` (context, not evidence)
- [x] Live-verified: "the first of those customers" resolves across turns

### B3 — Message edit / delete / regenerate
- [x] `PATCH /sessions/{sid}/messages/{mid}` (sets `edited_at`)
- [x] `DELETE /sessions/{sid}/messages/{mid}`
- [x] `POST /sessions/{sid}/messages/{mid}/regenerate` (rebuilds context, re-runs, overwrites)
- [x] `edited_at` column via idempotent migration; rowid tiebreaker for same-second ordering

### B4 — Real token streaming
- [x] `LLMClient.stream_text` (OpenAI/Anthropic native streaming; offline chunks cached/fallback text)
- [x] `generate_answer_stream` (prose mode; `[eN]` citations recovered post-hoc and verified)
- [x] `/ask/stream` rewritten: worker thread + `asyncio.Queue`; real token deltas; word fallback for non-streaming paths
- [x] Verified: 340 token deltas on a document answer

### B5 — LangGraph iterative agent
- [x] `app/agent/tools.py` — `sql_query` / `search_documents` wrap existing sources; shared `AgentRunContext`
- [x] `app/agent/graph.py` — `StateGraph` agent⇄tools loop (ChatOpenAI + bind_tools, recursion cap)
- [x] `app/agent/runner.py` — runs the graph, rebuilds the standard `Trace`, runs existing verify/contributions/contradiction/risk
- [x] `Trace.agent_trace` (additive); `agent_mode` toggle; import-guarded `agent_available()`
- [x] SSE `agent_step` / `agent_observation` events; graceful offline fallback to classic path
- [x] Verified: HYBRID question uses both tools, 6 evidence, populated Inspector/Explainability

### B6 — Semantic chunking
- [x] Sentence-respecting, structure-aware chunking (~900 chars, 180 overlap) replacing fixed window; deterministic ids
- [x] Hard-window fallback only for pathologically long sentences

### B7 — German replaces Hebrew
- [x] Generic `detect_language` (German vs English); RTL repair retired
- [x] Router detects German (`["de"]`), German contract vocabulary; example + tests updated
- [x] German sample contract (`TABOR_Vertrag_DE.pdf`) + reseeded DB; Hebrew files removed
- [x] Verified: German question routes PDF, retrieves German contract, answers in German

## Frontend

### F-API — client + types
- [x] `AskOptions` with `temperature` / `agent_mode` / `conversation_history`
- [x] `askStream` handles `agent_step` / `agent_observation`; `AbortSignal` support
- [x] `editMessage` / `deleteMessage` / `regenerateMessage`; `Message.edited_at`; `AgentTrace` types

### F0 — State lifecycle
- [x] Single settings store (`useAiSettings`) — one localStorage key, single source of truth
- [x] `activeSessionId` persisted; conversation restored on reload
- [x] Consistent loading / streaming / empty / error states

### F1 — Removals
- [x] Demo tab deleted (tab + render + component)
- [x] Response-Style (RoleSelector) panel deleted — role lives only in AI Settings

### F2 — Chat experience
- [x] `Chat` tab (default) with threaded conversation (`ChatThread.tsx`)
- [x] Token streaming render + live agent-step panel
- [x] Per-turn edit / delete / regenerate / copy; ChatGPT-style composer (Enter to send)
- [x] Workspace slimmed to sources-only (uploads + inventory)

### F3 — Merged Output control
- [x] One `Output` dropdown (`OUTPUT_OPTIONS` → `{output_mode, output_format}`); overlaps deduped

### F4 — Settings panel
- [x] Settings modal: applied temperature slider (0–1, labelled), theme, default role/output, reasoning toggles
- [x] API-key / local-model sections scaffolded as "coming soon" (deferred)

### F5 — Evidence
- [x] Full evidence text (scrollable, never truncated); section names full-on-hover

### F6 — German + polish
- [x] German language labels; Hebrew RTL checks dropped; agent-timeline panel on completed answers
- [x] Settings/agent/temperature badges in the top bar + composer

## Constraints & tests
- [x] Additive request/trace fields + SSE events; classic path unchanged
- [x] Idempotent migration (`edited_at`); rowid ordering tiebreaker
- [x] Agent deps import-guarded; offline path needs no LangChain
- [x] `tests/test_chat_upgrade.py` (temperature, history, message CRUD, agent fallback)
- [x] Full suite **56 passed / 10 skipped**; UI `tsc` + `next build` clean
