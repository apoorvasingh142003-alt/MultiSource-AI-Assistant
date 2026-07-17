# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A multi-source retrieval & orchestration engine (not a PDF chatbot). It answers free-form
business questions by **routing** to the relevant source(s), retrieving from **PDF documents**
and a **SQLite database** (or both, agentically), producing a **grounded answer with verified
citations**, and exposing the **complete step-by-step trace**. FastAPI backend + Next.js
inspector frontend. English/Hebrew/German (bilingual, RTL-aware). Runs live (Claude / any
OpenAI-compatible endpoint) or fully **offline** with deterministic fallbacks.

The README describes the original single-tenant demo. The codebase has since grown auth +
multi-tenancy, a LangGraph agent path, chat sessions/workspaces/memory/workflows, external
channels (Telegram, WhatsApp), and integrations (Google Sheets, HubSpot). Treat this file as
the current map.

## Toolchain lives OUTSIDE the working tree (important)

The git working tree is `/mnt/c/Users/Apoor/MultiSource-AI-Assistant` (a Windows mount via
WSL) and has **no `.venv` and no `ui/node_modules`**. The installed toolchain is in a separate
clone at `/home/apoorv/MultiSource-AI-Assistant`:

- **Backend / tests:** run from the `/mnt/c` working dir using the `/home` venv:
  `/home/apoorv/MultiSource-AI-Assistant/.venv/bin/python`
  (cwd resolves `app/` correctly; `config.ROOT` points at the `/mnt/c` tree).
  Tests: `/home/apoorv/MultiSource-AI-Assistant/.venv/bin/python -m pytest -q`
- **Frontend typecheck/build:** the `/home` copy is a *stale clone* that does NOT reflect
  `/mnt/c` edits automatically. To typecheck/build, first sync:
  `rsync -a --delete --exclude node_modules --exclude .next /mnt/c/Users/Apoor/MultiSource-AI-Assistant/ui/ /home/apoorv/MultiSource-AI-Assistant/ui/`
  then inside `/home/.../ui`: `./node_modules/.bin/tsc --noEmit` and `./node_modules/.bin/next build`.
- Installing deps into `/mnt/c` directly is slow (Windows mount) — prefer the `/home` venv.

`make setup/seed/api/ui` assume a local `.venv`; on this machine substitute the `/home` venv
path above, or use Docker.

## Commands

```bash
# Full stack via Docker (UI :3000, API :8000; host API port overridable via ABA_API_HOST_PORT)
docker compose up --build

# Backend only (from /mnt/c working dir, /home venv)
/home/apoorv/MultiSource-AI-Assistant/.venv/bin/uvicorn app.main:app --reload --port 8000

# Seed the demo corpus (SQLite business.db + PDFs) — regenerable any time
<venv>/bin/python scripts/seed_data.py && <venv>/bin/python scripts/make_pdfs.py

# Frontend dev
cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev

# Tests (whole suite; hermetic — conftest forces auth OFF + offline embeddings)
<venv>/bin/python -m pytest -q
# Single test
<venv>/bin/python -m pytest tests/test_source_centric_routing.py -q
<venv>/bin/python -m pytest tests/test_tenancy.py::<name> -q

# Routing/retrieval eval across all demo questions (offline-safe; checks route + evidence + citations)
<venv>/bin/python -m scripts.eval

# Run the whole app on a local Ollama model
./scripts/local-model.sh    # or: make local

# Frontend lint
cd ui && npm run lint

# Bring up prod (app + permanent Cloudflare tunnel); ./scripts/stop.sh to tear down
./scripts/start.sh [--build] [--local]
```

There is no pytest config file — tests are discovered under `tests/`. `tests/conftest.py`
sets `ABA_AUTH_ENABLED=false` and offline/hashing defaults *before app import*, so the whole
suite runs deterministically without a key or auth.

## Architecture

### The pipeline (this is the product)
`app/routing/orchestrator.py` is the heart. One question flows:
**classify/route** (`app/routing/classify.py`: rules + LLM structured output → `PDF | SQL | HYBRID | NONE | GENERAL_KNOWLEDGE`, with an agentic flag) →
**per-source retrieval** →
**evidence aggregation** (normalized provenance) →
**grounded generation** (`app/generation/generate.py`) →
**citation verification** (`app/generation/verify.py`: every `[eN]` in the answer must trace to retrieved evidence).
Everything is recorded into a single `Trace` (`app/models.py`) that every UI panel renders.

- **Document branch** (`app/retrieval/`): dense embeddings + BM25 → RRF fusion (`fusion.py`) →
  optional cross-encoder rerank (`rerank.py`) → semantic keep-ratio gate. `document_retriever.py`
  owns the hybrid `DocumentIndex`; `vector_store.py` has numpy (default) + Qdrant backends.
- **PDF ingestion** (`app/ingestion/pdf.py` → `app/ingestion/parsers/`): pluggable parsers behind
  the stable `ingest_pdf`/`ingest_pdf_dir` API. `basic` (pypdf, always available, offline/CI
  default) and `docling` (robust tables/multi-column/OCR, optional heavy dep, import-guarded).
  `ABA_PDF_PARSER=auto|docling|basic`; Docling failures fall back to basic per-file. Every chunk
  carries a **parse-confidence** (0..1) that flows to `Evidence.parse_confidence` → `trust_factors`;
  a low-confidence *cited* passage adds a `verification_warning` + answer caveat but stays
  **grounded** (the tri-state wall is never blended). Tests force `basic` for determinism.
- **SQL branch** (`app/sql/`): `generate.py` (schema-aware LLM SQL) → `validate.py` (sqlglot AST,
  read-only, SELECT-only, allow-listed tables, LIMIT) → `execute.py`. The model never touches the DB directly.
- **HYBRID (agentic)**: SQL finds rows → entities extracted and linked to specific documents →
  document retrieval restricted to those documents → combined cited answer.

### Sources are the extension point
`app/sources/base.py` defines the `Source` interface (`describe()` + `retrieve()`). Concrete:
`document_source.py`, `relational_source.py`, and the stubbed `crm_source.py` (future). The
router builds its capability brief from `describe()` — adding a source is a new implementation,
not a pipeline change.

### Two generation paths, one Trace shape
Besides the classic orchestrator, `app/agent/` is a **LangGraph iterative agent** (tools:
`sql_query`, `search_documents`) used only when a live OpenAI-compatible LLM is configured
(`agent_available()`); `runner.py` reconstructs the *same* `Trace` (route, evidence, sql, doc
retrieval) and runs the same verification, so the UI is unchanged. `app/multi_agent.py`
decomposes multi-part questions into 2–4 sub-questions, runs the full pipeline per sub-question
concurrently, then synthesizes — exposing a `multi_agent_trace`.

### Engine, tenancy, and state
- `app/engine.py`: `Engine` wires sources + orchestrator. **One Engine per tenant** —
  `get_engine(user_id)` is an LRU cache of per-user engines. Startup ingests only the
  deterministic sample corpus; uploads mutate the live engine under a lock (PDF chunks appended
  to the index, uploaded SQLite tables merged into a working DB).
- `app/auth.py`: `get_current_user` dependency. `ABA_AUTH_ENABLED=false` (default) → every
  request is `default_user_id` (single-tenant/dev/CI). Enabled → verifies an HS256 identity JWT
  (minted by the Next.js Google auth layer) against `ABA_AUTH_SECRET`, using only the stdlib
  (no new backend dep).
- `app/db/migrations.py`: a **separate `sessions.db`** (users, sessions, messages, workspaces,
  memory, workflows) kept out of the business data. Business data + per-tenant mutable state live
  under `data/` (`data_path`, `state_path`, `uploads/<user_id>/`).
- `app/crypto.py`: **secrets encrypted at rest** (Fernet). Stored OAuth/provider tokens
  (`integration_tokens.token`, e.g. HubSpot) are encrypted before write / decrypted on read via
  `encrypt()`/`decrypt()`; the key derives from `ABA_ENCRYPTION_KEY` → `ABA_AUTH_SECRET` → a
  deterministic dev fallback (so offline/CI need no config). `decrypt()` is backward-compatible
  with legacy plaintext rows. New persisted secrets must go through this.
- `app/readiness.py` + `/health`: cold-start signal. `/health` **never 500s** — it reports
  `status: "warming"` (HTTP 200) until `main._warm()` finishes building the engine, then
  `status: "ok"` with the corpus summary. The UI shows a calm "warming up" banner meanwhile.

### Config
`app/config.py` — a single pydantic-settings `Settings` (env prefix `ABA_`, `.env` at repo root),
accessed via `get_settings()` (cached singleton, **intentionally mutable**). `app/runtime.py`
flips the live LLM between API and local Ollama at runtime by overwriting Settings fields in
place and resetting the LLM clients — no restart. `ANTHROPIC_API_KEY` is the only secret that
matters; without it the app runs offline. See `.env.example` for provider configs (Anthropic,
OpenAI, Groq, Gemini compat, Ollama).

### API & UI
- `app/api/routes.py`: all endpoints. Core: `/ask`, `/ask/stream`, `/examples`, `/sources`,
  `/inventory`, `/config`, `/health`, `/ingest/pdf`, `/ingest/sqlite`, `/runtime/model-mode`.
  Plus sessions, workspaces (+ artifacts/memory/workflows), and channel/integration webhooks
  (`/telegram/*`, `/whatsapp/*`, `/sheets/import`, `/hubspot/*`).
- `app/channels/` (telegram, whatsapp) and `app/integrations/` (google_sheets, hubspot) are
  per-tenant; inbound channel messages map to a tenant and run its isolated engine.
- `ui/` is Next.js (App Router). It proxies `/api/*` to the backend (`API_PROXY_TARGET`).
  **Phase-2 shell (ChatGPT-class):** `app/page.tsx` is a clean chat surface — `ChatSidebar`
  (threads) · centered `ChatThread` (slim messages: answer + clickable `[eN]` citations + a
  compact tri-state `AnswerStateChip` + source chips + Inspect/Copy/Regenerate) · `Composer`
  (📎 in-chat PDF upload → `/ingest/pdf`, plus a `CustomizePanel` popover for free-text role +
  instructions — the replacement for the removed 13-persona picker). The heavy trace/evidence
  lives in `InspectorPanel.tsx`, a right slide-in drawer with tabs **Answer · Trace · Evidence ·
  Sources** that reuses the rich renderers verbatim (`AnswerPanel.tsx`, `Inspector.tsx`,
  `trace.tsx`, `Workspace` rows). Streaming still uses the custom SSE transport in `lib/api.ts`
  (`askStream`); the final `done` event carries the full `Trace`. There are no top-nav tabs and
  no assistant-ui/Vercel-AI-SDK dependency (deliberate — see the Phase-2 plan).

## UI styling convention

`ui/` uses **semantic CSS-variable design tokens** + Tailwind `darkMode: class`. Style with the
token classes (`text-fg`, `bg-surface`, `border-line`, etc.) — **never raw slate/gray colors**.
See `ui/app/globals.css` and `ui/tailwind.config.ts` for the token set.

## Conventions worth matching

- **Grounding is the invariant.** Never let an answer cite evidence it didn't retrieve; the
  citation verifier enforces this. Ungrounded/general-knowledge answers get an explicit
  "not found in your sources" disclaimer (see `orchestrator.py`).
- **Offline determinism is a feature.** New LLM-touching code must degrade to a deterministic
  fallback so `scripts/eval.py` and the test suite pass with no key.
- **Additive tracing.** New reasoning paths reconstruct the existing `Trace` shape rather than
  inventing new UI contracts, so existing panels keep working.
- Auth-off + per-tenant isolation must both keep working: the default-user path backfills/owns
  all data when auth is disabled.
