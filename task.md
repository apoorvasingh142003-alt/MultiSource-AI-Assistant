# Nexus AI — Task Tracker (Grounding-First Robustness round)

> Branch `enterprise-upgrade`. `[x]` = implemented & verified. Reasoning in `IMPLEMENTATION_PLAN.md`,
> incident write-up in `docs/grounding-first-fix.md`.
> Suite: **108 passed, 10 skipped** · `scripts/eval.py` 10/10 · flagship HYBRID ev=9 · UI `tsc` + `next build` clean.

## Backend — grounding-first guarantee

### G1 — Relevance gate widened (no silent evidence drop)
- [x] `_on_topic()` checks **any of the top-3** passages for a shared content word (was top-1 only)
- [x] Honest decline preserved: out-of-scope corpora with no lexical overlap still decline
- [x] Verified: `test_out_of_scope_still_declined` (Berlin headcount / weather) still passes

### G2 — Parametric answer gated behind real retrieval
- [x] `GENERAL_KNOWLEDGE` parametric branch only runs after in-scope docs were searched and found nothing on-topic (or no docs in scope)
- [x] Never overrides on-topic document/DB evidence
- [x] Loud `_GK_DISCLAIMER` prepended to every parametric answer; synthetic evidence relabelled "ungrounded"
- [x] `hallucination_risk_score` for parametric answers raised 0.3 → 0.5

### G3 — Tolerant route coercion for weak models
- [x] `_coerce_route(data, fallback)` — validates route enum, clamps confidence to [0,1], fills missing/typed-wrong fields from `rule_route`, never raises
- [x] Replaces the bare `RouteDecision(**data)` that crashed on a missing required field

### G4 — Retry + rule-vs-LLM reconciliation (live-only)
- [x] One retry with a terser directive prompt on malformed/low-confidence (`< 0.6`) routing
- [x] Low-confidence `GENERAL_KNOWLEDGE`/`NONE` overridden toward the grounded rule-layer route (`PDF`/`SQL`/`HYBRID`) — never the reverse
- [x] `NONE → GENERAL_KNOWLEDGE` upgrade moved AFTER reconciliation; only when the rule layer also found no in-scope source
- [x] All gated behind `use_live_llm` + `call.mode == "live"` → offline/cached paths byte-identical

### G5 — Config & local-model defaults
- [x] `router_low_confidence_threshold: float = 0.6`, `router_rule_override: bool = True`
- [x] `local_model` default aligned to `qwen2.5:7b-instruct` (matches `scripts/local-model.sh`); bump via `ABA_LOCAL_MODEL`

### G7 — Agent-mode grounding-first (LangGraph path)
- [x] No evidence gathered → `run_agent` falls back to the classic grounding-first `orch.ask` (fixes "Who is the nurse?" → GENERAL_KNOWLEDGE fabrication)
- [x] Evidence gathered → final answer produced by reliable `generate_answer` over collected evidence (enforces citations, kills fabricated dates + off-topic GLOBEX leak in Sources)
- [x] `_build_response` verification combines declared + inline citations (fixes false "citations unverified")
- [x] `tests/test_agent_grounding.py`; live-verified in agent mode (Roberts / Feldman / correct meds, only nursing_home_.pdf cited, zero fabrication)

### G6 — Grounded advice for recommendation questions
- [x] `is_advice_question()` (`retrieval/intent.py`) detects recommend/advise/should/is-it-safe questions
- [x] `generate_grounded_advice()` (`generation/generate.py`) — two-part PROSE answer: PART 1 grounded + cited from the subject's record, PART 2 clearly-labelled general guidance led by a forced disclaimer; never fabricates, never bare-declines
- [x] Orchestrator resolves the subject from conversation history (pronoun "him" → Mohammad Ben), retrieves his context, and routes advice questions here instead of declining
- [x] Live-verified on local model: "would you recommend smokeless tobacco to him?" → grounds dementia [e1] + disclaimed guidance advising against it; zero fabricated staff/meds

## Frontend — trust correctness + visual polish

### U1 — Ungrounded answers are loud
- [x] `GENERAL_KNOWLEDGE` → prominent amber/rose "not grounded — model knowledge, may be inaccurate" banner (was a subtle blue info line)
- [x] `VerificationBadge` GK state is a warning pill, never a calm/positive state
- [x] Hallucination risk % surfaced for parametric / high-risk answers

### U2 — Honest confidence labelling
- [x] Confidence relabelled **router confidence** with a tooltip clarifying it is not answer correctness

### U3 — Historical turns
- [x] Reloaded turns show a "not re-verified" indicator (never indistinguishable from a verified answer)

### U4 — Truncation honesty
- [x] Indicators for capped SQL rows / compact evidence ("+N more…")

### U5 — Visual polish
- [x] Spacing/typography, cohesive light+dark palette, refined chat bubbles + composer, clearer route/trust pills, better empty/loading/streaming/error states, cleaner header, more legible explainability/trace panels
- [x] Only existing `ui/lib/types.ts` fields used; `tsc --noEmit` + `next build` clean

## Tests & docs

- [x] `tests/test_grounding_first.py` — forced-GK still grounds; no fabricated values; OOS declined/disclaimed
- [x] `tests/test_router_robustness.py` — coercion survives garbage; low-conf GK reconciled; confident GK respected
- [x] `tests/test_nursing_home_red_team.py` — grounded facts correct; never-fabricate invariant; OOS declines
- [x] `scripts/eval.py` — grounding-first regression line; HYBRID stays ev=9
- [x] `docs/grounding-first-fix.md` — incident + PDF comparison + root cause
- [x] `IMPLEMENTATION_PLAN.md` + `task.md` regenerated for this round

## Stack

- [x] Rebuilt & restarted (`docker compose up -d --build`), `/health` OK, flipped to local mode (`qwen2.5:7b-instruct`)
- [x] Live E2E on local model: the incident question now grounds correctly (Donepezil 10mg, Metformin, Lisinopril, Acetaminophen, Vitamin D; nurses Roberts & Tran) — zero fabricated values; "capital of France" answers with the loud not-grounded disclaimer (risk 0.5)
- [x] UI: `NONE`-route answers recovered by the safety net show a "recovered from documents" chip (no more "Insufficient evidence" badge over a grounded answer)
