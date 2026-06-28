# Implementation Plan — Nexus AI Enterprise Upgrade (Agentic Chat)

**Goal of this round:** turn a high-quality single-shot RAG engine into an enterprise,
ChatGPT-like **agentic, multi-turn, streaming** assistant — without regressing the
routing / retrieval / verification / explainability that already works.

**Branch:** `enterprise-upgrade`  ·  **Status:** implemented & verified (see `task.md`).

---

## 1. What changed and why

The previous build was a stateless Q→A engine: each `/ask` was independent, settings were
scattered across three unsynced places, evidence was truncated, the multilingual demo used
Hebrew, and there was a Demo tab. This round delivers a conversational product:

- **Two-way, multi-turn conversation** — follow-ups resolve references ("the first of those
  customers") because prior turns are threaded into routing + generation.
- **LangGraph iterative agent** — an optional agent that loops over tools (SQL → docs →
  answer), wrapping the *existing* sources so every trace/explainability panel still works.
- **Real token-by-token streaming** with live agent-step events.
- **Editable history** — edit / delete / regenerate any turn.
- **Applied temperature**, a **dedicated Settings panel**, a **single settings store**,
  a **merged Output control**, **untruncated evidence**, **German** multilingual showcase,
  and the **Demo tab + Response-Style panel removed**.

## 2. Architecture decisions

- **Hybrid LangChain adoption** (confirmed with the user): the conversational plumbing
  (history, streaming, edit/delete) is library-agnostic; **LangGraph** powers only the
  optional iterative agent, which wraps the existing pipeline as tools. The classic path is
  untouched and remains the offline/no-key fallback. The agent layer is **import-guarded** —
  if `langgraph`/`langchain-openai` are missing or there's no live LLM, the engine silently
  uses the classic path.
- **Additive, not destructive.** New request fields (`temperature`, `agent_mode`,
  `conversation_history`), a new `Trace.agent_trace`, and new SSE events
  (`agent_step` / `agent_observation`) are all additive — existing consumers keep working.
- **Determinism preserved.** Temperature applies to *final generation only*; routing and
  SQL stay at temperature 0, and the temperature-0 response cache is never invalidated
  (temperature is folded into the cache key only when non-zero).

## 3. Backend (app/)

| ID | Area | Key files |
|----|------|-----------|
| B1 | Per-request temperature threaded llm-client → generation | `llm/client.py`, `generation/generate.py`, `routing/orchestrator.py`, `engine.py`, `models.py` |
| B2 | Multi-turn conversation context (router + generator) | `conversation.py` (new), `routing/classify.py`, `generation/generate.py`, `engine.py` |
| B3 | Message edit / delete / regenerate endpoints | `api/routes.py`, `db/migrations.py` (`edited_at`) |
| B4 | Real token streaming (`stream_text`, `generate_answer_stream`); SSE rewrite | `llm/client.py`, `generation/generate.py`, `api/routes.py` |
| B5 | LangGraph iterative agent (tools / graph / runner) + `agent_trace` | `agent/{tools,graph,runner}.py` (new), `engine.py`, `models.py` |
| B6 | Structure-aware semantic chunking (sentence-respecting, overlap) | `ingestion/pdf.py` |
| B7 | German replaces Hebrew; generic language detection; German sample doc | `ingestion/pdf.py`, `routing/classify.py`, `engine.py`, `scripts/make_pdfs.py`, `scripts/seed_data.py` |

**Streaming bridge:** `/ask/stream` runs `engine.ask` on a worker thread with an `on_token`
sink that pushes deltas onto an `asyncio.Queue`; agent steps go through `on_event`. The
classic path streams real generation tokens; non-streaming paths (multi-agent, offline) fall
back to progressive word delivery so the UI is never blank.

## 4. Frontend (ui/)

| ID | Area | Key files |
|----|------|-----------|
| F0 | Single settings store (source of truth, persisted) + `activeSessionId` persistence | `components/AiSettingsPanel.tsx`, `app/page.tsx` |
| F1 | Remove Demo tab + Response-Style (RoleSelector) panel | deleted `Demo.tsx`, `RoleSelector.tsx`; `page.tsx` |
| F2 | Chat tab + threaded conversation (streaming, agent steps, edit/delete/regenerate) | `components/ChatThread.tsx` (new), `app/page.tsx`, slimmed `Workspace.tsx` (sources only) |
| F3 | Merged Output control (presentation × format → one dropdown) | `AiSettingsPanel.tsx` (`OUTPUT_OPTIONS`, `resolveOutput`) |
| F4 | Settings modal with applied temperature slider | `components/SettingsPanel.tsx` (new), `page.tsx` |
| F5 | Untruncated evidence (full, scrollable) | `components/trace.tsx` |
| F6 | German labels, drop Hebrew RTL checks, agent-timeline panel, enterprise polish | `trace.tsx`, `AnswerPanel.tsx`, `Workspace.tsx` |
| F-API | `temperature`/`agent_mode`/`conversation_history`, new SSE events, message CRUD | `lib/api.ts`, `lib/types.ts` |

## 5. Verification (done)

- **Backend:** `pytest` → **56 passed, 10 skipped**. New `tests/test_chat_upgrade.py` covers
  temperature cache-key behaviour, history formatting/cap, message edit/delete/regenerate,
  and offline agent fallback.
- **Live E2E (TestClient + real key):** multi-turn follow-up resolves a cross-turn reference
  (Q1 lists overdue customers → Q2 "the first of those customers" answers from Acme's
  contract); agent mode answers a SQL+doc question with both tools and a populated trace;
  German contract retrieves and answers in German; SSE emits real token deltas + agent events.
- **Frontend:** `tsc --noEmit` clean, `next build` clean.

## 6. Deferred (explicitly, per user)

- API-key management + local-model switch UI (scaffolded as "coming soon" in Settings).
- Deeper retrieval/embedding-model evaluation (semantic chunking landed; bge-m3 retained).
