import type {
  AppConfig, AskResponse, ExampleQuestion, IngestResult, Inventory,
  Message, Session, SourceInfo, Workspace, WorkspaceArtifact, ProjectMemory,
  Workflow,
} from "./types";

// All API calls go through the UI's own origin at /api/*, which the Next server proxies
// to the backend (see next.config.js rewrites). One origin → works on localhost, a LAN
// IP, or behind a single public URL (Cloudflare tunnel) with no CORS and no extra port.
function apiBase(): string {
  return "/api";
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

async function postJSON<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json();
}

async function patchJSON<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
  return res.json();
}

async function deleteJSON(path: string): Promise<void> {
  const res = await fetch(`${apiBase()}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
}

/* ---- bootstrap ---- */
export async function fetchConfig(): Promise<AppConfig> {
  return getJSON<AppConfig>("/config");
}

export async function fetchExamples(): Promise<ExampleQuestion[]> {
  return getJSON<ExampleQuestion[]>("/examples");
}

export async function fetchSources(): Promise<SourceInfo[]> {
  return getJSON<SourceInfo[]>("/sources");
}

export async function fetchInventory(): Promise<Inventory> {
  return getJSON<Inventory>("/inventory");
}

/* ---- ask (updated for Sections 2, 3, 5, 10) ---- */
export type AskScope = "workspace" | "demo" | "all";

export async function ask(
  question: string,
  scope: AskScope = "workspace",
  role?: string | null,
  outputMode: string = "Standard Response",
  opts?: {
    custom_system_prompt?: string | null;
    agent_role?: string | null;
    output_format?: string;
    multi_agent?: boolean;
    session_id?: string | null;
  },
): Promise<AskResponse> {
  const res = await fetch(`${apiBase()}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      scope,
      output_mode: outputMode,
      ...(role ? { role } : {}),
      ...(opts?.custom_system_prompt ? { custom_system_prompt: opts.custom_system_prompt } : {}),
      ...(opts?.agent_role ? { agent_role: opts.agent_role } : {}),
      ...(opts?.output_format && opts.output_format !== "auto" ? { output_format: opts.output_format } : {}),
      ...(opts?.multi_agent ? { multi_agent: true } : {}),
      ...(opts?.session_id ? { session_id: opts.session_id } : {}),
    }),
  });
  if (!res.ok) throw new Error(`ask → ${res.status}`);
  return res.json();
}

/* ---- ingestion ---- */
async function postFiles(path: string, files: File[]): Promise<IngestResult> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const res = await fetch(`${apiBase()}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function ingestPdf(files: File[]): Promise<IngestResult> {
  return postFiles("/ingest/pdf", files);
}

export async function ingestSqlite(files: File[]): Promise<IngestResult> {
  return postFiles("/ingest/sqlite", files);
}

export async function resetWorkspace(): Promise<Inventory> {
  const res = await fetch(`${apiBase()}/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`reset → ${res.status}`);
  return res.json();
}

/* ---- sessions (Section 5) ---- */
export async function fetchSessions(): Promise<Session[]> {
  return getJSON<Session[]>("/sessions");
}

export async function createSession(): Promise<Session> {
  return postJSON<Session>("/sessions", {});
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  return getJSON<Message[]>(`/sessions/${sessionId}/messages`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  return deleteJSON(`/sessions/${sessionId}`);
}

export async function renameSession(sessionId: string, title: string): Promise<Session> {
  return patchJSON<Session>(`/sessions/${sessionId}`, { title });
}

/* ---- workspaces (Section 7) ---- */
export async function fetchWorkspaces(): Promise<Workspace[]> {
  return getJSON<Workspace[]>("/workspaces");
}

export async function createWorkspace(name: string, description?: string): Promise<Workspace> {
  return postJSON<Workspace>("/workspaces", { name, description: description || "" });
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  return deleteJSON(`/workspaces/${workspaceId}`);
}

export async function fetchArtifacts(workspaceId: string): Promise<WorkspaceArtifact[]> {
  return getJSON<WorkspaceArtifact[]>(`/workspaces/${workspaceId}/artifacts`);
}

export async function fetchArtifact(workspaceId: string, artifactId: string): Promise<WorkspaceArtifact> {
  return getJSON<WorkspaceArtifact>(`/workspaces/${workspaceId}/artifacts/${artifactId}`);
}

export async function generateArtifact(
  workspaceId: string,
  question: string,
  artifactType: string,
  title: string,
): Promise<WorkspaceArtifact> {
  return postJSON<WorkspaceArtifact>(`/workspaces/${workspaceId}/generate`, {
    question, artifact_type: artifactType, title,
  });
}

export async function deleteArtifact(workspaceId: string, artifactId: string): Promise<void> {
  return deleteJSON(`/workspaces/${workspaceId}/artifacts/${artifactId}`);
}

/* ---- project memory (Section 9) ---- */
export async function fetchMemories(workspaceId: string): Promise<ProjectMemory[]> {
  return getJSON<ProjectMemory[]>(`/workspaces/${workspaceId}/memory`);
}

export async function addMemory(
  workspaceId: string,
  memoryType: string,
  key: string,
  value: string,
): Promise<ProjectMemory> {
  return postJSON<ProjectMemory>(`/workspaces/${workspaceId}/memory`, {
    memory_type: memoryType, key, value,
  });
}

export async function deleteMemory(workspaceId: string, memoryId: string): Promise<void> {
  return deleteJSON(`/workspaces/${workspaceId}/memory/${memoryId}`);
}

/* ---- workflows (Section 11) ---- */
export async function fetchWorkflows(workspaceId: string): Promise<Workflow[]> {
  return getJSON<Workflow[]>(`/workspaces/${workspaceId}/workflows`);
}

export async function createWorkflow(
  workspaceId: string,
  name: string,
  triggerType: string,
  steps: { question: string; artifact_type: string; output_to: string }[],
  scheduleCron?: string,
): Promise<Workflow> {
  return postJSON<Workflow>(`/workspaces/${workspaceId}/workflows`, {
    name, trigger_type: triggerType, steps,
    ...(scheduleCron ? { schedule_cron: scheduleCron } : {}),
  });
}

export async function runWorkflow(workspaceId: string, workflowId: string): Promise<void> {
  await postJSON(`/workspaces/${workspaceId}/workflows/${workflowId}/run`, {});
}
