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

See [plans/04-DEEP-RESEARCH-plan.md](plans/04-DEEP-RESEARCH-plan.md). **Design note:** the
headline loop is a provider-agnostic controller (`app/agent/research.py`) — the LangGraph
agent requires an OpenAI-compatible endpoint, so a LangGraph-only loop would be invisible
on the Anthropic/offline deployments; the LangGraph path additionally got the same gate.

- [x] Sufficiency check — `app/agent/sufficiency.py`: deterministic core (term coverage
      with inflection tolerance, multi-aspect splitting, corpus-spread requirement) +
      live LLM refinement with heuristic fallback. Wired as a real **sufficiency node**
      in the LangGraph graph (`app/agent/graph.py`, bounded loop-back steering) AND as
      the gate of the deep-research controller.
- [x] Query reformulation / expansion loop; bounded rounds + latency cap —
      `app/agent/research.py::run_deep_research` (uncovered-aspect queries, missing-term
      queries, per-document targeting for "across all X"; `ABA_RESEARCH_*` knobs:
      max rounds, queries/round, time budget, evidence cap). Off-topic relevance gate →
      classic grounding-first fallback (the tri-state wall holds).
- [x] Stream iteration steps into the trace panel — `research_step` SSE events render a
      live round-by-round timeline while streaming (`ChatThread.tsx`), and the persisted
      `research_trace` renders as a "Deep research" panel in the inspector Trace tab
      (`Inspector.tsx`). Toggled per-chat via the composer's "Deep research" chip.
- [x] Eval: multi-hop + evidence-spread-across-docs cases — `scripts/eval.py` Phase-4
      block (the spread question must iterate ≥2 rounds and ground + verify citations
      across ≥4 documents; an out-of-scope deep-research question must still decline)
      + `tests/test_deep_research.py`.

## Phase 5 — Reasoning / design mode

See [plans/05-REASONING-plan.md](plans/05-REASONING-plan.md). **Design note:** one
deterministic detector (`app/retrieval/intent.py::detect_reasoning_mode` → advice /
design / analysis / plain), three wall-safe treatments — advice/design get the two-part
grounded-facts + labelled-guidance answer (reasoned); analysis stays a grounded,
cited document-intelligence answer.

- [x] Strengthen `generate_grounded_advice` for design/strategy Qs — `mode="design"`
      turns Part 2 into a structured deliverable (situation → options → recommendations
      → risks → next steps); real streaming; extractive+structured deterministic
      fallback so offline demos still ground Part 1 and cite it. **Crucially, the
      advice path now also fires when retrieval FOUND evidence** (before, a design
      question with retrieved contracts got the plain factual prompt), gated by the
      deterministic `_on_topic` check so guidance is never grounded in off-topic text.
- [x] Document-intelligence prompts — `analysis` reasoning mode appends a DOCUMENT
      INTELLIGENCE directive (findings per document/clause, every finding cited,
      absences stated as facts about the record only) to grounded generation; answer
      stays `grounded`. Deep research honours the same modes for its final answer.
- [x] Advice answers always carry the reasoned-advice label + disclaimer — the exact
      `ADVICE_GUIDANCE_DISCLAIMER` sentence is enforced post-generation, and
      `compute_answer_state` lands every advice/design answer on `reasoned`. Grouped
      citation markers ("[e1, e2]") are normalized so a grounded Part 1 always passes
      verification. `Trace.reasoning_mode` surfaces the mode in the inspector.
- [x] Eval: `scripts/eval.py` Phase-5 block (design → reasoned + cited + verified +
      disclaimed; analysis → grounded + verified; off-corpus advice → disclaimed, never
      fabricated, never a bare decline) + `tests/test_reasoning_mode.py`.

## Phase 6 — Actions & integrations

See [plans/06-ACTIONS-plan.md](plans/06-ACTIONS-plan.md). **Design notes:** actions are
strictly propose → **confirm** → execute (a chat message can only propose; dispatch is a
separate user-confirmed call, HMAC-signed, audit-logged, `simulated` when no webhook is
configured — demo-able offline). MCP is hand-rolled Streamable-HTTP JSON-RPC on the stdlib
(the `mcp` SDK isn't in the image; the subset we speak is small and keeps tests hermetic).

- [x] Action-tool framework (`app/actions/`): deterministic command detection + param
      extraction, per-tenant n8n webhook config **encrypted at rest**, dispatch + audit
      log (`action_configs`/`action_log`), ActionCard UI (editable params, Confirm),
      config UI in Sources → Actions & automations.
  - [x] `create_lead` / CRM write.
  - [x] `escalate` (hand off to human) — ALSO auto-suggested on every insufficient
        answer ("escalates when unsure"); the tri-state label is untouched.
  - [x] Vertical action (`create_invoice` → QuickBooks et al. via n8n).
- [x] MCP **server**: `POST /mcp` (Streamable HTTP) exposing `search_documents`,
      `sql_query` (NL→SQL, sqlglot-validated read-only), `list_sources` — tenant-scoped;
      endpoint + tool list advertised in the UI (`/mcp/info`).
- [x] MCP **client**: minimal Streamable-HTTP client + per-tenant registry
      (`mcp_servers`, auth header encrypted) + `/mcp/servers*` endpoints; registered
      servers' tools join the LangGraph agent as observation-only tools (never cited
      as evidence). Verified end-to-end by self-consuming our own `/mcp`.
- [x] Sandboxed code execution (`app/code_exec.py`): gated to grounded SQL answers with
      an explicit statistical ask; deterministic codegen, AST validation, `python -I -S`
      subprocess with rlimits + wall-clock kill; code+output in the inspector Trace tab,
      answer gains a labeled "Computed from the cited rows" block.
- [ ] Google Drive connector — deferred, demand-driven (per the roadmap's own note).
- [ ] WhatsApp live validation (Meta Cloud webhook + 24h window) — deferred: the channel
      code exists; validating live needs a client's Meta credentials + business number.

## Cross-cutting (do continuously)

- [ ] Keep `scripts/eval.py` green every phase; separate retrieval vs generation vs abstention metrics.
- [x] Make the tri-state wall a first-class, backend-computed `answer_state`
      (grounded/reasoned/insufficient) rendered by one `AnswerStateBanner` — no UI re-derivation,
      no blending. (`app/models.py::compute_answer_state`, stamped in `app/engine.py::_finalize`;
      `ui/components/AnswerStateBanner.tsx`.) See [plans/01-PRODUCT.md](plans/01-PRODUCT.md).
- [ ] Keep the tri-state wall intact — no phase may blend grounded and ungrounded into one stream.
- [ ] Keep offline determinism so tests/eval run without a key.
- [ ] Update `CLAUDE.md` when architecture shifts (e.g. after the Phase 2 UI rebuild).
