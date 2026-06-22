"use client";
import React from "react";
import type { Workspace, WorkspaceArtifact, ArtifactType } from "@/lib/types";
import {
  fetchWorkspaces, createWorkspace, deleteWorkspace,
  fetchArtifacts, generateArtifact, deleteArtifact,
} from "@/lib/api";
import { segmentAnswer } from "@/lib/tableParser";
import AnswerTable from "./AnswerTable";
import MemoryViewer from "./MemoryViewer";
import WorkflowBuilder from "./WorkflowBuilder";
import { Button, Card, EmptyState, Icons, Pill, SectionTitle, Tabs, cn } from "./ui";

const ARTIFACT_TYPES: ArtifactType[] = ["report", "ppt_content", "table", "json", "summary", "action_plan"];

const TYPE_ICON: Record<ArtifactType, React.ReactNode> = {
  report: <Icons.doc className="h-3.5 w-3.5" />,
  ppt_content: <Icons.layers className="h-3.5 w-3.5" />,
  table: <Icons.table className="h-3.5 w-3.5" />,
  json: <Icons.bolt className="h-3.5 w-3.5" />,
  summary: <Icons.inspect className="h-3.5 w-3.5" />,
  action_plan: <Icons.check className="h-3.5 w-3.5" />,
};

type StudioTab = "artifacts" | "memory" | "workflows";

/* ---------------- artifact content renderer ---------------- */
function ArtifactContent({ artifact, asSlides }: { artifact: WorkspaceArtifact; asSlides: boolean }) {
  if (asSlides && artifact.artifact_type === "ppt_content") {
    const slides = artifact.content.split(/\n(?=\s*(?:Slide\s*\d|##\s*Slide|\*\*Slide))/i).filter((s) => s.trim());
    return (
      <div className="space-y-3">
        {slides.map((s, i) => (
          <div key={i} className="rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-4 shadow-sm">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-indigo-400">Slide {i + 1}</div>
            <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">{s.trim()}</pre>
          </div>
        ))}
      </div>
    );
  }
  if (artifact.artifact_type === "json") {
    return (
      <pre className="overflow-x-auto rounded-xl bg-slate-900 p-4 font-mono text-[12.5px] leading-relaxed text-slate-100">
        {artifact.content}
      </pre>
    );
  }
  const segments = segmentAnswer(artifact.content);
  return (
    <div className="space-y-3">
      {segments.map((seg, i) =>
        seg.type === "table"
          ? <AnswerTable key={i} table={seg.table} />
          : <pre key={i} className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed text-slate-700">{seg.content}</pre>
      )}
    </div>
  );
}

/* ---------------- artifact modal ---------------- */
function ArtifactModal({
  artifact, onClose, onRegenerate, regenerating,
}: {
  artifact: WorkspaceArtifact;
  onClose: () => void;
  onRegenerate: () => void;
  regenerating: boolean;
}) {
  const [asSlides, setAsSlides] = React.useState(false);

  const download = (ext: "txt" | "md") => {
    const blob = new Blob([artifact.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.title.replace(/[^\w.-]+/g, "_") || "artifact"}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const copy = () => navigator.clipboard?.writeText(artifact.content).catch(() => {});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 panel-transition"
      onClick={onClose}>
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Pill tone="indigo">{TYPE_ICON[artifact.artifact_type]}{artifact.artifact_type}</Pill>
              <h2 className="truncate text-[15px] font-bold text-slate-900">{artifact.title}</h2>
            </div>
            <p className="mt-0.5 truncate text-[11.5px] text-slate-400">{artifact.source_question}</p>
          </div>
          <button onClick={onClose} className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <Icons.x className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-2.5">
          <Button variant="secondary" size="sm" onClick={() => download("md")}>
            <Icons.doc className="h-3.5 w-3.5" />Download .md
          </Button>
          <Button variant="secondary" size="sm" onClick={() => download("txt")}>
            <Icons.doc className="h-3.5 w-3.5" />Download .txt
          </Button>
          <Button variant="secondary" size="sm" onClick={copy}>
            <Icons.check className="h-3.5 w-3.5" />Copy
          </Button>
          {artifact.artifact_type === "ppt_content" && (
            <Button variant="secondary" size="sm" onClick={() => setAsSlides((s) => !s)}>
              <Icons.layers className="h-3.5 w-3.5" />{asSlides ? "Raw" : "View as slides"}
            </Button>
          )}
          <Button size="sm" onClick={onRegenerate} disabled={regenerating} className="ml-auto">
            {regenerating
              ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/50 border-t-white" />
              : <Icons.refresh className="h-3.5 w-3.5" />}
            Regenerate
          </Button>
        </div>

        <div className="overflow-y-auto px-5 py-4">
          <ArtifactContent artifact={artifact} asSlides={asSlides} />
        </div>
      </div>
    </div>
  );
}

/* ---------------- generate dialog ---------------- */
function GenerateDialog({
  onClose, onGenerate, busy,
}: {
  onClose: () => void;
  onGenerate: (q: string, type: ArtifactType, title: string) => void;
  busy: boolean;
}) {
  const [question, setQuestion] = React.useState("");
  const [type, setType] = React.useState<ArtifactType>("report");
  const [title, setTitle] = React.useState("");
  const suggested = title || question.slice(0, 50);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-lg p-5" >
        <div onClick={(e) => e.stopPropagation()}>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[15px] font-bold text-slate-900">Generate new artifact</h2>
            <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100">
              <Icons.x className="h-4 w-4" />
            </button>
          </div>
          <textarea
            value={question} onChange={(e) => setQuestion(e.target.value)}
            rows={3} placeholder="What should this artifact answer?"
            className="focus-ring mb-2.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13.5px]"
          />
          <div className="mb-2.5 flex gap-2">
            <select value={type} onChange={(e) => setType(e.target.value as ArtifactType)}
              className="focus-ring rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[12.5px] text-slate-700">
              {ARTIFACT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input
              value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder={`Title (auto: "${question.slice(0, 24)}…")`}
              className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[12.5px]"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" onClick={() => onGenerate(question.trim(), type, suggested || "Untitled")}
              disabled={busy || !question.trim()}>
              {busy
                ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/50 border-t-white" />
                : <Icons.spark className="h-3.5 w-3.5" />}
              Generate
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

/* ================= main ================= */
export default function WorkspaceView() {
  const [workspaces, setWorkspaces] = React.useState<Workspace[]>([]);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [subTab, setSubTab] = React.useState<StudioTab>("artifacts");
  const [newName, setNewName] = React.useState("");

  const [artifacts, setArtifacts] = React.useState<WorkspaceArtifact[]>([]);
  const [showGen, setShowGen] = React.useState(false);
  const [genBusy, setGenBusy] = React.useState(false);
  const [open, setOpen] = React.useState<WorkspaceArtifact | null>(null);
  const [regenBusy, setRegenBusy] = React.useState(false);

  React.useEffect(() => {
    fetchWorkspaces().then((ws) => {
      setWorkspaces(ws);
      if (ws.length && !activeId) setActiveId(ws[0].id);
    }).catch(() => {});
  }, [activeId]);

  const loadArtifacts = React.useCallback((wid: string) => {
    fetchArtifacts(wid).then(setArtifacts).catch(() => setArtifacts([]));
  }, []);

  React.useEffect(() => {
    if (activeId && subTab === "artifacts") loadArtifacts(activeId);
  }, [activeId, subTab, loadArtifacts]);

  const onCreateWorkspace = async () => {
    if (!newName.trim()) return;
    try {
      const w = await createWorkspace(newName.trim());
      setWorkspaces((p) => [w, ...p]);
      setActiveId(w.id);
      setNewName("");
    } catch { /* ignore */ }
  };

  const onDeleteWorkspace = async (id: string) => {
    if (!window.confirm("Delete this workspace and all its artifacts, memory, and workflows?")) return;
    try {
      await deleteWorkspace(id);
      setWorkspaces((p) => p.filter((w) => w.id !== id));
      if (activeId === id) setActiveId(null);
    } catch { /* ignore */ }
  };

  const onGenerate = async (q: string, type: ArtifactType, title: string) => {
    if (!activeId) return;
    setGenBusy(true);
    try {
      const a = await generateArtifact(activeId, q, type, title);
      setArtifacts((p) => [a, ...p]);
      setShowGen(false);
    } catch { /* ignore */ } finally { setGenBusy(false); }
  };

  const onRegenerate = async () => {
    if (!activeId || !open) return;
    setRegenBusy(true);
    try {
      const a = await generateArtifact(activeId, open.source_question, open.artifact_type, open.title);
      setArtifacts((p) => [a, ...p]);
      setOpen(a);
    } catch { /* ignore */ } finally { setRegenBusy(false); }
  };

  const onDeleteArtifact = async (id: string) => {
    if (!activeId) return;
    setArtifacts((p) => p.filter((a) => a.id !== id));
    try { await deleteArtifact(activeId, id); } catch { loadArtifacts(activeId); }
  };

  const active = workspaces.find((w) => w.id === activeId) || null;

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
      {/* ---- workspace list ---- */}
      <aside className="space-y-3">
        <Card className="p-4">
          <SectionTitle hint="report studios">Workspaces</SectionTitle>
          <div className="mb-3 flex gap-2">
            <input
              value={newName} onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") onCreateWorkspace(); }}
              placeholder="New workspace name"
              className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px]"
            />
            <Button size="sm" onClick={onCreateWorkspace} disabled={!newName.trim()}>
              <Icons.plus className="h-3.5 w-3.5" />
            </Button>
          </div>
          {workspaces.length === 0 ? (
            <p className="py-3 text-center text-[12px] text-slate-400">No workspaces yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {workspaces.map((w) => (
                <li key={w.id}>
                  <button
                    onClick={() => setActiveId(w.id)}
                    className={cn("group flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left transition",
                      activeId === w.id ? "bg-indigo-50 ring-1 ring-inset ring-indigo-200" : "hover:bg-slate-50")}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-slate-700">{w.name}</span>
                      <span className="text-[10.5px] text-slate-400">{w.artifact_count ?? 0} artifact(s)</span>
                    </span>
                    <span onClick={(e) => { e.stopPropagation(); onDeleteWorkspace(w.id); }}
                      className="shrink-0 rounded p-1 text-slate-300 opacity-0 transition hover:text-rose-500 group-hover:opacity-100"
                      title="Delete workspace">
                      <Icons.x className="h-3.5 w-3.5" />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </aside>

      {/* ---- active workspace ---- */}
      <main className="space-y-4">
        {!active ? (
          <Card>
            <EmptyState icon={<Icons.grid className="h-6 w-6" />} title="Select or create a workspace">
              Workspaces are persistent studios where you generate reusable artifacts (reports,
              slide outlines, tables, action plans), and where the assistant builds project memory.
            </EmptyState>
          </Card>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-[16px] font-bold text-slate-900">{active.name}</h2>
                {active.description && <p className="text-[12px] text-slate-400">{active.description}</p>}
              </div>
              <Tabs<StudioTab>
                tabs={[
                  { id: "artifacts", label: "Artifacts", icon: <Icons.doc className="h-3.5 w-3.5" /> },
                  { id: "memory", label: "Memory", icon: <Icons.spark className="h-3.5 w-3.5" /> },
                  { id: "workflows", label: "Workflows", icon: <Icons.bolt className="h-3.5 w-3.5" /> },
                ]}
                active={subTab} onChange={setSubTab}
              />
            </div>

            {subTab === "artifacts" && (
              <Card className="p-4">
                <div className="mb-3 flex items-center justify-between">
                  <SectionTitle hint="generated documents">Artifact library</SectionTitle>
                  <Button size="sm" onClick={() => setShowGen(true)}>
                    <Icons.plus className="h-3.5 w-3.5" />Generate new
                  </Button>
                </div>
                {artifacts.length === 0 ? (
                  <EmptyState icon={<Icons.doc className="h-6 w-6" />} title="No artifacts yet">
                    Generate a report, table, slide outline, or action plan from a question.
                  </EmptyState>
                ) : (
                  <div className="grid gap-2.5 sm:grid-cols-2">
                    {artifacts.map((a) => (
                      <div key={a.id}
                        className="group cursor-pointer rounded-xl border border-slate-200 bg-white p-3 transition hover:border-indigo-300 hover:shadow-sm"
                        onClick={() => setOpen(a)}>
                        <div className="flex items-center justify-between gap-2">
                          <Pill tone="indigo">{TYPE_ICON[a.artifact_type]}{a.artifact_type}</Pill>
                          <span onClick={(e) => { e.stopPropagation(); onDeleteArtifact(a.id); }}
                            className="rounded p-0.5 text-slate-300 opacity-0 transition hover:text-rose-500 group-hover:opacity-100"
                            title="Delete artifact">
                            <Icons.x className="h-3.5 w-3.5" />
                          </span>
                        </div>
                        <h3 className="mt-1.5 truncate text-[13px] font-semibold text-slate-700">{a.title}</h3>
                        <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-slate-500">
                          {a.content.slice(0, 100)}
                        </p>
                        <p className="mt-1.5 text-[10.5px] text-slate-400">{a.created_at?.slice(0, 16).replace("T", " ")}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}

            {subTab === "memory" && <MemoryViewer workspaceId={active.id} />}
            {subTab === "workflows" && <WorkflowBuilder workspaceId={active.id} />}
          </>
        )}
      </main>

      {showGen && active && (
        <GenerateDialog onClose={() => setShowGen(false)} onGenerate={onGenerate} busy={genBusy} />
      )}
      {open && (
        <ArtifactModal artifact={open} onClose={() => setOpen(null)}
          onRegenerate={onRegenerate} regenerating={regenBusy} />
      )}
    </div>
  );
}
