"""Deep research — provider-agnostic agentic iterative retrieval (Phase 4).

The headline loop: retrieve → **sufficiency check** → reformulate / target the gaps →
retrieve more → repeat (bounded) → answer. Unlike the LangGraph agent (which needs a
live OpenAI-compatible endpoint), this controller drives the existing sources
deterministically, so it runs identically with Claude, any OpenAI-compatible provider,
a local model, or fully offline — the loop's *control flow* is code, only the
sufficiency refinement and the final generation use the LLM (with the usual
deterministic fallbacks).

Guarantees preserved:
- **The tri-state wall.** The loop only collects evidence. The final answer goes
  through the same grounded generation + citation verification as every other path,
  and zero evidence after all rounds falls back to the classic grounding-first
  orchestrator (honest decline / labelled advice / labelled general knowledge).
- **Additive tracing.** The standard ``Trace`` is reconstructed (route, evidence, sql,
  document retrieval, verification) so every existing panel lights up; the iterative
  search itself is recorded in a new additive ``research_trace`` and streamed live as
  ``research_step`` SSE events — visible progress, never a silent spinner.
- **Latency guardrails.** Rounds, follow-up queries per round, total evidence, and
  wall-clock are all bounded via settings (``ABA_RESEARCH_*``).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from app.agent.sufficiency import (assess_sufficiency, heuristic_verdict,
                                   wants_corpus_spread)
from app.agent.tools import AgentRunContext
from app.config import get_settings
from app.generation.analysis import (attach_trust_factors, compute_contributions,
                                     compute_hallucination_risk, detect_contradictions)
from app.generation.generate import (generate_answer, generate_answer_stream,
                                     generate_grounded_advice)
from app.generation.verify import verify_citations
from app.models import (AskResponse, GenerationStep, StageTiming, Trace)
from app.pricing import summarize
from app.retrieval.intent import detect_reasoning_mode
from app.routing.classify import classify

log = logging.getLogger("aba.research")


def run_deep_research(orch, question: str,
                      allowed_docs: Optional[list[str]] = None,
                      allowed_tables: Optional[list[str]] = None,
                      role: Optional[str] = None,
                      output_mode: str = "Standard Response",
                      custom_system_prompt: Optional[str] = None,
                      agent_role: Optional[str] = None,
                      output_format: Optional[str] = "auto",
                      temperature: Optional[float] = None,
                      conversation_history: Optional[list[dict]] = None,
                      on_token=None, on_event=None) -> AskResponse:
    s = get_settings()
    t0 = time.perf_counter()
    ctx = AgentRunContext(orch, allowed_docs, allowed_tables)

    def _emit(data: dict) -> None:
        if on_event:
            try:
                on_event("research_step", data)
            except Exception:
                pass

    # The in-scope corpus (for the spread requirement + per-document targeting).
    if allowed_docs is not None:
        target_docs = list(allowed_docs)
    else:
        target_docs = list(orch.documents.documents)

    _emit({"kind": "start", "max_rounds": s.research_max_rounds,
           "documents_in_scope": len(target_docs)})

    # ---- round 1: route-aware initial retrieval -----------------------------------
    decision, route_call = classify(question, orch.capability_brief, agent_role=agent_role,
                                    conversation_history=conversation_history)
    ctx.calls.append(route_call)

    rounds: list[dict] = []
    seen_queries: set[tuple] = set()
    round_no = 1
    actions: list[dict] = []

    if decision.route in ("SQL", "HYBRID"):
        actions.append(_run_sql(ctx, decision.sql_subquery or question, round_no, _emit))
    # Grounding-first: always search the in-scope documents on the ORIGINAL question
    # (the safety-net lesson — a router rewrite must never defeat retrieval).
    actions.append(_search_documents(ctx, question, None, round_no, _emit,
                                     languages=decision.languages))
    seen_queries.add((question.lower(), ()))
    rounds.append({"round": round_no, "actions": [a for a in actions if a], "verdict": None})

    # ---- iterate: assess → reformulate → retrieve more ----------------------------
    stop_reason = "max_rounds"
    while True:
        verdict = assess_sufficiency(question, ctx.evidence, target_documents=target_docs,
                                     settings=s)
        if verdict.call:
            ctx.calls.append(verdict.call)
        rounds[-1]["verdict"] = verdict.as_dict()
        _emit({"kind": "assess", "round": round_no, "sufficient": verdict.sufficient,
               "coverage": round(verdict.coverage, 3),
               "missing_terms": verdict.missing_terms[:6],
               "missing_documents": verdict.missing_documents,
               "note": verdict.reasoning, "source": verdict.source})

        if verdict.sufficient:
            stop_reason = "sufficient"
            break
        if round_no >= s.research_max_rounds:
            stop_reason = "max_rounds"
            break
        if (time.perf_counter() - t0) > s.research_time_budget_seconds:
            stop_reason = "time_budget"
            break
        if len(ctx.evidence) >= s.research_max_evidence:
            stop_reason = "evidence_cap"
            break

        queries = []
        for nq in verdict.next_queries:
            key = (nq.query.lower(), tuple(sorted(nq.documents or [])))
            if key in seen_queries:
                continue
            seen_queries.add(key)
            queries.append(nq)
            if len(queries) >= s.research_queries_per_round:
                break
        if not queries:
            stop_reason = "exhausted"
            break

        round_no += 1
        actions = []
        for nq in queries:
            actions.append(_search_documents(ctx, nq.query, nq.documents, round_no, _emit,
                                             reason=nq.reason))
        actions = [a for a in actions if a]
        rounds.append({"round": round_no, "actions": actions, "verdict": None})
        if sum(a.get("added", 0) for a in actions) == 0:
            stop_reason = "no_progress"
            break

    docs_covered = sorted({e.document for e in ctx.evidence if e.document})
    research_trace = {
        "question": question,
        "rounds": rounds,
        "total_rounds": len(rounds),
        "stop_reason": stop_reason,
        "documents_covered": docs_covered,
        "target_documents": target_docs if wants_corpus_spread(question) else None,
        "evidence_count": len(ctx.evidence),
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    _emit({"kind": "done", "stop_reason": stop_reason, "rounds": len(rounds),
           "evidence": len(ctx.evidence), "documents": len(docs_covered)})

    # ---- nothing usable found: hand over to the classic grounding-first pipeline --
    # Retrieval always returns SOMETHING (top-k), so evidence that shares not a single
    # content term with the question is off-topic junk, not grounding — the same
    # deterministic relevance gate the orchestrator's safety net applies. Either way
    # the classic path takes over (honest decline / labelled advice / labelled general
    # knowledge — the tri-state wall holds).
    off_topic = False
    if ctx.evidence:
        hv = heuristic_verdict(question, ctx.evidence, None, s)
        off_topic = hv.coverage == 0.0 and bool(hv.missing_terms)
    if not ctx.evidence or off_topic:
        if off_topic:
            research_trace["stop_reason"] = "off_topic"
            _emit({"kind": "off_topic", "note": "Retrieved passages share no content "
                   "term with the question — declining to ground an answer in them."})
        log.info("deep research found no usable evidence (off_topic=%s) — falling back "
                 "to the classic path", off_topic)
        resp = orch.ask(
            question, allowed_docs=allowed_docs, allowed_tables=allowed_tables,
            role=role, output_mode=output_mode, custom_system_prompt=custom_system_prompt,
            agent_role=agent_role, output_format=output_format, temperature=temperature,
            conversation_history=conversation_history, on_token=on_token,
        )
        resp.trace.notes.insert(
            0, f"Deep research ran {len(rounds)} retrieval round(s) but found "
               + ("only off-topic passages" if off_topic else "no evidence")
               + "; answered via the classic grounding-first pipeline (ground or decline)."
        )
        resp.trace.research_trace = research_trace
        resp.research_trace = research_trace
        return resp

    # ---- final grounded answer over EVERYTHING collected --------------------------
    # Reasoning mode (Phase 5): a design/advice question over the researched evidence
    # gets the same two-part treatment as the classic path (cited Part 1 + labelled
    # guidance → reasoned); an analysis question gets the document-intelligence
    # directive (stays grounded). Plain factual questions are unchanged.
    reasoning_mode = detect_reasoning_mode(question)
    if reasoning_mode in ("advice", "design"):
        answer, cited, insufficient, gen_call = generate_grounded_advice(
            question, ctx.evidence, role=role, output_mode=output_mode,
            custom_system_prompt=custom_system_prompt, agent_role=agent_role,
            output_format=output_format, temperature=temperature,
            conversation_history=conversation_history,
            mode=reasoning_mode, on_token=on_token,
        )
    elif on_token:
        answer, cited, insufficient, gen_call = generate_answer_stream(
            question, ctx.evidence, on_token=on_token, role=role, output_mode=output_mode,
            custom_system_prompt=custom_system_prompt, agent_role=agent_role,
            output_format=output_format, temperature=temperature,
            conversation_history=conversation_history,
            reasoning_mode=reasoning_mode or None,
        )
    else:
        answer, cited, insufficient, gen_call = generate_answer(
            question, ctx.evidence, role=role, output_mode=output_mode,
            custom_system_prompt=custom_system_prompt, agent_role=agent_role,
            output_format=output_format, temperature=temperature,
            conversation_history=conversation_history,
            reasoning_mode=reasoning_mode or None,
        )
    if gen_call:
        ctx.calls.append(gen_call)

    return _build_response(
        question, answer, ctx, decision, research_trace, rounds,
        role, output_mode, t0, declared_cited=cited, insufficient=insufficient,
        reasoning_mode=reasoning_mode or None,
    )


# -- retrieval actions ---------------------------------------------------------------

def _search_documents(ctx: AgentRunContext, query: str,
                      documents: Optional[list[str]], round_no: int, _emit,
                      languages: Optional[list[str]] = None,
                      reason: str = "") -> Optional[dict]:
    """One document search recorded into the run context (same shape as the agent's
    ``search_documents`` tool, so the standard trace panels light up unchanged)."""
    if ctx.allowed_docs is not None and len(ctx.allowed_docs) == 0:
        return None
    filters: dict = {}
    docs: Optional[list[str]] = None
    if documents:
        docs = [d for d in documents
                if ctx.allowed_docs is None or d in set(ctx.allowed_docs)]
        if not docs:
            return None
        filters["documents"] = docs
    elif ctx.allowed_docs:
        filters["documents"] = ctx.allowed_docs
    if languages:
        filters["languages"] = languages

    ev, dtrace = ctx.orch.documents.retrieve(query, filters=filters)
    if ctx.document_retrieval is None:
        ctx.document_retrieval = dtrace
    else:
        ctx.document_retrieval.candidates += dtrace.candidates
    before = len(ctx.evidence)
    ids = ctx.add_evidence(ev)
    added = len(ctx.evidence) - before
    obs = f"{len(ev)} passage(s), {added} new"
    ctx.steps.append({
        "iteration": len(ctx.steps) + 1, "tool": "search_documents",
        "args": {"query": query, **({"documents": docs} if docs else {})},
        "observation": obs, "evidence_ids": ids,
    })
    action = {"tool": "search_documents", "query": query, "found": len(ev),
              "added": added, **({"documents": docs} if docs else {}),
              **({"reason": reason} if reason else {})}
    _emit({"kind": "search", "round": round_no, **action,
           "total_evidence": len(ctx.evidence)})
    return action


def _run_sql(ctx: AgentRunContext, query: str, round_no: int, _emit) -> Optional[dict]:
    """One structured lookup recorded into the run context (mirrors the agent's
    ``sql_query`` tool)."""
    if ctx.allowed_tables is not None and len(ctx.allowed_tables) == 0:
        return None
    ev, strace, call = ctx.orch.relational.run(
        query, purpose="research_sql", allowed_tables=ctx.allowed_tables
    )
    if call:
        ctx.calls.append(call)
    ctx.sql_executions.append(strace)
    before = len(ctx.evidence)
    ids = ctx.add_evidence(ev)
    added = len(ctx.evidence) - before
    obs = (f"{strace.row_count} row(s), {added} new" if strace.valid
           else f"SQL failed: {strace.validation_error}")
    ctx.steps.append({
        "iteration": len(ctx.steps) + 1, "tool": "sql_query",
        "args": {"query": query}, "observation": obs, "evidence_ids": ids,
    })
    action = {"tool": "sql_query", "query": query,
              "found": strace.row_count if strace.valid else 0, "added": added}
    _emit({"kind": "search", "round": round_no, **action,
           "total_evidence": len(ctx.evidence)})
    return action


# -- response assembly ---------------------------------------------------------------

def _build_response(question, answer, ctx: AgentRunContext, decision, research_trace,
                    rounds, role, output_mode, t0, declared_cited=None,
                    insufficient=False, reasoning_mode=None) -> AskResponse:
    """Rebuild the standard ``Trace`` (same shape as the classic orchestrator + agent
    runner) and run the identical verification/explainability chokepoints."""
    trace = Trace(question=question)
    trace.role = role
    trace.output_mode = output_mode
    trace.reasoning_mode = reasoning_mode
    trace.route = decision
    trace.languages = decision.languages
    trace.notes.append(
        f"Deep research — {len(rounds)} retrieval round(s), "
        f"{len(ctx.evidence)} evidence item(s) from "
        f"{len(research_trace['documents_covered'])} document(s); "
        f"stop: {research_trace['stop_reason']}."
    )
    trace.generation_steps.append(GenerationStep(
        step="routing", decision=decision.route, confidence=decision.confidence,
        duration_ms=0.0,
    ))

    trace.evidence = ctx.evidence
    trace.sql_executions = ctx.sql_executions
    trace.document_retrieval = ctx.document_retrieval
    for strace in ctx.sql_executions:
        trace.generation_steps.append(GenerationStep(
            step="sql_generation",
            decision="valid" if strace.valid else "invalid",
            duration_ms=strace.duration_ms,
            details={"sql": strace.validated_sql or strace.generated_sql,
                     "rows_returned": strace.row_count, "purpose": strace.purpose},
        ))
    if ctx.document_retrieval is not None:
        dr = ctx.document_retrieval
        trace.generation_steps.append(GenerationStep(
            step="document_retrieval", duration_ms=0.0,
            details={"candidates": len(dr.candidates),
                     "after_rerank": len([c for c in dr.candidates if c.selected]),
                     "intent": dr.intent},
        ))
    for r in rounds:
        trace.generation_steps.append(GenerationStep(
            step="research_round", decision=f"round {r['round']}", duration_ms=0.0,
            details={"queries": [a.get("query") for a in r["actions"]],
                     "added": sum(a.get("added", 0) for a in r["actions"]),
                     "verdict": r.get("verdict")},
        ))
    trace.generation_steps.append(GenerationStep(
        step="generation", decision="deep_research", duration_ms=0.0,
        details={"evidence_items": len(ctx.evidence)},
    ))

    # verification + explainability — identical functions to every other path.
    inline = re.findall(r"\[(e\d+)\]", answer)
    cited = sorted(set(declared_cited or []) | set(inline), key=lambda x: int(x[1:]))
    check = verify_citations(answer, cited, ctx.evidence)
    trace.citation_check = check
    cited_ids = set(check.cited_ids)
    for e in ctx.evidence:
        e.used = e.id in cited_ids
    compute_contributions(answer, ctx.evidence)
    attach_trust_factors(ctx.evidence, ctx.document_retrieval, ctx.sql_executions)
    contradictions, warning, pairs = detect_contradictions(answer, ctx.evidence, ctx.calls)
    hallucination = compute_hallucination_risk(check, contradictions, pairs)
    trace.generation_steps.append(GenerationStep(
        step="verification",
        decision="verified" if check.verified else "issues",
        duration_ms=0.0,
        details={"verified": len(check.cited_ids) - len(check.unknown_ids),
                 "unverified": len(check.unknown_ids),
                 "contradictions": len(contradictions),
                 "hallucination_risk": hallucination},
    ))
    if warning:
        answer = answer.rstrip() + (
            "\n\n⚠️ Note: Some sources contain conflicting information. "
            "See the Explainability panel for details."
        )

    trace.llm_calls = list(ctx.calls)
    trace.cost = summarize(trace.llm_calls)
    trace.mode = "live" if any(c.mode == "live" for c in trace.llm_calls) else "offline"
    trace.timings.append(StageTiming(
        name="total", duration_ms=round((time.perf_counter() - t0) * 1000, 1)))
    trace.research_trace = research_trace

    cited_set = set(check.cited_ids)
    citations = [e for e in ctx.evidence if e.id in cited_set] or ctx.evidence
    return AskResponse(
        question=question, answer=answer, insufficient=insufficient,
        citations=citations, trace=trace,
        verification_warning=warning,
        hallucination_risk_score=hallucination,
        contradictions=contradictions,
        research_trace=research_trace,
    )
