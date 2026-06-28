"""Agent tools — thin LangChain wrappers over the existing sources.

Each tool delegates to the live ``Orchestrator``'s document / relational sources and
records what it found into a shared :class:`AgentRunContext`. Evidence ids are assigned
incrementally (``e1``, ``e2``, …) as tools run, so the ids the model sees in tool
observations are exactly the ids that end up in the final answer and trace — no
relabeling pass that could desync citations.
"""
from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool

from app.models import Evidence


class AgentRunContext:
    """Mutable scratchpad shared by all tool calls in a single agent run."""

    def __init__(self, orchestrator, allowed_docs: Optional[list[str]],
                 allowed_tables: Optional[list[str]]) -> None:
        self.orch = orchestrator
        self.allowed_docs = allowed_docs
        self.allowed_tables = allowed_tables
        self.evidence: list[Evidence] = []
        self.sql_executions: list = []
        self.document_retrieval = None
        self.calls: list = []
        self.steps: list[dict] = []
        self._seen: dict[tuple, str] = {}

    def add_evidence(self, ev_list: list[Evidence]) -> list[str]:
        """Append evidence (dedup by content) and return the assigned ids, in order."""
        ids: list[str] = []
        for e in ev_list:
            key = (e.source_kind, e.source_name, e.content)
            if key in self._seen:
                ids.append(self._seen[key])
                continue
            new_id = f"e{len(self.evidence) + 1}"
            self.evidence.append(e.model_copy(update={"id": new_id}))
            self._seen[key] = new_id
            ids.append(new_id)
        return ids


def make_tools(ctx: AgentRunContext) -> list[StructuredTool]:
    """Build the tool set bound to ``ctx``. Closures keep the per-run state private."""

    def sql_query(query: str) -> str:
        """Run a read-only SQL lookup against the business database. Pass a natural-language
        description of what to fetch (e.g. 'customers with overdue invoices'); SQL is
        generated, validated read-only, and executed. Returns the matching rows."""
        if ctx.allowed_tables is not None and len(ctx.allowed_tables) == 0:
            return "No database tables are in scope for this question."
        ev, trace, call = ctx.orch.relational.run(
            query, purpose="agent_sql", allowed_tables=ctx.allowed_tables
        )
        if call:
            ctx.calls.append(call)
        ctx.sql_executions.append(trace)
        ids = ctx.add_evidence(ev)
        if not trace.valid:
            obs = f"SQL could not be run: {trace.validation_error}"
        elif not ev:
            obs = f"Query executed but returned {trace.row_count} usable row(s)."
        else:
            rows = "\n".join(f"[{i}] {e.content}" for i, e in zip(ids, ev))
            obs = f"Returned {trace.row_count} row(s):\n{rows}"
        ctx.steps.append({
            "iteration": len(ctx.steps) + 1, "tool": "sql_query",
            "args": {"query": query}, "observation": obs[:600],
            "evidence_ids": ids,
        })
        return obs

    def search_documents(query: str) -> str:
        """Search the uploaded documents (PDFs) with hybrid dense + keyword retrieval.
        Pass what you want to find in the documents. Returns the most relevant passages
        with their citation ids and provenance."""
        if ctx.allowed_docs is not None and len(ctx.allowed_docs) == 0:
            return "No documents are in scope for this question."
        filters: dict = {}
        if ctx.allowed_docs:
            filters["documents"] = ctx.allowed_docs
        ev, dtrace = ctx.orch.documents.retrieve(query, filters=filters)
        # keep the richest retrieval trace + accumulate candidates for the inspector
        if ctx.document_retrieval is None:
            ctx.document_retrieval = dtrace
        else:
            ctx.document_retrieval.candidates += dtrace.candidates
        ids = ctx.add_evidence(ev)
        if not ev:
            obs = "No relevant passages found in the documents for that query."
        else:
            passages = "\n".join(
                f"[{i}] {e.citation_label} {e.content[:300]}" for i, e in zip(ids, ev)
            )
            obs = f"Found {len(ev)} passage(s):\n{passages}"
        ctx.steps.append({
            "iteration": len(ctx.steps) + 1, "tool": "search_documents",
            "args": {"query": query}, "observation": obs[:600],
            "evidence_ids": ids,
        })
        return obs

    return [
        StructuredTool.from_function(
            sql_query, name="sql_query",
            description=sql_query.__doc__,
        ),
        StructuredTool.from_function(
            search_documents, name="search_documents",
            description=search_documents.__doc__,
        ),
    ]
