"""Run the LangGraph agent and rebuild the standard Trace from it.

The agent loops over tools; afterwards we reconstruct the SAME ``Trace`` shape the
classic orchestrator produces (route, evidence, sql_executions, document_retrieval,
generation_steps) and run the EXISTING verification + explainability analysis over the
final answer. The result is an ordinary ``AskResponse`` plus an additive ``agent_trace``
timeline, so every existing UI panel lights up unchanged.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from app.config import get_settings
from app.generation.analysis import (attach_trust_factors, compute_contributions,
                                     compute_hallucination_risk, detect_contradictions)
from app.generation.generate import _get_system_prompt
from app.generation.verify import verify_citations
from app.models import (AskResponse, GenerationStep, LLMCall, RouteDecision, StageTiming,
                        Trace)
from app.pricing import summarize

log = logging.getLogger("aba.agent")

_AGENT_PREAMBLE = (
    "\n\nYOU ARE AN ITERATIVE AGENT.\n"
    "You have tools: `sql_query` (structured business database) and `search_documents` "
    "(the uploaded PDFs). Work step by step: decide what you still need, call a tool to "
    "get it, read the observation, then decide the next step. You may call tools multiple "
    "times and combine them. When you have enough evidence, STOP calling tools and write "
    "the final answer.\n"
    "Ground every factual claim ONLY in the evidence the tools return, and cite it inline "
    "with the evidence id(s) shown in the observations, e.g. [e1] or [e2][e5]. If the "
    "tools cannot supply enough evidence, say so honestly rather than guessing."
)

_RECURSION_LIMIT = 14  # ~6 tool rounds (agent+tools = 2 supersteps each) + final answer


def agent_available() -> bool:
    """True only when the agent can really run: deps importable + a live OpenAI-compatible
    LLM configured. Otherwise the engine uses the classic path."""
    s = get_settings()
    if not s.use_live_llm or s.llm_provider != "openai":
        return False
    try:
        import langgraph  # noqa: F401
        import langchain_openai  # noqa: F401
        from app.agent.graph import build_agent_graph  # noqa: F401
        return True
    except Exception:
        return False


def _history_messages(conversation_history: Optional[list[dict]]):
    from langchain_core.messages import AIMessage, HumanMessage
    msgs = []
    for turn in (conversation_history or []):
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if turn.get("role") == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(HumanMessage(content=content))
    return msgs


def run_agent(orch, question: str,
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
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from app.agent.graph import build_agent_graph
    from app.agent.tools import AgentRunContext

    s = get_settings()
    t0 = time.perf_counter()
    ctx = AgentRunContext(orch, allowed_docs, allowed_tables)

    system_prompt = _get_system_prompt(
        role, output_mode, custom_system_prompt=custom_system_prompt,
        agent_role=agent_role, output_format=output_format,
    ).replace("Return JSON only.", "").rstrip() + _AGENT_PREAMBLE

    messages = ([SystemMessage(content=system_prompt)]
                + _history_messages(conversation_history)
                + [HumanMessage(content=question)])

    graph = build_agent_graph(ctx, s.model_generation, s, temperature)

    agent_calls: list[LLMCall] = []
    final_answer = ""
    iterations = 0

    def _emit(event: str, data: dict) -> None:
        if on_event:
            try:
                on_event(event, data)
            except Exception:
                pass

    try:
        for update in graph.stream(
            {"messages": messages},
            config={"recursion_limit": _RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for node, delta in update.items():
                new_msgs = (delta or {}).get("messages", []) if isinstance(delta, dict) else []
                for m in new_msgs:
                    if isinstance(m, AIMessage):
                        # account tokens for this agent LLM step
                        um = getattr(m, "usage_metadata", None) or {}
                        if um:
                            from app.pricing import call_cost
                            it, ot = um.get("input_tokens"), um.get("output_tokens")
                            agent_calls.append(LLMCall(
                                purpose="agent", model=s.model_generation, mode="live",
                                input_tokens=it, output_tokens=ot,
                                cost_usd=call_cost(s.model_generation, it or 0, ot or 0),
                            ))
                        tool_calls = getattr(m, "tool_calls", None) or []
                        if tool_calls:
                            iterations += 1
                            for tc in tool_calls:
                                _emit("agent_step", {
                                    "iteration": iterations,
                                    "tool": tc.get("name"),
                                    "args": tc.get("args", {}),
                                })
                        elif isinstance(m.content, str) and m.content.strip():
                            final_answer = m.content.strip()
                    else:  # ToolMessage observation
                        obs = getattr(m, "content", "")
                        _emit("agent_observation", {
                            "tool": getattr(m, "name", None),
                            "summary": (obs or "")[:400],
                        })
    except Exception as exc:  # recursion limit hit or transient agent failure
        log.warning("agent run ended early: %s", exc)

    if not final_answer:
        final_answer = ("I could not complete the agent reasoning for this question. "
                        "Please try rephrasing it.") if not ctx.evidence else (
            "Based on the gathered evidence, I was unable to compose a final answer.")

    # stream the final answer to the live sink (chunked — the loop produced it whole)
    if on_token and final_answer:
        for i in range(0, len(final_answer), 24):
            on_token(final_answer[i:i + 24])

    return _build_response(question, final_answer, ctx, agent_calls, iterations,
                           role, output_mode, t0)


def _infer_route(ctx) -> str:
    used_sql = any(st["tool"] == "sql_query" for st in ctx.steps)
    used_doc = any(st["tool"] == "search_documents" for st in ctx.steps)
    if used_sql and used_doc:
        return "HYBRID"
    if used_sql:
        return "SQL"
    if used_doc:
        return "PDF"
    return "GENERAL_KNOWLEDGE"


def _build_response(question, answer, ctx, agent_calls, iterations,
                    role, output_mode, t0) -> AskResponse:
    import re

    trace = Trace(question=question)
    trace.role = role
    trace.output_mode = output_mode
    route = _infer_route(ctx)
    tools_used = sorted({st["tool"] for st in ctx.steps})
    trace.route = RouteDecision(
        route=route,
        reasoning=f"Iterative agent: {iterations} tool round(s) over {', '.join(tools_used) or 'no tools'}.",
        confidence=0.8 if ctx.evidence else 0.4,
    )
    trace.notes.append(
        f"Agent mode — {iterations} reasoning step(s); tools used: {', '.join(tools_used) or 'none'}."
    )
    trace.generation_steps.append(GenerationStep(
        step="routing", decision=route, confidence=trace.route.confidence, duration_ms=0.0,
    ))

    # evidence (already labeled e1..eN by the context) + retrieval/sql traces
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
    for st in ctx.steps:
        trace.generation_steps.append(GenerationStep(
            step="agent_tool", decision=st["tool"], duration_ms=0.0,
            details={"iteration": st["iteration"], "args": st["args"],
                     "observation": st["observation"]},
        ))
    trace.generation_steps.append(GenerationStep(
        step="generation", decision="agent", duration_ms=0.0,
        details={"evidence_items": len(ctx.evidence)},
    ))

    # verification + explainability — identical functions to the classic path
    cited = sorted(set(re.findall(r"\[(e\d+)\]", answer)), key=lambda x: int(x[1:]))
    check = verify_citations(answer, cited, ctx.evidence)
    trace.citation_check = check
    cited_ids = set(check.cited_ids)
    for e in ctx.evidence:
        e.used = e.id in cited_ids
    compute_contributions(answer, ctx.evidence)
    attach_trust_factors(ctx.evidence, ctx.document_retrieval, ctx.sql_executions)
    all_calls = list(ctx.calls) + list(agent_calls)
    contradictions, warning, pairs = detect_contradictions(answer, ctx.evidence, all_calls)
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

    trace.llm_calls = all_calls
    trace.cost = summarize(all_calls)
    trace.mode = "live" if all_calls else "offline"
    trace.timings.append(StageTiming(name="total", duration_ms=round((time.perf_counter() - t0) * 1000, 1)))

    agent_trace = {
        "original_question": question,
        "iterations": iterations,
        "tools_used": tools_used,
        "steps": ctx.steps,
    }
    trace.agent_trace = agent_trace

    cited_set = set(check.cited_ids)
    citations = [e for e in ctx.evidence if e.id in cited_set] or ctx.evidence
    return AskResponse(
        question=question, answer=answer, insufficient=not ctx.evidence,
        citations=citations, trace=trace,
        verification_warning=warning,
        hallucination_risk_score=hallucination,
        contradictions=contradictions,
        agent_trace=agent_trace,
    )
