"""Multi-agent reasoning (Section 10).

For multi-part questions we decompose into 2–4 sub-questions, run the FULL pipeline for
each independently (concurrently), then synthesize one coherent, cited answer. The
``multi_agent_trace`` exposes the whole tree to the Explainability panel.

The sub-questions are executed via ``Orchestrator.ask`` (which does NOT take the engine
lock), so it is safe to fan out with a thread pool — the LLM/HTTP calls are I/O-bound, so
threads give real concurrency.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.config import get_settings
from app.generation.analysis import (attach_trust_factors, compute_contributions,
                                     compute_hallucination_risk, detect_contradictions)
from app.generation.verify import verify_citations
from app.llm.client import get_llm
from app.models import (AskResponse, CostSummary, Evidence, GenerationStep, LLMCall,
                        RouteDecision, StageTiming, Trace)
from app.pricing import summarize

log = logging.getLogger("aba.multi_agent")

_DECOMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sub_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sub_questions"],
}

_SYNTH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "synthesis_reasoning": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "synthesis_reasoning", "citations"],
}

_QUESTION_WORDS = re.compile(r"\b(and|also|additionally|as well as|plus|furthermore)\b", re.I)


def is_multipart(question: str) -> bool:
    """Heuristic trigger: more than two sentences, or a conjunction joining clauses in a
    reasonably long question."""
    sentences = [s for s in re.split(r"[.?!]+", question) if s.strip()]
    if len(sentences) > 2:
        return True
    if _QUESTION_WORDS.search(question) and len(question.split()) >= 12:
        return True
    return False


def _decompose(question: str) -> tuple[list[str], Optional[LLMCall]]:
    s = get_settings()
    llm = get_llm()
    data, call = llm.structured(
        purpose="decomposition",
        model=s.model_router,
        system=("Decompose a complex question into 2–4 minimal, independent sub-questions "
                "that together fully cover it. Keep each self-contained. If the question is "
                "already simple, return it unchanged as a single item. JSON only."),
        user=f"Question: {question}",
        schema=_DECOMPOSE_SCHEMA,
        fallback=lambda: {"sub_questions": _rule_split(question)},
        max_tokens=300,
    )
    subs = [q.strip() for q in (data.get("sub_questions") or []) if q.strip()]
    return (subs or [question])[:4], call


def _rule_split(question: str) -> list[str]:
    """Offline fallback: split on ' and ' / sentence boundaries."""
    parts = re.split(r"\band\b|[.?!]+", question)
    parts = [p.strip() for p in parts if len(p.strip()) > 8]
    return parts[:4] if len(parts) >= 2 else [question]


def _evidence_block(evidence: list[Evidence]) -> str:
    return "\n\n".join(f"{e.id} {e.citation_label}\n{e.content}" for e in evidence)


def run_multi_agent(
    orch, question: str,
    allowed_docs: Optional[list[str]], allowed_tables: Optional[list[str]],
    role: Optional[str], output_mode: str,
    custom_system_prompt: Optional[str], agent_role: Optional[str],
    output_format: Optional[str],
    temperature: Optional[float] = None,
    conversation_history: Optional[list[dict]] = None,
) -> AskResponse:
    t0 = time.perf_counter()
    calls: list[LLMCall] = []
    trace = Trace(question=question)
    trace.role = role
    trace.output_mode = output_mode

    # 1) DECOMPOSE
    ts = time.perf_counter()
    sub_questions, dcall = _decompose(question)
    if dcall:
        calls.append(dcall)
    trace.generation_steps.append(GenerationStep(
        step="decomposition", decision=f"{len(sub_questions)} sub-questions",
        duration_ms=_ms(ts), details={"sub_questions": sub_questions},
    ))

    if len(sub_questions) < 2:
        # nothing to fan out — fall back to a single normal pass
        return orch.ask(question, allowed_docs, allowed_tables, role, output_mode,
                        custom_system_prompt, agent_role, output_format,
                        temperature, conversation_history)

    # 2) PARALLEL SUB-AGENTS — each runs the full route→retrieve→generate pipeline.
    # Sub-questions are self-contained, so they don't carry the conversation history
    # (only the original question's framing matters here).
    def _run_sub(sq: str) -> AskResponse:
        return orch.ask(sq, allowed_docs, allowed_tables, role, output_mode,
                        custom_system_prompt, agent_role, output_format,
                        temperature)

    ts = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(4, len(sub_questions))) as pool:
        sub_resps = list(pool.map(_run_sub, sub_questions))

    # 3) MERGE evidence (dedupe + relabel e1..eN) and build the sub-answer tree
    merged: list[Evidence] = []
    content_to_id: dict[tuple, str] = {}
    sub_answers: list[dict] = []
    for sq, resp in zip(sub_questions, sub_resps):
        ids: list[str] = []
        for e in resp.trace.evidence:
            key = (e.source_kind, e.source_name, e.content)
            if key not in content_to_id:
                new_id = f"e{len(merged) + 1}"
                merged.append(e.model_copy(update={"id": new_id}))
                content_to_id[key] = new_id
            ids.append(content_to_id[key])
        for c in resp.trace.llm_calls:
            calls.append(c)
        sub_answers.append({
            "sub_question": sq,
            "route": resp.trace.route.route if resp.trace.route else "NONE",
            "answer": resp.answer,
            "evidence_ids": sorted(set(ids), key=lambda x: int(x[1:])),
        })
    trace.evidence = merged
    trace.generation_steps.append(GenerationStep(
        step="sub_agents", decision=f"{len(sub_resps)} answered",
        duration_ms=_ms(ts), details={"routes": [sa["route"] for sa in sub_answers]},
    ))

    # 4) SYNTHESIZE one coherent answer over the merged evidence
    ts = time.perf_counter()
    s = get_settings()
    llm = get_llm()
    sub_block = "\n\n".join(
        f"Sub-question {i+1}: {sa['sub_question']}\nAnswer: {sa['answer']}"
        for i, sa in enumerate(sub_answers)
    )
    synth, scall = llm.structured(
        purpose="synthesis",
        model=s.model_generation,
        system=("You integrate several sub-answers into ONE coherent, non-redundant final "
                "answer. Use ONLY the provided evidence and cite claims inline with [eN] "
                "ids. De-duplicate overlapping points. Also give a one-paragraph "
                "'synthesis_reasoning' explaining how the parts fit together. JSON only."),
        user=f"Original question: {question}\n\n{sub_block}\n\nEvidence:\n{_evidence_block(merged)}",
        schema=_SYNTH_SCHEMA,
        fallback=lambda: {
            "answer": "\n\n".join(f"**{sa['sub_question']}**\n{sa['answer']}" for sa in sub_answers),
            "synthesis_reasoning": "Combined the sub-answers (offline synthesis).",
            "citations": [e.id for e in merged],
        },
        max_tokens=1800,
    )
    if scall:
        calls.append(scall)
    answer = (synth.get("answer", "") or "").replace("\\n", "\n").strip()
    reasoning = synth.get("synthesis_reasoning", "")
    trace.generation_steps.append(GenerationStep(
        step="synthesis", decision="merged", duration_ms=_ms(ts),
        details={"evidence_items": len(merged)},
    ))

    # 5) VERIFY + explainability/verification analysis over the synthesized answer
    check = verify_citations(answer, list(synth.get("citations", [])), merged)
    trace.citation_check = check
    for e in merged:
        e.used = e.id in set(check.cited_ids)
    compute_contributions(answer, merged)
    # merge document candidates + sql executions across subs so trust_factors resolve
    for resp in sub_resps:
        if resp.trace.document_retrieval and not trace.document_retrieval:
            trace.document_retrieval = resp.trace.document_retrieval
        elif resp.trace.document_retrieval:
            trace.document_retrieval.candidates += resp.trace.document_retrieval.candidates
        trace.sql_executions += resp.trace.sql_executions
    attach_trust_factors(merged, trace.document_retrieval, trace.sql_executions)
    contradictions, warning, pairs = detect_contradictions(answer, merged, calls)
    hallucination = compute_hallucination_risk(check, contradictions, pairs)

    # 6) finalize — synthetic route badge + multi_agent_trace
    routes = {sa["route"] for sa in sub_answers}
    final_route = "HYBRID" if len(routes) > 1 else (routes.pop() if routes else "NONE")
    trace.route = RouteDecision(
        route=final_route,
        reasoning=f"Multi-agent: decomposed into {len(sub_questions)} sub-questions, "
                  f"answered independently, then synthesized.",
        confidence=round(sum(r.trace.route.confidence for r in sub_resps if r.trace.route)
                         / max(1, len(sub_resps)), 2),
    )
    mat = {
        "original_question": question,
        "sub_questions": sub_questions,
        "sub_answers": sub_answers,
        "synthesis_reasoning": reasoning,
    }
    trace.multi_agent_trace = mat
    trace.llm_calls = calls
    trace.cost = summarize(calls)
    trace.mode = _mode(calls)
    trace.timings.append(StageTiming(name="total", duration_ms=_ms(t0)))
    trace.notes.append(
        f"Multi-agent reasoning: {len(sub_questions)} sub-questions → synthesis."
    )

    citations = [e for e in merged if e.id in set(check.cited_ids)] or merged
    return AskResponse(
        question=question, answer=answer, insufficient=not merged,
        citations=citations, trace=trace,
        verification_warning=warning,
        hallucination_risk_score=hallucination,
        contradictions=contradictions,
        multi_agent_trace=mat,
    )


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _mode(calls: list[LLMCall]) -> str:
    modes = {c.mode for c in calls}
    if "live" in modes:
        return "live" if modes == {"live"} else "mixed"
    if "cached" in modes:
        return "cached"
    return "offline"
