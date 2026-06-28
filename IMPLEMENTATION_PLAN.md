# Implementation Plan — MultiSource AI Assistant Upgrade

**Driving spec:** `MASTER_FEATURE_PROMPT.md` (14 sections)
**Tracker:** `task.md` (kept in sync as work lands)
**Date started:** 2026-06-19
**Working copy:** `/home/apoorv/MultiSource-AI-Assistant` (WSL native)

---

## 1. Key finding — this is a *completion* job, not a from-scratch build

The repo's single "Initial commit" already contains a substantial (~70–80%) attempt at the
entire spec. A section-by-section audit (backend pipeline, backend data/services, frontend)
found that most files in the spec's "files to create" checklist already exist with real code.
**So the work is: verify what's there, fix what's broken, build the genuinely-missing pieces,
and prove it runs** — not re-implement.

### Baseline (verified 2026-06-19)
- Backend imports cleanly; existing pytest suite: **34 passed, 10 skipped** (skips = optional ML embeddings).
- Frontend **does not currently typecheck** — `components/Workspace.tsx:352` references undefined
  `aiSettings` / `onAiSettingsUpdate`. **Blocker — fix first.**
- `.venv` (core deps) and `ui/node_modules` are installed.
- `.env` created from template; **needs the user's API key** for live LLM validation.

---

## 2. Audit results — what's DONE vs. what's a GAP

Legend: ✅ done & plausibly correct · 🟡 partial · 🔴 missing/broken

| Spec | Feature | Status | Notes |
|------|---------|--------|-------|
| 0.1 | `GENERAL_KNOWLEDGE` route + secondary classifier + synthetic evidence + skip-verify + blue chip | ✅ | Backend + UI both wired |
| 1.1 / 1.2 | Domain-agnostic router; dynamic `describe()` | ✅ | Source-centric prompt; content-based descriptions |
| 2.1 | `agent_role` / `custom_system_prompt` injection (grounding preserved) | ✅ | except `agent_role` not passed to router → 🟡 |
| 2.2 | AI Settings panel (role presets, prompt counter, format, localStorage) | ✅ | |
| 3.1 / 3.2 | Output-format directives; `AnswerTable` (sort/paginate/CSV/copy/timeline) | ✅ | |
| 4.1 | `ReadAloud` TTS | 🟡 | missing sentence-boundary highlight, voice lang filter, unsupported tooltip |
| 5.1 | sessions/messages tables + 5 endpoints | 🟡 | **`save_message()` is never called** — chat history never persists |
| 5.2 | `ChatSidebar` | ✅ | |
| 6.1 | `generation_steps` / `contribution_percentage` / `trust_factors` | 🔴 | steps partial; the other two fields **never computed** |
| 6.2 | `ExplainabilityPanel` (5 sub-panels) | 🟡 | 4/5 done; **Citation Map missing** |
| 7.1 | workspaces/artifacts tables + 7 endpoints + generate | 🟡 | per-artifact-type prompt directives are weak (only generic output_format) |
| 7.2 | Workspace artifact UI (library, modal, export, regenerate, PPT preview) | 🔴 | `Workspace.tsx` is upload-focused; artifact UI absent |
| 8.1 | Contradiction detection; `hallucination_risk_score`; `contradictions[]` | 🔴 | `verify.py` only checks citation validity — none of this exists |
| 8.2 | `VerificationBadge` | ✅ | (will light up once 8.1 produces data) |
| 9.1 | project_memory table + 3 endpoints | 🟡 | **`app/memory.py` missing** — no extraction, no injection |
| 9.2 | `MemoryViewer.tsx` | 🔴 | file missing |
| 10.1 | Multi-agent decompose → parallel → synthesize | 🔴 | `multi_agent` flag is a no-op; `multi_agent_trace` never set |
| 10.2 | `MultiAgentTrace.tsx` | ✅ | (renders once 10.1 produces data) |
| 11.1 | workflows table + 3 endpoints | 🟡 | **`app/workflow.py` missing**; no scheduler; manual-only, synchronous |
| 11.2 | `WorkflowBuilder.tsx` | 🔴 | file missing |
| 12 | Layout, answer-card, dark CSS vars, RTL | 🟡 | missing: Ctrl+Enter, Ctrl+E, dark toggle, example chips, skeleton wiring, mobile bottom-sheet |
| 12.3 | SSE streaming (`StreamingResponse`) | 🔴 | not present (back or front) |
| 13 | Migrations at startup | ✅ | HTTP status codes (201/204) 🟡; i18n adoption 🟡 |
| — | **UI typecheck** | 🔴 | `Workspace.tsx:352` undefined identifiers — compile blocker |

---

## 3. Execution phases (ordered to respect spec dependencies)

Each phase ends with a concrete **acceptance check** and `task.md` boxes ticked.

### Phase 0 — Stabilize baseline  *(no API key needed)*
- Fix `Workspace.tsx:352` compile error so `npx tsc --noEmit` and `next build` are clean.
- Add `pytest` to dev deps; confirm suite green.
- Bring backend (`uvicorn`) + frontend (`next dev`) up; smoke-test `/health`, `/ask` (offline mode).
- **Accept:** UI typechecks; backend serves; one offline `/ask` round-trips end-to-end.

### Phase 1 — Explainability + Verification backend  *(Sec 6.1, 8.1)*
Unlocks the already-built `ExplainabilityPanel` + `VerificationBadge` with real data.
- Compute `contribution_percentage` per evidence (parse `[eN]` markers / total).
- Populate `trust_factors` per evidence from retrieval candidate scores (BM25/dense/RRF/rerank) + SQL.
- Complete `generation_steps` (sql_generation, document_retrieval, verification) with timings.
- Implement cross-source contradiction detection in `verify.py` (pairwise LLM calls), populate
  `contradictions[]`, `verification_warning`, and `hallucination_risk_score` (spec formula).
- Count all new LLM calls in `pricing.py`.
- **Accept:** a HYBRID question returns populated trace fields; contradiction unit test passes.

### Phase 2 — Chat history persistence  *(Sec 5.1)*
- Call `save_message()` for the user question and assistant answer after `/ask`, keyed by
  `session_id`; auto-create session + title (first 60 chars) when absent.
- **Accept:** asking with a `session_id` then `GET /sessions/{id}/messages` returns the turn.

### Phase 3 — Project memory  *(Sec 9)*
- Create `app/memory.py`: LLM extraction pass (facts/entities/preferences) + relevance retrieval.
- Inject workspace memory into generation context; run extraction after workspace Q&A.
- Build `MemoryViewer.tsx` + wire a Memory tab; count LLM calls.
- **Accept:** a workspace answer creates memory rows; next answer shows injected context; UI lists/forgets.

### Phase 4 — Workspace artifacts UI + per-type prompts  *(Sec 7)*
- Per-artifact-type generation directives (report / ppt_content / action_plan / table / json / summary).
- Build artifact library UI: cards, full-screen modal (render + export .txt/.md + copy), Regenerate,
  PPT "slides preview", and the Generate-New dialog (reusing AI Settings).
- **Accept:** generate → appears in library → opens in modal → exports → regenerates.

### Phase 5 — Multi-agent reasoning  *(Sec 10.1)*
- Decomposer → `asyncio.gather` sub-pipelines → synthesizer; populate `multi_agent_trace`.
- Trigger on `multi_agent: true` or multi-part heuristic; count LLM calls.
- **Accept:** a 2-part question returns a `multi_agent_trace`; `MultiAgentTrace` renders the tree.

### Phase 6 — Workflow automation  *(Sec 11)*
- Create `app/workflow.py`: step executor + async scheduler (APScheduler or asyncio) wired at startup;
  manual + scheduled (cron) triggers; status tracking.
- Build `WorkflowBuilder.tsx` + Workflows tab.
- **Accept:** create workflow → Run Now produces artifacts; a scheduled workflow fires.

### Phase 7 — Frontend polish  *(Sec 6.2, 4.1, 12, 13)*
- Citation Map in `ExplainabilityPanel`; ReadAloud sentence highlight + voice filter + tooltip.
- Ctrl+Enter / Ctrl+E shortcuts; manual dark-mode toggle; empty-state example chips; skeleton wiring;
  mobile bottom-sheet; finish i18n adoption (EN/HE) for remaining hardcoded strings.
- **Accept:** shortcuts work; dark toggle persists; chips populate input; no hardcoded user-facing strings.

### Phase 8 — Streaming + HTTP hygiene  *(Sec 12.3, 13)*
- SSE `/ask/stream` via `StreamingResponse`; frontend incremental consumption + skeleton.
- Proper 201/204 status codes on POST/DELETE.
- Pass `agent_role` to router (Sec 2.1 remainder).
- **Accept:** streamed answer renders incrementally; status codes correct.

### Phase 9 — Tests + final validation
- Unit tests required by spec §13: `GENERAL_KNOWLEDGE` routing, SQL validation, contradiction detection.
- Full live validation pass with the real key across business + general questions; `docker compose` sanity.
- **Accept:** new tests green; Docker build unbroken; README example questions behave correctly.

---

## 4. Hard constraints (from spec §13) — enforced every phase
- Do **not** break Docker Compose; new tables via idempotent startup migration (already in place).
- Do **not** change existing `Source` interface signature — extend additively.
- Do **not** change existing `Route` enum values — only add (already satisfied).
- New API endpoints return proper status codes + JSON error bodies.
- New UI components are individual files under `ui/components/`; no new logic dumped in `page.tsx`.
- Bilingual EN/HE for new strings via `ui/lib/i18n.ts`.
- Every new LLM call counted in `app/pricing.py`.

## 5. Validation strategy
- **Backend:** pytest (offline) for logic; live `curl`/HTTP for LLM-dependent paths once key is set.
- **Frontend:** `tsc --noEmit` + `next build` clean per phase; manual UX check in `next dev`.
- **End-to-end:** the README's example questions exercise PDF / SQL / HYBRID / GENERAL_KNOWLEDGE routes.

## 6. Risks / watch-items
- LLM-call volume rises (verification, memory, multi-agent) → cost; keep `cache_first` on for dev.
- Async scheduler must not block FastAPI startup or break the offline path.
- Multi-agent `asyncio.gather` must reuse the engine safely (no shared-state races).
- Frontend artifact/memory/workflow UIs depend on backend shapes — land backend first per phase.
