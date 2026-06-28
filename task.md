# AI Business Assistant — Upgrade Task Tracker

> Status reflects an evidence-based audit of the existing code (2026-06-19), not assumptions.
> `[x]` = implemented & verified · `[ ]` = to do · 🟡 = partially there (see note).
> Full reasoning in `IMPLEMENTATION_PLAN.md`. Phases (P0–P9) give execution order.

## Phase 0 — Stabilize baseline ✅
- [x] Fix UI compile error: `Workspace.tsx:246` now destructures `aiSettings` / `onAiSettingsUpdate`
- [x] `npx tsc --noEmit` clean + `next build` clean (BUILD_EXIT=0)
- [x] Add `pytest`/`httpx` to `requirements-dev.txt`; backend suite green (34 pass / 10 skip)
- [x] Backend serves `/health` (9 docs, 65 chunks, 5 tables) + offline `/ask` round-trips (200)

## Section 0 — Critical Bug Fixes (GENERAL_KNOWLEDGE Route)
- [x] Add `GENERAL_KNOWLEDGE` to `Route` in `app/models.py` (models.py:14)
- [x] Secondary classifier NONE→GK in `classify.py` (classify.py:160-214)
- [x] Handle `GENERAL_KNOWLEDGE` in `orchestrator.py` (synthetic evidence, orchestrator.py:152-191)
- [x] GK generation in `generate.py` (generate.py:268-339)
- [x] Skip verification for GK (orchestrator.py:177-191)
- [x] UI types + blue chip badge for GK (VerificationBadge.tsx:20-26, AnswerPanel.tsx:66-71)

## Section 1 — Multi-Source & Multi-Purpose Routing
- [x] Domain-agnostic router prompt (classify.py:42-82)
- [x] Dynamic `describe()` in sources (document_source.py:19-48, relational_source.py:47-75)

## Section 2 — Custom Prompt & Role Injection
- [x] `custom_system_prompt`, `agent_role` on request (models.py:181-182)
- [x] Generation handles custom prompts, grounding preserved (generate.py:105-145)
- [x] `AiSettingsPanel.tsx` (role presets, 500-char counter, format, localStorage, multi-agent toggle)
- [x] Pass `agent_role` to router so it can bias routing (`classify(..., agent_role=)`) (P8)

## Section 3 — Structured Output Formatting
- [x] `output_format` on request + all 7 directives injected (generate.py:78-102)
- [x] `tableParser.ts`
- [x] `AnswerTable.tsx` (sortable, pagination >10, CSV export, copy, timeline accent)
- [x] Table rendering wired into `AnswerPanel`

## Section 4 — Read Aloud
- [x] `ReadAloud.tsx` core (play/pause/stop, speed, voice, strip citations)
- [x] Boundary tracking → live "now reading" sentence caption (P7) — in-answer inline highlight remains a 🟡 nice-to-have
- [x] Voice list filtered by detected language (EN/HE) (P7)
- [x] Unsupported-browser tooltip (disabled button + title) (P7)

## Section 5 — Chat History
- [x] `migrations.py` with sessions/messages tables (migrations.py:17-31)
- [x] Session API endpoints (GET/POST/DELETE/PATCH + messages)
- [x] `ChatSidebar.tsx` (collapsible, grouped, search, rename/delete)
- [x] **Wire auto-save: `/ask` persists user Q + assistant A** with route/confidence (P2, verified: 4 msgs)
- [x] Auto-create session (INSERT OR IGNORE) + 60-char auto-title (P2)
- [x] `get_session_db()` self-heals schema (works under TestClient / cold start) (P2)

## Section 6 — Explainability Mode
- [x] **Compute `contribution_percentage`** per evidence ([eN] count / total) — `analysis.compute_contributions` (P1, live-verified)
- [x] **Populate `trust_factors`** (retrieval/rerank/is_primary/summary) — `analysis.attach_trust_factors` (P1)
- [x] Complete `generation_steps` (routing/sql_generation/document_retrieval/generation/verification) — orchestrator (P1)
- [x] `ExplainabilityPanel.tsx` flowchart + contribution chart + trust list + SQL details
- [x] **Citation Map** sub-panel (2-col [eN] ↔ evidence, clickable highlight) (P7)

## Section 7 — Workspace Mode
- [x] Workspace/artifact tables + 7 endpoints + `/generate` (routes.py)
- [x] Per-artifact-type generation directives (`_ARTIFACT_DIRECTIVES`: report/ppt_content/action_plan/summary) (P4)
- [x] `WorkspaceView.tsx` artifact library UI (cards + preview, new Studio tab) (P4)
- [x] Artifact modal: render (tables via AnswerTable, JSON code block) + export .txt/.md + copy + Regenerate (P4)
- [x] PPT "slides preview" toggle (P4)
- [x] "Generate New Artifact" dialog (P4)

## Section 8 — Verification Layer
- [x] **Cross-source contradiction detection** (pairwise LLM) — `analysis.detect_contradictions` (P1, live-verified: 4 pair checks)
- [x] **Populate `contradictions[]` + `verification_warning`** — orchestrator (P1)
- [x] **Compute `hallucination_risk_score`** (spec formula) — `analysis.compute_hallucination_risk` (P1)
- [x] `VerificationBadge.tsx` (verified / contradictions / unverified / GK)
- [x] New LLM calls counted in pricing; OpenAI model prices added (P1)

## Section 9 — Project Memory
- [x] project_memory table + 3 CRUD endpoints (routes.py)
- [x] **`app/memory.py`** — extraction + retrieval logic (P3, verified: 5 items stored)
- [x] LLM memory-extraction pass after workspace Q&A (`extract_and_store`) (P3)
- [x] Inject relevant memory into generation context (`get_memory_context` → custom_system_prompt) (P3)
- [x] `MemoryViewer.tsx` + Memory tab (confidence bar, forget, add) (P3)

## Section 10 — Multi-Agent Reasoning
- [x] **Multi-agent orchestration** `app/multi_agent.py`: decompose → ThreadPool fan-out → synthesize (P5, live: 3 sub-Qs)
- [x] Populate `multi_agent_trace`; trigger on `multi_agent` flag OR multi-part heuristic (`is_multipart`) (P5)
- [x] `MultiAgentTrace.tsx` wired in `AnswerPanel` (renders the tree when present) (P5)
- [ ] UI toggle to force multi-agent (add to AI Settings) — P7

## Section 11 — Workflow Automation
- [x] workflows table + 3 endpoints (routes.py)
- [x] **`app/workflow.py`** executor + asyncio cron scheduler (started in main.py) (P6, verified: 2-step run → 2 artifacts)
- [x] Scheduled (cron, no extra deps) + manual triggers; status tracking (P6)
- [x] `WorkflowBuilder.tsx` + Workflows tab (in Studio) (P6)
- [x] Shared `app/artifacts.py` (generate_artifact_core reused by route + workflows) (P6)

## Section 12 — UI/UX Global Improvements
- [x] `ui/lib/i18n.ts` (EN/HE base strings)
- [x] Layout restructure (`page.tsx` sidebar + main + settings + tabs)
- [x] Answer card anatomy (`AnswerPanel.tsx`)
- [x] Dark mode via CSS vars + `prefers-color-scheme`; RTL Hebrew detection
- [x] `types.ts` + `api.ts` with new types/endpoints
- [x] Ctrl+K (new chat) shortcut
- [x] Ctrl+Enter (submit, in question box) + Ctrl+E (toggle explainability, via event) (P7)
- [x] Manual dark-mode toggle in top nav (+ globals.css manual override) (P7)
- [x] Empty-state example question chips (populate + ask) (P7)
- [x] Loading state on answer (spinner card present) (P7)
- [ ] 🟡 Mobile bottom-sheet drawer (<768px) — sidebar already collapses to rail; deferred polish
- [ ] 🟡 Finish i18n adoption for new Studio/MemoryViewer/Workflow strings — deferred polish
- [x] **SSE streaming**: `/ask/stream` `StreamingResponse` (status→route→delta→done) + `askStream` client + live render (P8)

## Section 13 — Constraints & Tests
- [x] New tables via idempotent startup migration (main.py) + self-healing `get_session_db`
- [x] Proper HTTP status codes — 201 on POST creates (P8); deletes return 200 + body
- [x] Tests: GENERAL_KNOWLEDGE routing path (`tests/test_upgrade_features.py`) (P9)
- [x] Tests: SQL validation (SELECT/LIMIT/DDL-DML/allow-list/multi-stmt) (P9)
- [x] Tests: contradiction detection + contribution + hallucination-risk (P9)
- [x] Live end-to-end validation (PDF/SQL/HYBRID/GENERAL_KNOWLEDGE) ✓; Docker sanity (no new deps, `COPY app`) ✓ (P9)
- [x] Full suite: **49 passed, 10 skipped**; UI `tsc` + `next build` clean
