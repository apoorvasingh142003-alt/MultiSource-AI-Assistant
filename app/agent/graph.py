"""The LangGraph state machine: agent ⇄ tools loop.

A minimal ReAct-style graph — the model either calls a tool (SQL / document search) or
emits the final answer. ``tools_condition`` ends the loop when no more tool calls are
requested. The graph is intentionally thin; all real work lives in the wrapped sources.
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.tools import AgentRunContext, make_tools


def build_agent_graph(ctx: AgentRunContext, model: str, settings,
                      temperature: float | None = None):
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

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
