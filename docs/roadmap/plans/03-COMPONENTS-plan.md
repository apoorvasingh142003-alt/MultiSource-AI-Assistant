# Phase 3 — Tri-state answers + generative components (plan)

Status: **shipped** — 2026-07-17.

## Goal (from roadmap 03-ROADMAP.md / backlog 04-BACKLOG.md)

Trustworthy labeled answers, with inline tables/charts/timelines like ChatGPT.

Exit criteria (roadmap): *"show overdue invoices" streams a cited, copyable table;
"contracts expiring timeline" streams a timeline; every answer is unmistakably labeled
by trust level.*

Backlog items:
- [ ] Prominent tri-state label (grounded+cited / reasoned-advice / insufficient) — never
  a calm/positive state for ungrounded.
- [ ] Clickable citations → highlight evidence in the panel.
- [ ] Generative UI: cited **table** from SQL rows + copy/export, **chart**, **timeline**,
  **document/clause artifact** in the side panel.
- [ ] Intent → component selection.

## Locked decisions honored

- **The wall is sacred.** Data-bearing generative components (table / chart / timeline)
  are only ever built for a **grounded** answer, and each carries the evidence ids it was
  built from so a component is as cited as the prose. A reasoned-advice or insufficient
  answer never sprouts a confident-looking table/chart. The tri-state label
  (`AnswerStateBanner` / `AnswerStateChip`, backend `answer_state`) stays the single
  source of truth — this phase does not touch how the label is computed.
- **Offline determinism.** Component selection + construction is **fully deterministic**
  (regex intent + reading the trace's SQL rows / evidence). No new LLM call, no new runtime
  dep. `scripts/eval.py` and the whole test suite stay green with no key.
- **Additive tracing.** Components are a new `AskResponse.components` field derived from the
  *existing* `Trace` (SQL executions + evidence) in the one `Engine._finalize` chokepoint
  every answer path already flows through — so every path (classic, agent, multi-agent)
  gets components for free and no existing panel changes contract.
- **No library churn.** Phase 2 deliberately stayed on the proven custom-SSE transport with
  zero chart deps. Charts + timelines are self-contained SVG (no Recharts/Tremor install),
  keeping the `/home` clone build reproducible and the bundle lean.

## Stack decision (deviation, consistent with Phase 2)

The backlog names *Vercel AI SDK generative UI* (a tool result rendering as a React
component mid-stream). As in Phase 2, the backend uses a custom SSE protocol whose `done`
event carries the full `Trace`. Rather than re-plumb a second streaming protocol, the
`done` payload gains a `components` array (already flows via `resp.model_dump_json()`), and
the chat renders those components right after the streamed prose. Same user-visible outcome
(cited table / chart / timeline appear with the answer, copy/export buttons), no dependency
or protocol rewrite. The exit criteria are a UX outcome; the library is not a locked
decision.

## The design

### Backend — deterministic components from the trace

`app/generation/components.py` (new):
- `detect_component_intent(question) -> "chart" | "timeline" | "table" | None` — regex over
  the question ("chart/plot/graph/bar", "timeline/expiring/over time/schedule", "table/
  list/breakdown/per "). Deterministic, offline.
- `build_components(resp) -> list[AnswerComponent]`:
  - Guard: only when `answer_state == "grounded"` (protect the wall). Otherwise `[]`.
  - Pick the **primary SQL execution** (valid, has rows: `sql_main` → `sql_step` → first
    valid-with-rows; never `entity_link`). Map its rows → the relational `Evidence` ids
    (`source_kind == "relational"`) for citations.
  - **table**: always built from the primary SQL result (columns + rows) — the canonical
    *cited* table (copy/export on the client). Carries `evidence_ids`.
  - **chart** (only if intent==chart and a label col + numeric col exist): `{labels, values,
    value_label}`, capped rows.
  - **timeline** (intent==timeline OR a date-like column present): `{events:[{date,title,
    detail}]}`, sorted by date.
- All three read only the trace — no new model call.

`app/models.py`: add `AnswerComponent` (kind, title, table cols/rows, chart labels/values,
timeline events, `evidence_ids`, `note`) and `AskResponse.components: list[AnswerComponent]`.

`app/engine.py::_finalize`: after `compute_answer_state`, set
`resp.components = build_components(resp)`. One chokepoint → every path covered.

### Frontend — render the components under the streamed prose

- `lib/types.ts`: add `AnswerComponent` + `components?` on `AskResponse`.
- `components/GenerativeComponents.tsx` (new): each component in a titled card with a
  "grounded" chip and a `[eN]`-style cited footer (clickable → inspector). Dispatch on `kind`:
  - `table` → **reuses `AnswerTable` verbatim** by adapting the structured `{columns, rows}`
    into its existing `ParsedTable` shape (`{headers, rows, startIndex:0, endIndex:0}`) — no
    change to `AnswerTable`'s signature, so its sorting/paging/CSV/TSV all keep working.
  - `chart` → self-contained SVG/flex bar chart (no chart-lib dep), animated bars.
  - `timeline` → self-contained vertical timeline (chronological, date-accented).
  - `artifact` → a verbatim cited document-clause blockquote (shipped in addition to the
    three planned data components — the "document/clause artifact" backlog item).
- `components/ChatThread.tsx` + `AnswerPanel.tsx`: render `resp.components` after the answer
  body. When a structured **table** component is present, suppress the markdown-parsed table
  for the same data (`stripMarkdownTables`, added to `lib/tableParser.ts`) — the structured
  one is the cited canonical.
- Clickable citation on a component → `onCite(turn, evId)` → existing inspector highlight.

## Files

New:
- `app/generation/components.py` — intent detection + deterministic component builder.
- `ui/components/GenerativeComponents.tsx` — table/chart/timeline/artifact renderer.
- `tests/test_components.py` — deterministic, offline component tests.

Changed:
- `app/models.py` — `AnswerComponent` + `AskResponse.components`.
- `app/engine.py` — build components in `_finalize`.
- `app/retrieval/intent.py` — `detect_component_intent`.
- `ui/lib/types.ts` — `AnswerComponent` + `components?`.
- `ui/lib/tableParser.ts` — `stripMarkdownTables` (avoid a double table).
- `ui/components/ui.tsx` — `chart` + `timeline` icons.
- `ui/app/globals.css` — `bar-grow` bar animation.
- `ui/components/ChatThread.tsx`, `ui/components/AnswerPanel.tsx` — render components.
- `docs/roadmap/04-BACKLOG.md` — check off Phase 3 items.
- `CLAUDE.md` — note the components layer.

## Exit criteria checklist

- [x] SQL question ("total outstanding invoice amount per customer") → streams a **cited,
      copyable table** (rows + export CSV + copy TSV + clickable `[eN]` source chips).
- [x] "contracts expiring in the next 90 days" → streams a **timeline** (by End Date) + table.
- [x] Chart intent ("chart the outstanding invoice amount by customer") → streams a **bar
      chart** (Acme 60k / Globex 30k / Initech 15k) + the cited table.
- [x] Clause question ("what do our contracts say about service suspension?") → streams a
      verbatim **document/clause artifact**.
- [x] Every answer unmistakably labeled by trust level (tri-state chip + banner), and no
      data component ever appears for a reasoned/insufficient answer (verified: Berlin
      headcount → insufficient, no components; SaaS best-practices → reasoned, no components).
- [x] Clicking a component's citation opens the inspector on the backing evidence
      (`onCite` → existing `useCiteHighlight` scroll+pulse).
- [x] `pytest -q` (185 passed, 10 skipped) + `scripts/eval.py` (12/12) green offline;
      `tsc --noEmit` + `next build` clean (page bundle 33.7 kB).
- [x] Verified live at https://assistant.lazysnail.xyz/ — public UI 200, `/health` green,
      the newly-built UI bundle is the one served (`bar-grow`/`cited:`/grounded chip present
      in the served `app/page` chunk), and the real HTTP SSE `done` frame carries `components`
      for the chart/table/timeline/artifact scenarios (auth ON, stdlib-minted JWT).

## Verification notes

- **Backend:** `pytest -q` → 185 passed, 10 skipped. `scripts.eval` → **12/12** (Phase-2
  baseline was 11/12; the SQL/HYBRID/PDF routing + hard-PDF cases all pass). 16 new
  deterministic component tests in `tests/test_components.py`.
- **Frontend:** `tsc --noEmit` exit 0; `next build` compiled, 4/4 pages, page bundle 33.7 kB
  (≈ +2 kB over Phase 2 for the new renderer). Charts/timelines are dependency-free SVG.
- **Live (production image, auth ON, live OpenAI):** exercised the running container the way
  the browser does — the SSE `/ask/stream` `done` frame over real HTTP carries a grounded
  `chart` + `table` (values Acme 60000 / Globex 30000 / Initech 15000, cited e1–e3). Ran all
  six scenarios (table / chart / timeline / artifact / insufficient / reasoned) through the
  production engine; the two ungrounded states correctly emit **zero** components (wall intact).
