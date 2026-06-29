"""Core data models — the spine of traceability.

Everything the engine produces is one of these objects. The answer, the citation
list, and the inspector panel all reference the SAME ``Evidence`` objects, so there
is exactly one source of truth from retrieval through to the rendered citation.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SourceKind = Literal["documents", "relational", "api"]
Route = Literal["PDF", "SQL", "HYBRID", "NONE", "GENERAL_KNOWLEDGE"]


class Evidence(BaseModel):
    """A single, fully-attributed piece of evidence used to ground the answer."""

    id: str                                   # "e1", "e2", … — stable citation handle
    source_name: str                          # "contracts_pdf" | "business_db" | …
    source_kind: SourceKind
    content: str                              # exact text/row handed to the LLM
    citation_label: str                       # "[ACME_MSA_2025.pdf p.4]" / "[invoices #1187]"
    score: Optional[float] = None             # retrieval / rerank score (documents)
    language: Optional[str] = None            # "en" | "de"
    origin: Optional[str] = None              # "sample" | "uploaded" — provenance for trust
    contribution_percentage: Optional[float] = None  # fraction of answer this evidence contributed
    trust_factors: Optional[dict[str, Any]] = None   # recency_score, retrieval_score, etc.
    used: bool = False                        # did the final answer actually cite this?

    # document provenance
    document: Optional[str] = None
    page: Optional[int] = None
    chunk_id: Optional[str] = None
    section: Optional[str] = None

    # relational provenance
    table: Optional[str] = None
    row_ids: Optional[list[Any]] = None
    sql: Optional[str] = None
    columns: Optional[list[str]] = None

    extra: dict[str, Any] = Field(default_factory=dict)


class RetrievalCandidate(BaseModel):
    """One document chunk as it moves through the hybrid pipeline — for the inspector."""

    chunk_id: str
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    language: Optional[str] = None
    snippet: str

    dense_rank: Optional[int] = None
    dense_score: Optional[float] = None
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None
    final_rank: Optional[int] = None
    selected: bool = False
    keyword_hit: bool = False                 # chunk literally contains a searched term


class DocumentRetrievalTrace(BaseModel):
    query: str
    rewritten_queries: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    embedding_backend: str = "unknown"
    reranker_backend: str = "none"
    params: dict[str, Any] = Field(default_factory=dict)
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    # intent-aware retrieval (set by DocumentIndex.retrieve)
    intent: str = "semantic"                  # "keyword" | "semantic"
    search_terms: list[str] = Field(default_factory=list)
    exact_hits: int = 0                       # chunks literally containing a term
    strategy: str = ""                        # plain-English summary for the inspector


class SqlExecutionTrace(BaseModel):
    purpose: str                              # what this query was for
    natural_language: str
    generated_sql: str
    validated_sql: Optional[str] = None
    valid: bool = False
    validation_error: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    tables: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0


class RouteDecision(BaseModel):
    route: Route
    reasoning: str
    confidence: float = 0.0
    languages: list[str] = Field(default_factory=lambda: ["en"])
    document_subquery: Optional[str] = None   # what to ask the documents
    sql_subquery: Optional[str] = None        # what to ask the database
    entity_hint: Optional[str] = None         # e.g. "customers with overdue invoices"
    agentic: bool = False                     # does this need SQL → entities → docs?
    strategy_note: Optional[str] = None


class LLMCall(BaseModel):
    purpose: str
    model: str
    mode: Literal["live", "cached", "stub"]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_ms: float = 0.0


class CostSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_usd: float = 0.0
    live_calls: int = 0
    note: str = ""


class StageTiming(BaseModel):
    name: str
    duration_ms: float


class CitationCheck(BaseModel):
    verified: bool
    cited_ids: list[str] = Field(default_factory=list)
    unknown_ids: list[str] = Field(default_factory=list)
    note: str = ""


class GenerationStep(BaseModel):
    """One step in the answer generation pipeline — for the explainability panel."""
    step: str
    decision: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    """The complete, inspectable record of how an answer was produced."""

    question: str
    languages: list[str] = Field(default_factory=lambda: ["en"])
    role: Optional[str] = None                                # assigned role (e.g., "doctor", "business_analyst")
    role_instructions: Optional[str] = None                   # role-specific system instructions used
    output_mode: str = "Standard Response"
    route: Optional[RouteDecision] = None
    notes: list[str] = Field(default_factory=list)            # orchestrator narration
    document_retrieval: Optional[DocumentRetrievalTrace] = None
    sql_executions: list[SqlExecutionTrace] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    generation: dict[str, Any] = Field(default_factory=dict)
    citation_check: Optional[CitationCheck] = None
    llm_calls: list[LLMCall] = Field(default_factory=list)
    cost: Optional["CostSummary"] = None
    timings: list[StageTiming] = Field(default_factory=list)
    mode: str = "live"                                        # live | offline-cache | mixed
    generation_steps: list[GenerationStep] = Field(default_factory=list)
    multi_agent_trace: Optional[dict[str, Any]] = None
    # Iterative LangGraph agent timeline (tool calls + observations), when agent_mode is on.
    agent_trace: Optional[dict[str, Any]] = None


class AskRequest(BaseModel):
    question: str
    developer_mode: bool = True
    # "workspace" → answer only from the user's uploaded sources (a clean, isolated
    # workspace). "demo" → answer only from the preloaded sample data. "all" → both.
    scope: Literal["workspace", "demo", "all"] = "workspace"
    # role-based adaptation (e.g., "doctor", "business_analyst", "nurse", etc.)
    role: Optional[str] = None
    output_mode: str = "Standard Response"
    # --- new fields (Sections 2, 3, 5, 10) ---
    custom_system_prompt: Optional[str] = None   # free-form system prompt override
    agent_role: Optional[str] = None             # e.g. "You are a legal analyst..."
    output_format: Optional[str] = "auto"        # auto|prose|table|timeline_table|json|bullet_points|executive_summary
    multi_agent: bool = False                    # force multi-agent decomposition
    agent_mode: bool = False                     # force the LangGraph iterative agent
    temperature: Optional[float] = None          # generation temperature (None == deterministic)
    session_id: Optional[str] = None             # active chat session id
    # Optional explicit prior turns; when omitted the server loads them from session_id.
    conversation_history: Optional[list[dict[str, Any]]] = None


class AskResponse(BaseModel):
    question: str
    answer: str
    insufficient: bool = False
    citations: list[Evidence] = Field(default_factory=list)
    trace: Trace
    # --- new fields (Sections 8, 10) ---
    verification_warning: Optional[str] = None
    hallucination_risk_score: Optional[float] = None
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    multi_agent_trace: Optional[dict[str, Any]] = None
    agent_trace: Optional[dict[str, Any]] = None


class ExampleQuestion(BaseModel):
    label: str
    question: str
    route: Route
    why: str
    language: str = "en"


class SourceInfo(BaseModel):
    name: str
    kind: SourceKind
    title: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    status: Literal["active", "future"] = "active"
    details: dict[str, Any] = Field(default_factory=dict)


# --- Ingestion & inventory (runtime uploads) --------------------------------

class TableInfo(BaseModel):
    """One table detected in an uploaded (or sample) SQLite database."""

    name: str                                  # effective name (post collision-safe rename)
    original_name: Optional[str] = None        # name in the uploaded file, if renamed
    rows: int = 0
    columns: list[str] = Field(default_factory=list)


class IngestedDocumentInfo(BaseModel):
    """A PDF that has been ingested and indexed at runtime (or pre-loaded sample)."""

    name: str
    type: Literal["pdf"] = "pdf"
    origin: Literal["sample", "uploaded"] = "uploaded"
    status: Literal["indexed", "error"] = "indexed"
    chunks_indexed: int = 0
    languages: list[str] = Field(default_factory=list)
    pages: Optional[int] = None
    ingestion_ms: float = 0.0
    error: Optional[str] = None


class IngestedDatabaseInfo(BaseModel):
    """A SQLite database registered with the router (sample or uploaded)."""

    name: str
    type: Literal["sqlite"] = "sqlite"
    origin: Literal["sample", "uploaded"] = "uploaded"
    status: Literal["indexed", "error"] = "indexed"
    tables: list[TableInfo] = Field(default_factory=list)
    total_rows: int = 0
    ingestion_ms: float = 0.0
    error: Optional[str] = None


class Inventory(BaseModel):
    """Everything currently indexed — drives the Workspace source inventory."""

    documents: list[IngestedDocumentInfo] = Field(default_factory=list)
    databases: list[IngestedDatabaseInfo] = Field(default_factory=list)
    total_chunks: int = 0
    total_tables: int = 0


class IngestResult(BaseModel):
    """Response for an upload: what was ingested this request + the full inventory."""

    ok: bool = True
    documents: list[IngestedDocumentInfo] = Field(default_factory=list)
    databases: list[IngestedDatabaseInfo] = Field(default_factory=list)
    inventory: Inventory
    message: str = ""
