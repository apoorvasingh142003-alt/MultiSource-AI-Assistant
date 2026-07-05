# Implementation Plan — Grounding-First Robustness + UI Trust Upgrade

**Branch:** `enterprise-upgrade` · **Status:** implemented & verified (see `task.md`).

**Goal of this round:** make the assistant **safe and dependable on a weak local model**.
A local Ollama run (`qwen2.5:7b-instruct`) routed a document-answerable question to
`GENERAL_KNOWLEDGE` and **fabricated** medications/staff that contradicted the uploaded
nursing-home PDF. This round makes grounding unconditional, hardens routing for small models,
makes the UI tell the truth loudly, and adds an adversarial test + red-team suite — without
regressing the API path, the 56-test baseline, or the flagship HYBRID demo (evidence = 9).

Full incident write-up + side-by-side fabrication table: `docs/grounding-first-fix.md`.

---

## 1. Root cause

A **routing-trust** problem, not a transport problem. Ollama already runs through the
unified OpenAI-compatible client (`app/llm/client.py`); the weakness is the *model*. The weak
7B router returned `GENERAL_KNOWLEDGE` (confidence 0.4), and the orchestrator had a parametric
escape hatch reachable whenever the only guard — a single-token `_on_topic()` lexical check —
dropped the recovered evidence. So a weak router could bypass retrieval and answer from
training data. **LangChain/ChatOllama would not fix this** (it does not improve structured-output
quality); the fix is architectural.

## 2. Backend — grounding-first guarantee

| ID | Area | Key files |
|----|------|-----------|
| G1 | `_on_topic()` widened (single passage → any of top-3 share a content word); honest decline preserved | `routing/orchestrator.py` |
| G2 | `GENERAL_KNOWLEDGE` parametric branch gated behind a real in-scope document search; never overrides on-topic evidence; loud disclaimer prepended; `hallucination_risk_score` 0.3 → 0.5 | `routing/orchestrator.py` |
| G3 | `_coerce_route()` — tolerant of malformed/partial 7B JSON (clamp confidence, validate enum, fill from rule layer) | `routing/classify.py` |
| G4 | One retry on malformed/low-confidence routing; rule-vs-LLM reconciliation (low-conf `GENERAL_KNOWLEDGE`/`NONE` → grounded route, never the reverse); `NONE→GK` upgrade moved after reconciliation | `routing/classify.py` |
| G5 | `router_low_confidence_threshold` (0.6), `router_rule_override` (True); `local_model` default aligned to `qwen2.5:7b-instruct` | `config.py` |
| G6 | Advice/recommendation questions → two-part **grounded context + disclaimed general guidance** (never fabricate, never bare-decline); subject resolved from conversation history | `retrieval/intent.py`, `generation/generate.py`, `routing/orchestrator.py` |

**Determinism preserved.** All new router logic is gated behind `use_live_llm` + `call.mode ==
"live"`, so offline/cached paths (the entire deterministic test suite) are byte-identical.
Reconciliation only ever *downgrades toward grounding*; it cannot push a question to the
parametric path.

## 3. Frontend — trust correctness + visual polish (`ui/`)

| ID | Area | Key files |
|----|------|-----------|
| U1 | `GENERAL_KNOWLEDGE` → prominent amber/rose "not grounded" warning banner (was a subtle blue info line); surface risk % | `components/AnswerPanel.tsx`, `components/VerificationBadge.tsx` |
| U2 | Confidence relabelled as **router** confidence (+ tooltip): it is not answer correctness | `components/AnswerPanel.tsx` |
| U3 | Historical turns show a "not re-verified" indicator (never indistinguishable from a verified answer) | `components/ChatThread.tsx` |
| U4 | Truncation indicators for capped SQL rows / compact evidence | `components/trace.tsx` |
| U5 | Visual polish: spacing/typography, cohesive light+dark palette, refined bubbles/composer/pills, clearer states, header, explainability legibility | `app/globals.css`, `components/ui.tsx`, panels |

The backend prepends the parametric disclaimer to the answer text; the UI renders it
prominently. Constraint: only fields already in `ui/lib/types.ts`; `tsc --noEmit` + `next
build` stay clean.

## 4. Local-model robustness (no LangChain migration)

Transport unchanged (`runtime.set_model_mode` keeps the OpenAI-compatible Ollama path). The
robustness layer (§2) is what makes a 7B route dependably. `langchain`/`langgraph` stay only
for the optional iterative agent. Bump the model via `ABA_LOCAL_MODEL` (e.g.
`qwen2.5:14b-instruct`) for stronger routing on more RAM.

## 5. Tests & verification

- `tests/test_grounding_first.py` (new) — forced-`GENERAL_KNOWLEDGE` still grounds in the PDF;
  no fabricated values; out-of-scope is declined or loudly disclaimed.
- `tests/test_router_robustness.py` (new) — `_coerce_route` survives garbage; low-conf GK
  reconciles to grounded; confident GK respected.
- `tests/test_nursing_home_red_team.py` (new) — adversarial Q&A over the real PDF: correct
  grounded facts, never-fabricate invariant, out-of-scope declines.
- `scripts/eval.py` — grounding-first regression line added; flagship HYBRID stays at ev = 9.
- **Suite: 108 passed, 10 skipped** (was 56/10). `scripts/eval.py` 10/10. UI `tsc` + `next
  build` clean. Live local-mode E2E: meds question grounds (Donepezil 10 mg, Metformin,
  Lisinopril, Acetaminophen, Vitamin D); "capital of France" answers with the loud disclaimer.

---

## Appendix — previous round (enterprise agentic-chat upgrade)

The prior round turned the single-shot RAG engine into a ChatGPT-like **agentic, multi-turn,
streaming** assistant: per-request temperature, multi-turn conversation context, message
edit/delete/regenerate, real token streaming, an optional LangGraph iterative agent (wrapping
the existing sources as tools), structure-aware semantic chunking, German multilingual
showcase, a single settings store, and a merged Output control. That work remains intact and
unregressed; this round is additive on top of it.
