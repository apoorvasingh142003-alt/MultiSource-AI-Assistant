# 04 — Backlog (pick-up-able tasks)

Concrete tasks per phase. Attach this + the phase's context to a fresh session and start.
Check items off as done. Each task names the likely files.

## Phase 0 — Reliability floor

- [x] One-command bring-up documented + verified from cold (`scripts/start.sh`; `/health` green,
      public link up). See [plans/00-RELIABILITY-plan.md](plans/00-RELIABILITY-plan.md).
- [x] Encrypt OAuth/provider tokens at rest in the state DB — `app/crypto.py` (Fernet) wired into
      `app/integrations/hubspot.py`; `integration_tokens.token` is now `enc:v1:…` ciphertext,
      backward-compatible with legacy plaintext. Key: `ABA_ENCRYPTION_KEY` → `ABA_AUTH_SECRET` → dev.
- [x] Cold-start "warming up" UX instead of an error on first request — `app/readiness.py` +
      `/health` never-500 (`status: warming|ok`); UI shows a calm warming banner + gates the composer.
- [ ] (On first real client) provision an always-on host + stable domain + HTTPS; document deploy.

## Phase 1 — Docling ingestion

- [x] Add Docling as a parser behind the ingestion interface — pluggable parsers under
      `app/ingestion/parsers/` (`basic` = pypdf, always available; `docling` = import-guarded,
      optional). `ingest_pdf`/`ingest_pdf_dir` unchanged; `ABA_PDF_PARSER=auto|docling|basic`.
      Per-file fallback to basic on any Docling failure. See [plans/01-DOCLING-plan.md](plans/01-DOCLING-plan.md).
- [x] Table-aware chunking; table structure preserved into markdown for retrieval (Docling
      markdown tables kept whole; basic parser keeps pipe-delimited tables intact).
- [x] Emit per-document/parse **confidence** (`Chunk`/`IngestedDoc` → chunk dict → `Evidence`
      → `trust_factors`); thread it into the credibility label as a caveat.
- [x] Add hard PDFs (merged table, multi-column, image-only scan) to a separate eval corpus
      (`scripts/make_hard_pdfs.py` → `data/eval_pdfs/`, kept out of the seeded demo).
- [x] Eval: correct cited answers on the hard PDFs (`scripts/eval.py` Phase-1 block);
      graceful labelled degradation on parse fail (empty scan → `status=error`, never silent).
      Low parse confidence lowers credibility (verification_warning + answer caveat) while
      the tri-state wall stays intact (grounded stays grounded). Tests: `tests/test_ingestion_docling.py`.

## Phase 2 — ChatGPT-class UI

See [plans/02-CHAT-SURFACE-plan.md](plans/02-CHAT-SURFACE-plan.md). **Stack deviation (approved):**
kept the proven custom-SSE transport + rich `Trace` rendering instead of adopting assistant-ui +
Vercel AI SDK — the AI SDK data-stream protocol would mean rewriting tested streaming for no
user-visible gain, and the library isn't a locked decision (the exit criteria are a UX outcome).

- [x] Rebuilt the chat surface into a clean ChatGPT-style shell (sidebar · clean chat · composer),
      keeping tokens/`globals.css`. Top nav tabs removed; Studio (`WorkspaceView`) dropped from the
      surface (files kept). (`ui/app/page.tsx`, `ui/components/ChatThread.tsx`, `Composer.tsx`.)
- [x] Streaming wired from `POST /ask/stream` (existing `askStream`), smooth token stream + a
      compact tri-state chip (`AnswerStateChip.tsx`) on every message.
- [x] Side inspector panel with tabs Answer · Trace · Evidence · Sources — a slide-in drawer
      (`ui/components/InspectorPanel.tsx`) reusing `AnswerPanel`, `Inspector.tsx`, `trace.tsx`,
      `Workspace` rows verbatim. Citations + "Inspect" open it focused.
- [x] In-chat file upload → `POST /ingest/pdf` (📎 in the composer) with visible ingest state +
      a system note in the thread; SQLite upload lives in the Sources tab.
- [x] Replaced the 13-persona picker with user-defined role + instructions (ChatGPT-style
      `CustomizePanel.tsx`, mapped to existing `agent_role` / `custom_system_prompt` — no backend
      change). `app/roles.py` retained only as the default label. Removed `PRESET_ROLES` from the UI.
- [x] Threads/history kept wired to `/sessions` (sidebar unchanged).
- [x] `tsc --noEmit` + `next build` clean (via the /home clone workflow).

## Phase 3 — Tri-state answers + generative components

See [plans/03-COMPONENTS-plan.md](plans/03-COMPONENTS-plan.md). **Stack note (consistent with
Phase 2):** components ride the existing custom-SSE `done` payload as a new
`AskResponse.components` array (no Vercel AI SDK data-stream protocol); charts/timelines are
self-contained SVG (no Recharts/Tremor dep). Components are built **deterministically** from
the trace's SQL rows / evidence in the one `Engine._finalize` chokepoint, **grounded-only** —
so the wall is never dressed up as a confident chart, and every path gets them for free.

- [x] Prominent tri-state label component (grounded+cited / reasoned-advice / insufficient) —
      never a calm/positive state for ungrounded. Shipped in Phase 2 (`AnswerStateChip.tsx` on
      every message + full `AnswerStateBanner.tsx` in the inspector, driven by backend
      `answer_state`); verified prominent + wall-safe this phase.
- [x] Clickable citations → highlight evidence in the panel (`[eN]` in prose AND on every
      component's cited-footer → `openCitation` → inspector scroll + `cite-pulse`).
- [x] Generative UI tools → React components, rendered under the streamed prose:
  - [x] Cited **table** from SQL rows + copy/export — `AnswerComponent(kind="table")` from the
        primary SQL execution, rendered via `AnswerTable.tsx` (sort/paginate/CSV/TSV) with a
        cited footer. Suppresses the model's duplicate markdown table.
  - [x] **Chart** — self-contained SVG bar chart (`GenerativeComponents.tsx`), no chart lib.
  - [x] **Timeline** — self-contained vertical SVG-accented timeline, chronological.
  - [x] **Document/clause artifact** — verbatim top cited passage in a titled card.
- [x] Intent → component selection (`app/retrieval/intent.py::detect_component_intent` +
      `app/generation/components.py::build_components`). A false cue never invents a component —
      one is emitted only when the trace actually has the data to back it.

## Phase 4 — Agentic iterative retrieval

- [ ] Sufficiency-check node in the LangGraph agent (`app/agent/graph.py`): "does current
      evidence answer the question?" → continue/stop.
- [ ] Query reformulation / expansion loop; bounded rounds + latency cap.
- [ ] Stream iteration steps into the trace panel (`app/agent/runner.py` → trace timeline).
- [ ] Eval: multi-hop + evidence-spread-across-docs cases with ground-truth citations.

## Phase 5 — Reasoning / design mode

- [ ] Strengthen `generate_grounded_advice` (`app/generation/generate.py`) for design/strategy Qs.
- [ ] Document-intelligence prompts: clause analysis, gap analysis, risk ID over retrieved evidence.
- [ ] Ensure advice answers always carry the reasoned-advice label + disclaimer; never fabricate facts.
- [ ] Eval: advice questions produce structured, grounded, correctly-labeled output.

## Phase 6 — Actions & integrations

- [ ] Action-tool framework: LLM tools that POST to n8n webhooks (config per tenant).
  - [ ] `create_lead` / CRM write.
  - [ ] `escalate` (hand off to human).
  - [ ] Vertical action (e.g. `create_invoice` → QuickBooks via n8n / MCP).
- [ ] MCP **server**: expose `search_documents`, `sql_query`, `ingest_*` (Python `mcp` SDK).
- [ ] MCP **client**: consume one external MCP server (e.g. QuickBooks) as tools.
- [ ] Sandboxed code execution (Pyodide or e2b), gated to analysis intents, shown in trace.
- [ ] Google Drive connector.
- [ ] WhatsApp channel (validate the Meta Cloud webhook + 24h window live).

## Cross-cutting (do continuously)

- [ ] Keep `scripts/eval.py` green every phase; separate retrieval vs generation vs abstention metrics.
- [x] Make the tri-state wall a first-class, backend-computed `answer_state`
      (grounded/reasoned/insufficient) rendered by one `AnswerStateBanner` — no UI re-derivation,
      no blending. (`app/models.py::compute_answer_state`, stamped in `app/engine.py::_finalize`;
      `ui/components/AnswerStateBanner.tsx`.) See [plans/01-PRODUCT.md](plans/01-PRODUCT.md).
- [ ] Keep the tri-state wall intact — no phase may blend grounded and ungrounded into one stream.
- [ ] Keep offline determinism so tests/eval run without a key.
- [ ] Update `CLAUDE.md` when architecture shifts (e.g. after the Phase 2 UI rebuild).
