// Mirrors the backend Pydantic models (app/models.py).

export type Route = "PDF" | "SQL" | "HYBRID" | "NONE" | "GENERAL_KNOWLEDGE";
export type SourceKind = "documents" | "relational" | "api";

/* ---------------- role adaptation ---------------- */
export interface RoleInfo {
  name: string;
  label: string;
  description: string;
  system_instruction: string;
}

/* ---------------- trust & explainability (Section 6) ---------------- */
export interface TrustFactors {
  recency_score?: number;
  retrieval_score?: number;
  rerank_score?: number;
  is_primary_source?: boolean;
  trust_summary?: string;
}

export interface Evidence {
  id: string;
  source_name: string;
  source_kind: SourceKind;
  content: string;
  citation_label: string;
  score?: number | null;
  language?: string | null;
  origin?: "sample" | "uploaded" | null;
  contribution_percentage?: number | null;
  trust_factors?: TrustFactors | null;
  used?: boolean;
  document?: string | null;
  page?: number | null;
  chunk_id?: string | null;
  section?: string | null;
  table?: string | null;
  row_ids?: unknown[] | null;
  sql?: string | null;
  columns?: string[] | null;
  extra?: Record<string, unknown>;
}

export interface RetrievalCandidate {
  chunk_id: string;
  document: string;
  page?: number | null;
  section?: string | null;
  language?: string | null;
  snippet: string;
  dense_rank?: number | null;
  dense_score?: number | null;
  bm25_rank?: number | null;
  bm25_score?: number | null;
  rrf_score?: number | null;
  rerank_score?: number | null;
  final_rank?: number | null;
  selected: boolean;
  keyword_hit?: boolean;
}

export interface DocumentRetrievalTrace {
  query: string;
  filters: Record<string, unknown>;
  embedding_backend: string;
  reranker_backend: string;
  params: Record<string, unknown>;
  candidates: RetrievalCandidate[];
  intent?: string;
  search_terms?: string[];
  exact_hits?: number;
  strategy?: string;
}

export interface SqlExecutionTrace {
  purpose: string;
  natural_language: string;
  generated_sql: string;
  validated_sql?: string | null;
  valid: boolean;
  validation_error?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  tables: string[];
  duration_ms: number;
}

export interface RouteDecision {
  route: Route;
  reasoning: string;
  confidence: number;
  languages: string[];
  document_subquery?: string | null;
  sql_subquery?: string | null;
  entity_hint?: string | null;
  agentic: boolean;
  strategy_note?: string | null;
}

export interface LLMCall {
  purpose: string;
  model: string;
  mode: "live" | "cached" | "stub";
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_usd?: number | null;
  duration_ms: number;
}

export interface CostSummary {
  input_tokens: number;
  output_tokens: number;
  total_usd: number;
  live_calls: number;
  note: string;
}

export interface CitationCheck {
  verified: boolean;
  cited_ids: string[];
  unknown_ids: string[];
  note: string;
}

/* ---------------- generation steps (Section 6) ---------------- */
export interface GenerationStep {
  step: string;
  decision?: string | null;
  confidence?: number | null;
  duration_ms: number;
  details?: Record<string, unknown>;
}

/* ---------------- contradiction (Section 8) ---------------- */
export interface ContradictionResult {
  contradiction: boolean;
  severity: "none" | "minor" | "major";
  explanation: string;
  evidence_a_id?: string;
  evidence_b_id?: string;
}

/* ---------------- multi-agent (Section 10) ---------------- */
export interface MultiAgentSubAnswer {
  sub_question: string;
  route: Route;
  answer: string;
  evidence_ids: string[];
}

export interface MultiAgentTrace {
  original_question: string;
  sub_questions: string[];
  sub_answers: MultiAgentSubAnswer[];
  synthesis_reasoning: string;
}

/* ---------------- iterative agent (LangGraph) ---------------- */
export interface AgentStepTrace {
  iteration: number;
  tool: string;
  args: Record<string, unknown>;
  observation: string;
  evidence_ids: string[];
}

export interface AgentTrace {
  original_question: string;
  iterations: number;
  tools_used: string[];
  steps: AgentStepTrace[];
}

export interface Trace {
  question: string;
  languages: string[];
  role?: string | null;
  role_instructions?: string | null;
  output_mode: string;
  route?: RouteDecision | null;
  notes: string[];
  document_retrieval?: DocumentRetrievalTrace | null;
  sql_executions: SqlExecutionTrace[];
  evidence: Evidence[];
  generation: Record<string, unknown>;
  citation_check?: CitationCheck | null;
  llm_calls: LLMCall[];
  cost?: CostSummary | null;
  timings: { name: string; duration_ms: number }[];
  mode: string;
  generation_steps: GenerationStep[];
  multi_agent_trace?: MultiAgentTrace | null;
  agent_trace?: AgentTrace | null;
}

export interface AskResponse {
  question: string;
  answer: string;
  insufficient: boolean;
  citations: Evidence[];
  trace: Trace;
  verification_warning?: string | null;
  hallucination_risk_score?: number | null;
  contradictions: ContradictionResult[];
  multi_agent_trace?: MultiAgentTrace | null;
  agent_trace?: AgentTrace | null;
}

export interface ExampleQuestion {
  label: string;
  question: string;
  route: Route;
  why: string;
  language: string;
}

export interface SourceInfo {
  name: string;
  kind: SourceKind;
  title: string;
  description: string;
  capabilities: string[];
  status: "active" | "future";
  details: Record<string, unknown>;
}

export interface AppConfig {
  mode: string;
  provider: string;
  models: { generation: string; router: string; sql: string };
  embedding_backend: string;
  vector_backend: string;
  reranker_backend: string;
  has_api_key: boolean;
}

/* ---------------- ingestion & inventory ---------------- */
export type Origin = "sample" | "uploaded";
export type IngestStatus = "indexed" | "error";

export interface TableInfo {
  name: string;
  original_name?: string | null;
  rows: number;
  columns: string[];
}

export interface IngestedDocumentInfo {
  name: string;
  type: "pdf";
  origin: Origin;
  status: IngestStatus;
  chunks_indexed: number;
  languages: string[];
  pages?: number | null;
  ingestion_ms: number;
  error?: string | null;
}

export interface IngestedDatabaseInfo {
  name: string;
  type: "sqlite";
  origin: Origin;
  status: IngestStatus;
  tables: TableInfo[];
  total_rows: number;
  ingestion_ms: number;
  error?: string | null;
}

export interface Inventory {
  documents: IngestedDocumentInfo[];
  databases: IngestedDatabaseInfo[];
  total_chunks: number;
  total_tables: number;
}

export interface IngestResult {
  ok: boolean;
  documents: IngestedDocumentInfo[];
  databases: IngestedDatabaseInfo[];
  inventory: Inventory;
  message: string;
}

/* ---------------- chat sessions (Section 5) ---------------- */
export interface Session {
  id: string;
  title: string;
  created_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  route?: string | null;
  confidence?: number | null;
  created_at: string;
  edited_at?: string | null;
}

/* ---------------- workspaces & artifacts (Section 7) ---------------- */
export type ArtifactType = "report" | "ppt_content" | "table" | "json" | "summary" | "action_plan";

export interface Workspace {
  id: string;
  name: string;
  description: string;
  created_at: string;
  artifact_count?: number;
}

export interface WorkspaceArtifact {
  id: string;
  workspace_id: string;
  artifact_type: ArtifactType;
  title: string;
  content: string;
  source_question: string;
  created_at: string;
}

/* ---------------- project memory (Section 9) ---------------- */
export type MemoryType = "fact" | "preference" | "context" | "entity";

export interface ProjectMemory {
  id: string;
  workspace_id: string;
  memory_type: MemoryType;
  key: string;
  value: string;
  confidence: number;
  created_at: string;
  last_used: string;
}

/* ---------------- workflows (Section 11) ---------------- */
export type TriggerType = "manual" | "scheduled" | "on_new_document";
export type WorkflowStatus = "idle" | "running" | "error";

export interface WorkflowStep {
  question: string;
  artifact_type: ArtifactType;
  output_to: string;
}

export interface Workflow {
  id: string;
  workspace_id: string;
  name: string;
  trigger_type: TriggerType;
  schedule_cron?: string | null;
  steps: WorkflowStep[];
  last_run?: string | null;
  status: WorkflowStatus;
}
