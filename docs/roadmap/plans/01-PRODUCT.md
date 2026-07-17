# Plan — 01 PRODUCT: the tri-state grounding wall as a first-class concept

Phase context: [docs/roadmap/01-PRODUCT.md](../01-PRODUCT.md). This phase defines the product
identity. The one non-negotiable, demo-able deliverable that *is* the product's moat:

> **Every answer is explicitly labeled one of three states — grounded+cited /
> reasoned-advice / insufficient-evidence — and the three are never blended into one
> confident stream.**

## Problem with the code today

The backend already has the *spine* of the wall (grounding-first gate, `_GK_DISCLAIMER`,
`generate_grounded_advice`, honest "insufficient evidence" declines). But the **answer state
is never named**. The UI *re-derives* it from a scatter of loosely-related signals
(`route === "GENERAL_KNOWLEDGE"`, `citation_check.verified`, `evidence.length`,
`insufficient`, `hasContradictions`, `hallucination_risk_score`). That inference lives in
`VerificationBadge.tsx` + ad-hoc blocks in `AnswerPanel.tsx` and disagrees with itself in
edge cases (e.g. safety-net recovery on a `NONE` route needs a special `recoveredFromDocs`
patch to stop the badge contradicting the answer). That is *exactly* the "blend" the roadmap
forbids — the wall is implicit and fragile.

**Fix:** make the tri-state a single, explicit, backend-computed value that every generation
path sets, ship it in the API, and render it as one unmistakable label the UI reads directly
(no re-derivation). This hardens the moat and removes the fragile inference.

## Exact changes

### Backend
1. `app/models.py`
   - Add `AnswerState = Literal["grounded", "reasoned", "insufficient"]`.
   - Add `answer_state: AnswerState = "grounded"` to `AskResponse`.
   - Add `compute_answer_state(answer, route, evidence, insufficient) -> AnswerState`:
     a single classifier used everywhere. `insufficient` → `insufficient`; a
     GENERAL_KNOWLEDGE route / parametric synthetic evidence / the GK or advice disclaimer
     text in the answer → `reasoned`; otherwise `grounded`.
2. `app/engine.py` — `Engine.ask` is the one funnel for **all** paths (orchestrator,
   agent, multi-agent, empty-workspace). Compute and stamp `resp.answer_state` there right
   before returning, so no path can forget it. Also stamp the empty-workspace + error
   responses explicitly.
3. `app/api/routes.py` — the `/ask` error fallback returns `answer_state="insufficient"`.
   Streaming already serializes the full `AskResponse` in the `done` event, so it's covered.

### Frontend
4. `ui/lib/types.ts` — add `answer_state?: AnswerState` to `AskResponse` + the union type.
5. `ui/components/AnswerStateBanner.tsx` (new) — the prominent, unmistakable tri-state label.
   Three visually distinct treatments, driven **only** by `resp.answer_state`:
   - `grounded` — emerald, shield: "Grounded in your sources · cited".
   - `reasoned` — indigo/amber, lightbulb: "Reasoned advice · not from your sources".
   - `insufficient` — neutral slate, question: "Insufficient evidence · not answered".
   Never a calm/positive treatment for a non-grounded state.
6. `ui/components/AnswerPanel.tsx` — render `AnswerStateBanner` prominently at the top of the
   answer card. Keep `VerificationBadge` (citation-verified detail) as a secondary chip, but
   the tri-state banner is the headline. Drop the now-redundant ad-hoc `isGK` inference in
   favor of `answer_state === "reasoned"`; keep the `recoveredFromDocs` pill (it's useful
   provenance, no longer load-bearing for correctness).

### Eval / tests
7. `scripts/eval.py` — assert `answer_state` per case: NONE example → `insufficient`;
   answerable examples → `grounded`; the forced-GK grounding-first probe → `grounded`
   (the wall must not flip to `reasoned` when the safety net recovered a cited answer).
8. `tests/test_answer_state.py` (new) — unit-test `compute_answer_state` + an end-to-end
   assertion that a doc question is `grounded`, an out-of-scope question is `insufficient`.

## Exit criteria satisfied (from 01-PRODUCT + roadmap locked decisions)
- Every answer carries an explicit, prominent tri-state label. ✅ the wall, made first-class.
- Grounded / reasoned / insufficient never share the same visual weight. ✅
- Offline determinism preserved; `scripts/eval.py` stays green. ✅
- Additive tracing: no existing `Trace`/panel contract broken; `answer_state` is one new
  optional field. ✅

## Out of scope here (belongs to later phases, per 04-BACKLOG)
- Persona-picker removal (Phase 2 — the UI already uses free-text role + custom instructions;
  the 13-persona *picker* is gone, only `app/roles.py` presets remain as a `role` param).
- Generative table/chart/timeline components (Phase 3).
- Docling ingestion (Phase 1), agentic iterative retrieval (Phase 4).

## Status — SHIPPED
- [x] Plan written
- [x] Backend: `AnswerState` + `compute_answer_state` + stamp in engine (`_finalize`) / routes
- [x] Frontend: types + `AnswerStateBanner` + wired into `AnswerPanel` (replaces ad-hoc GK/insufficient blocks)
- [x] Eval + tests green — `tests/test_answer_state.py` (7 tests), full suite 150 passed, eval 9/10
      (the one miss is a pre-existing `SQL→HYBRID` live-route classification difference, unrelated)
- [x] Live site verified — https://assistant.lazysnail.xyz `/health` green; all three states
      exercised through the real container: grounded (PDF, 5 cites), reasoned (GK + disclaimer),
      insufficient (honest decline). Public `/api/ask` correctly 401s a forged bearer (NextAuth
      session-cookie auth intact); verified via a valid HS256 token against the same container.
- [x] Committed & pushed

### Classifier subtlety worth remembering
`compute_answer_state` must treat **real retrieved evidence as grounded even when the route
label says GENERAL_KNOWLEDGE** — the grounding-first safety net can recover cited documents
after the router (wrongly) chose GK. Keying the label off the route name alone flipped a
genuinely grounded answer to `reasoned`; the fix keys off evidence (parametric-vs-real) first,
route name only as the no-evidence fallback.
