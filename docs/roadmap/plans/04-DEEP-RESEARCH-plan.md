# Phase 4 plan — Agentic iterative retrieval ("deep research")

Roadmap: [03-ROADMAP.md](../03-ROADMAP.md) Phase 4 · Backlog: [04-BACKLOG.md](../04-BACKLOG.md)

## Exit criteria being satisfied

> A question needing evidence from many documents is answered correctly and cited, and
> the panel *shows* the iterative search that got there. Latency guardrails + visible
> progress (never a silent long spinner). Eval: multi-hop and "answer spread across many
> docs" cases.

## Design decision (the one that matters)

The roadmap says "extend the LangGraph agent", but `agent_available()` requires an
OpenAI-compatible provider — the live deployment runs Anthropic (or offline), so a
LangGraph-only implementation would be **invisible on the demo** and untestable offline.

Therefore the headline loop is a **provider-agnostic deep-research controller**
(`app/agent/research.py`) that drives the *existing* sources iteratively —
retrieve → sufficiency check → reformulate → retrieve more → answer — and works
identically live (any provider) and offline (deterministic heuristics). The LangGraph
path *additionally* gets a sufficiency gate so agent-mode users benefit too.

The tri-state wall is untouched: the loop only **collects evidence**; the final answer
still goes through the same `generate_answer` → `verify_citations` →
`compute_answer_state` chokepoints. Zero evidence after all rounds → fall back to the
classic grounding-first orchestrator (honest decline / labelled advice / labelled GK).

## Changes

### Backend

1. **`app/agent/sufficiency.py`** (new) — sufficiency check + reformulation.
   - Deterministic core (always runs; is the offline path AND the live fallback):
     - *term coverage*: `content_terms(question)` vs accumulated evidence text →
       coverage ratio + missing terms.
     - *aspect coverage*: split multi-part questions on connectors; an uncovered aspect
       becomes a reformulated sub-query.
     - *corpus spread*: "across all / each / every / compare …" + a doc-target noun →
       require evidence from multiple in-scope documents; unrepresented documents get
       per-document targeted queries.
   - Live enhancement: `llm.structured(...)` (any provider) refines the verdict
     {sufficient, missing, next_queries}; deterministic verdict is the fallback.
2. **`app/agent/research.py`** (new) — `run_deep_research(orch, question, …)`.
   - Reuses `AgentRunContext` (evidence dedup + stable e1..eN ids + step log).
   - Round 1: `classify()` route-aware retrieval (SQL and/or documents).
   - Loop (bounded): sufficiency verdict → run `next_queries` as document searches
     (scoped filters respected) → repeat. Stop reasons: `sufficient`, `max_rounds`,
     `time_budget`, `no_progress`.
   - Emits `research_step` events (via `on_event`) per round for live progress.
   - Final answer: `generate_answer_stream` (live sink) / `generate_answer` over ALL
     collected evidence; then the same verification/explainability as the agent runner.
   - Trace: additive `Trace.research_trace` + `AskResponse.research_trace`
     (rounds, queries, verdicts, stop reason) — existing panels unchanged.
3. **`app/models.py`** — `research_trace: Optional[dict]` on `Trace` + `AskResponse`;
   `deep_research: bool = False` on `AskRequest`.
4. **`app/engine.py`** — `deep_research` param; routes to `run_deep_research` (before
   agent/multi-agent); `_finalize` unchanged (wall + components for free).
5. **`app/api/routes.py`** — pass `deep_research` through `/ask`, `/ask/stream`,
   regenerate. SSE already forwards arbitrary events.
6. **`app/config.py`** — guardrail knobs: `research_max_rounds=3`,
   `research_queries_per_round=3`, `research_time_budget_seconds=25`,
   `research_min_coverage=0.7`.
7. **`app/agent/graph.py` / `runner.py`** — sufficiency-check node in the LangGraph
   graph: when the model stops calling tools, assess evidence; if insufficient and
   passes remain, inject a steering message ("missing X — search for Y") and loop back
   to the agent node (bounded). Recorded in `agent_trace` + emitted as `agent_step`.

### Frontend

8. **`ui/lib/types.ts`** — `ResearchRound`/`ResearchTrace`; `research_trace` on
   `Trace`/`AskResponse`; `deep_research` on `AskOptions`.
9. **`ui/lib/api.ts`** — send `deep_research`; parse `research_step` SSE →
   `onResearchStep`.
10. **`ui/components/AiSettingsPanel.tsx`** — `deepResearch` in the settings store.
11. **`ui/components/Composer.tsx`** — a "Deep research" toggle chip (ChatGPT-style)
    next to Customize; hint chip when active. Also a toggle in `CustomizePanel`/
    `SettingsPanel` beside Agent mode / Multi-agent.
12. **`ui/components/ChatThread.tsx`** — `StreamingAssistant` renders the live
    research timeline (round · query · found · coverage · missing) while streaming —
    visible progress, never a silent spinner.
13. **`ui/components/Inspector.tsx`** — "Deep research" collapsible in the Trace tab:
    full per-round timeline (queries, new evidence, verdict, stop reason).

### Eval & tests

14. **`scripts/eval.py`** — Phase-4 block (offline-deterministic):
    - *evidence spread*: "What do the agreements say about suspension across ALL
      customer contracts?" via `deep_research=True` → grounded + cited, evidence
      spanning ≥ 2 distinct documents, `research_trace` shows > 1 round.
    - *wall check*: out-of-scope deep-research question stays `insufficient`.
15. **`tests/test_deep_research.py`** — sufficiency heuristics (coverage / spread /
    aspects), bounded loop + stop reasons, research_trace shape, `research_step`
    events, tri-state wall (no fabrication when nothing is found), engine flag
    plumbing.

## Status

- [x] Plan written
- [x] Sufficiency module (`app/agent/sufficiency.py`)
- [x] Deep-research controller + trace + events (`app/agent/research.py`)
- [x] Engine/API plumbing + `ABA_RESEARCH_*` config knobs
- [x] LangGraph sufficiency gate (`graph.py` sufficiency node, bounded steer)
- [x] UI (composer toggle + settings toggles, live round timeline while streaming,
      "Deep research" panel in the inspector Trace tab)
- [x] Eval + tests green offline (pytest 207 passed incl. 11 new; scripts/eval 14/14)
- [x] tsc + next build green (via the /home clone workflow)
- [x] Live-site verification (2026-07-17): https://assistant.lazysnail.xyz loads,
      `/api/health` green; a deep-research ask streamed 13 `research_step` events
      (3 rounds, live-LLM sufficiency refinement, per-round searches) then a grounded,
      citation-verified answer over 5 documents in 12.3 s; the out-of-scope wall check
      declined with `stop: off_topic`; the deployed UI bundle serves the Deep research
      chip, live timeline, and inspector panel.
