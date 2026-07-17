"""The LangGraph state machine: agent ⇄ tools loop + a sufficiency gate.

A minimal ReAct-style graph — the model either calls a tool (SQL / document search) or
emits the final answer. ``tools_condition`` routes tool calls to the tool node; when the
model STOPS calling tools, control passes through a **sufficiency node** (Phase 4):
"does the evidence collected so far actually answer the question?". If not (and a
steering pass remains), a corrective message naming what is missing is injected and the
agent loops once more; otherwise the run ends. The graph stays intentionally thin — all
real work lives in the wrapped sources, and the sufficiency verdict comes from
``app.agent.sufficiency`` (deterministic core + optional LLM refinement).
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.sufficiency import assess_sufficiency
from app.agent.tools import AgentRunContext, make_tools

# At most one corrective loop-back: the check runs after the model's first final answer
# attempt and, if it steers, once more after the retry — bounded by design.
_MAX_SUFFICIENCY_PASSES = 2


def build_agent_graph(ctx: AgentRunContext, model: str, settings,
                      temperature: float | None = None,
                      question: str | None = None):
    """Compile the agent graph bound to a run context. ChatOpenAI targets the same
    OpenAI-compatible endpoint the rest of the app uses (OpenAI / Groq / Ollama / …)."""
    tools = make_tools(ctx)
    llm = ChatOpenAI(
        model=model,
        api_key=settings.openai_key or "no-key",
        base_url=settings.openai_base_url,
        temperature=temperature if temperature is not None else 0,
        timeout=60,
        max_retries=1,
    )
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: MessagesState) -> dict:
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    def sufficiency_node(state: MessagesState) -> dict:
        """Gate between 'the model stopped calling tools' and 'the run ends'."""
        ctx.sufficiency_passes += 1
        ctx.steer = False
        q = question or next(
            (m.content for m in state["messages"] if isinstance(m, HumanMessage)), "")
        verdict = assess_sufficiency(q, ctx.evidence, settings=settings)
        if verdict.call:
            ctx.calls.append(verdict.call)
        ctx.steps.append({
            "iteration": len(ctx.steps) + 1, "tool": "sufficiency_check",
            "args": {"pass": ctx.sufficiency_passes},
            "observation": verdict.reasoning[:600],
            "evidence_ids": [],
        })
        if (verdict.sufficient or not verdict.next_queries
                or ctx.sufficiency_passes >= _MAX_SUFFICIENCY_PASSES
                or not ctx.evidence):
            return {}
        ctx.steer = True
        hints = "; ".join(nq.query for nq in verdict.next_queries[:2])
        missing = ", ".join((verdict.missing_terms + verdict.missing_aspects)[:6])
        return {"messages": [HumanMessage(content=(
            "Sufficiency check: the evidence gathered so far does not fully cover the "
            f"question. Missing: {missing or 'key aspects'}. Call search_documents or "
            f"sql_query again — for example: {hints}. If the sources genuinely lack this "
            "information, stop and say so honestly."
        ))]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("sufficiency", sufficiency_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition,
                                {"tools": "tools", END: "sufficiency"})
    graph.add_conditional_edges("sufficiency", lambda _state: "agent" if ctx.steer else END,
                                {"agent": "agent", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
