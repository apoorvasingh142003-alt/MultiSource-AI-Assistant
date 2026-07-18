# Phase 5 plan — Reasoning / design mode ("it thinks")

Roadmap: [03-ROADMAP.md](../03-ROADMAP.md) Phase 5 · Backlog: [04-BACKLOG.md](../04-BACKLOG.md)

## Exit criteria being satisfied

> "Design a renewal strategy for these contracts" produces a structured, useful,
> clearly-labeled answer grounded in the actual contracts. Strengthen the reasoned-advice
> path; document intelligence (clause / gap / risk analysis over retrieved evidence);
> advice answers always carry the reasoned-advice label + disclaimer, never fabricate;
> eval: advice questions produce structured, grounded, correctly-labeled output.

## The gap (why the exit criterion fails today)

1. The advice path (`generate_grounded_advice`) only fires when retrieval found **nothing**
   (`if not evidence:` in the orchestrator). A design/strategy question that *does* retrieve
   contract passages goes through plain grounded generation, whose rules ("use ONLY the
   evidence, never outside knowledge") make a strategy answer impossible — the model either
   under-delivers or declares insufficient.
2. `is_advice_question` only recognises recommendation/safety cues ("recommend",
   "should he", "is it safe") — "design a renewal strategy" isn't detected at all.
3. There is no document-intelligence treatment: "analyze the termination clauses" /
   "identify the risks in these contracts" runs as a generic Q&A prompt.

## Design (wall-safe by construction)

One deterministic detector, three treatments — the tri-state wall never blends:

- **`detect_reasoning_mode(q)`** (`app/retrieval/intent.py`) → `"" | "advice" | "design" | "analysis"`.
  - `advice` — existing `_ADVICE_CUE` (recommend / should he / is it safe …).
  - `design` — design/strategy/planning cues (design/draft/propose a strategy/plan/roadmap,
    "how should we", gap analysis, improve/optimize …). Needs general knowledge → lands in
    the **two-part reasoned** treatment.
  - `analysis` — explicit analytic verbs over the record (analyze/assess/evaluate/audit/
    review, risk assessment, clause analysis). Answerable **entirely from evidence** →
    stays **grounded** with a document-intelligence prompt. (Jenny's ask: grounded
    reasoning over evidence, not invention — does not violate the wall.)
  - Word-boundary regexes; must NOT fire on the existing demo suite ("what penalties do
    they **define**", "**summarize** the risks" stay plain grounded Q&A).

- **advice/design + evidence** (new path): the orchestrator retrieves normally, gates the
  passages with the existing deterministic `_on_topic` check, then calls
  `generate_grounded_advice(mode=…)` — PART 1 = cited facts from the evidence (verified by
  the same `verify_citations`), PART 2 = begins with the EXACT `ADVICE_GUIDANCE_DISCLAIMER`
  sentence → `compute_answer_state` classifies **reasoned** via the existing marker. Design
  mode gets a structured-deliverable directive (situation → strategy/options → risks &
  mitigations → next steps, each tied back to Part-1 facts, no [eN] in Part 2).
  Off-topic retrieval → same honest "the record does not mention…" Part 1 as today.
- **advice/design + no evidence**: existing branch, broadened from `is_advice_question`
  to `mode in ("advice","design")`, now streams for real (`llm.stream_text`).
- **analysis + evidence**: plain grounded generation with a DOCUMENT INTELLIGENCE
  directive appended to the system prompt (findings organised per document/clause, every
  finding cited, absences stated as "the record does not show…" — never as world facts).
  `answer_state` stays **grounded**.
- **Deterministic fallback** (offline/CI): `generate_grounded_advice`'s fallback now
  builds PART 1 extractively from the evidence (cited) + a structured PART 2 skeleton
  after the disclaimer — so the eval/tests demonstrate structure + grounding + label with
  no key.

## Changes

### Backend
1. `app/retrieval/intent.py` — `_DESIGN_CUE`, `_ANALYSIS_CUE`, `detect_reasoning_mode()`.
2. `app/models.py` — additive `Trace.reasoning_mode: Optional[str]`.
3. `app/generation/generate.py` —
   - `generate_grounded_advice(..., mode="advice"|"design", on_token=None)`: mode-specific
     PART 2 directive, real streaming, extractive+structured deterministic fallback.
   - `reasoning_mode` param on `generate_answer` / `generate_answer_stream` → injects the
     DOCUMENT INTELLIGENCE directive when `"analysis"`.
4. `app/routing/orchestrator.py` — detect mode once; stamp `trace.reasoning_mode` + note;
   route generation per the table above; `trace.generation["reasoning_mode"]`.
5. `app/agent/research.py` — the deep-research final answer honors the same mode
   (advice/design → grounded advice over the collected evidence; analysis → directive).

### Frontend (minimal — the label already exists)
6. `ui/lib/types.ts` — `reasoning_mode?` on `Trace`; `ui/components/Inspector.tsx` — a
   pill in the Routing decision panel ("reasoning mode: design — grounded facts +
   labelled guidance").

### Eval & tests
7. `scripts/eval.py` — Phase-5 block (offline-deterministic):
   - design: "Design a renewal strategy for our customer contracts." → `reasoned`,
     evidence > 0, disclaimer present, citations verified, two-part structure.
   - analysis: "Analyze the termination clauses in our contracts." → `grounded`, cited,
     `reasoning_mode == "analysis"`.
   - wall: an out-of-domain advice question stays disclaimed (reasoned), never a
     fabricated grounded answer, never a bare decline.
8. `tests/test_reasoning_mode.py` — detector battery (incl. non-firing on the demo
   suite), engine e2e for all three treatments, off-topic design honesty, red-team
   suite (`test_nursing_home_red_team.py`) must stay green unchanged.

## Status

- [x] Plan written
- [x] Reasoning-mode detector + `Trace.reasoning_mode`
- [x] Grounded-advice strengthening (design mode, real streaming, extractive+structured
      deterministic fallback; grouped-citation normalization "[e1, e2]"→"[e1][e2]";
      paraphrased disclaimer re-inserted directly under the Part 2 header)
- [x] Analysis directive + orchestrator wiring (advice path now fires WITH evidence,
      gated by `_on_topic`)
- [x] Deep-research mode passthrough
- [x] UI pill + types
- [x] Tests green offline — pytest 231 passed / 10 skipped (incl. the new
      `tests/test_reasoning_mode.py`, 35 checks); `scripts/eval.py` **17/17 offline**.
      Live eval 16/17: the one ✗ is a pre-existing gpt-4o-mini router flake (the "total
      outstanding per customer" demo intermittently routes HYBRID instead of SQL — answer
      still grounded, cited, verified; routing untouched by this phase).
- [x] tsc + next build green (via the /home clone workflow)
- [x] Live verification (2026-07-17): https://assistant.lazysnail.xyz `/api/health` ok +
      UI loads through the tunnel; deployed bundle serves the inspector pill. Against the
      deployed authenticated API (live gpt-4o): "Design a renewal strategy for our
      customer contracts." → **reasoned**, `reasoning_mode: design`, PART 1 cites all 5
      seeded contracts ([e1]–[e5], citation check verified), exact disclaimer directly
      under the PART 2 header, then a structured strategy (situation → options →
      recommendations → risks → next steps). "Analyze the termination clauses…" →
      **grounded**, `reasoning_mode: analysis`, verified. A factual control question is
      unchanged (grounded, no mode). `/ask/stream` streamed the design answer live
      (517 deltas) with the full trace in the `done` event.
