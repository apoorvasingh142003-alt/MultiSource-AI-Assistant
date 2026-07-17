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

- [ ] Stand up assistant-ui + Vercel AI SDK in `ui/` (new chat surface; keep tokens/`globals.css`).
- [ ] Wire streaming from `POST /ask/stream` into the AI SDK transport.
- [ ] Side inspector panel with tabs: Answer · Trace · Evidence · Sources (reuse existing
      `Inspector.tsx`, `trace.tsx`, `ExplainabilityPanel.tsx` content).
- [ ] In-chat file upload → `POST /ingest/pdf`.
- [ ] Replace `app/roles.py` persona picker with user-defined instructions (custom system prompt
      per conversation/tenant). Remove the 13-persona UI.
- [ ] Threads/history wired to existing `/sessions` endpoints.
- [ ] `tsc --noEmit` + `next build` clean (remember the /home clone build workflow — see CLAUDE.md).

## Phase 3 — Tri-state answers + generative components

- [ ] Prominent tri-state label component (grounded+cited / reasoned-advice / insufficient) —
      never a calm/positive state for ungrounded. (Extend `VerificationBadge.tsx`.)
- [ ] Clickable citations → highlight evidence in the panel.
- [ ] Generative UI tools (AI SDK) → React components, streamed:
  - [ ] Cited **table** from SQL rows + copy/export (extend `AnswerTable.tsx`).
  - [ ] **Chart** (Recharts/Tremor).
  - [ ] **Timeline**.
  - [ ] **Document/clause artifact** in the side panel.
- [ ] Intent → component selection (extend `app/retrieval/intent.py`).

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
