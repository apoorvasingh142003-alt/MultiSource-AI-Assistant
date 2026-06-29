"use client";
import React from "react";
import type { Workflow, WorkflowStep, TriggerType, ArtifactType, WorkflowStatus } from "@/lib/types";
import { fetchWorkflows, createWorkflow, runWorkflow } from "@/lib/api";
import { Button, Card, EmptyState, Icons, Pill, SectionTitle, cn } from "./ui";

const ARTIFACT_TYPES: ArtifactType[] = ["report", "ppt_content", "table", "json", "summary", "action_plan"];

const STATUS_TONE: Record<WorkflowStatus, "slate" | "emerald" | "amber" | "rose"> = {
  idle: "slate", running: "amber", error: "rose",
};

const emptyStep = (): WorkflowStep => ({ question: "", artifact_type: "report", output_to: "" });

export default function WorkflowBuilder({ workspaceId }: { workspaceId: string }) {
  const [workflows, setWorkflows] = React.useState<Workflow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [building, setBuilding] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const [name, setName] = React.useState("");
  const [trigger, setTrigger] = React.useState<TriggerType>("manual");
  const [cron, setCron] = React.useState("0 9 * * 1");
  const [steps, setSteps] = React.useState<WorkflowStep[]>([emptyStep()]);

  const load = React.useCallback(() => {
    setLoading(true);
    fetchWorkflows(workspaceId)
      .then(setWorkflows)
      .catch(() => setWorkflows([]))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  React.useEffect(() => { load(); }, [load]);

  const resetForm = () => {
    setName(""); setTrigger("manual"); setCron("0 9 * * 1"); setSteps([emptyStep()]); setBuilding(false);
  };

  const onCreate = async () => {
    const valid = steps.filter((s) => s.question.trim());
    if (!name.trim() || valid.length === 0) return;
    try {
      const wf = await createWorkflow(
        workspaceId, name.trim(), trigger, valid,
        trigger === "scheduled" ? cron : undefined,
      );
      setWorkflows((prev) => [wf, ...prev]);
      resetForm();
    } catch { /* ignore */ }
  };

  const onRun = async (id: string) => {
    setBusyId(id);
    setWorkflows((prev) => prev.map((w) => w.id === id ? { ...w, status: "running" } : w));
    try {
      await runWorkflow(workspaceId, id);
    } catch { /* ignore */ } finally {
      setBusyId(null);
      load();
    }
  };

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <SectionTitle hint="multi-step pipelines that produce artifacts">Workflows</SectionTitle>
        <Button variant="ghost" size="sm" onClick={() => setBuilding((b) => !b)}>
          <Icons.plus className="h-3.5 w-3.5" />New workflow
        </Button>
      </div>

      {building && (
        <div className="mb-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <input
            value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Workflow name (e.g. Weekly overdue report)"
            className="focus-ring w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12.5px]"
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={trigger} onChange={(e) => setTrigger(e.target.value as TriggerType)}
              className="focus-ring rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-[12px] text-slate-700"
            >
              <option value="manual">Manual</option>
              <option value="scheduled">Scheduled</option>
              <option value="on_new_document">On new document</option>
            </select>
            {trigger === "scheduled" && (
              <input
                value={cron} onChange={(e) => setCron(e.target.value)}
                placeholder="cron e.g. 0 9 * * 1"
                className="focus-ring w-40 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 font-mono text-[12px]"
                title="Cron schedule (min hour day month weekday)"
              />
            )}
          </div>

          <div className="space-y-2">
            {steps.map((s, i) => (
              <div key={i} className="rounded-lg border border-slate-200 bg-white p-2">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-500">Step {i + 1}</span>
                  {steps.length > 1 && (
                    <button onClick={() => setSteps((p) => p.filter((_, j) => j !== i))}
                      className="rounded p-0.5 text-slate-400 hover:text-rose-500" title="Remove step">
                      <Icons.x className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                <input
                  value={s.question}
                  onChange={(e) => setSteps((p) => p.map((x, j) => j === i ? { ...x, question: e.target.value } : x))}
                  placeholder="Question to ask"
                  className="focus-ring mb-1.5 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px]"
                />
                <div className="flex gap-2">
                  <select
                    value={s.artifact_type}
                    onChange={(e) => setSteps((p) => p.map((x, j) => j === i ? { ...x, artifact_type: e.target.value as ArtifactType } : x))}
                    className="focus-ring rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-[12px] text-slate-700"
                  >
                    {ARTIFACT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <input
                    value={s.output_to}
                    onChange={(e) => setSteps((p) => p.map((x, j) => j === i ? { ...x, output_to: e.target.value } : x))}
                    placeholder="output label"
                    className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px]"
                  />
                </div>
              </div>
            ))}
            <Button variant="ghost" size="sm" onClick={() => setSteps((p) => [...p, emptyStep()])}>
              <Icons.plus className="h-3.5 w-3.5" />Add step
            </Button>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={resetForm}>Cancel</Button>
            <Button size="sm" onClick={onCreate} disabled={!name.trim() || !steps.some((s) => s.question.trim())}>
              Create workflow
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="py-6 text-center text-[12px] text-slate-400">Loading workflows…</p>
      ) : workflows.length === 0 ? (
        <EmptyState icon={<Icons.bolt className="h-6 w-6" />} title="No workflows yet">
          Build a multi-step workflow that generates artifacts on demand or on a schedule.
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {workflows.map((w) => (
            <li key={w.id} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-semibold text-slate-700">{w.name}</span>
                    <Pill tone={STATUS_TONE[w.status]}>{w.status}</Pill>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                    <Pill tone="sky">{w.trigger_type}</Pill>
                    {w.schedule_cron && <span className="font-mono">{w.schedule_cron}</span>}
                    <span>· {w.steps.length} step(s)</span>
                    {w.last_run && <span>· last run {w.last_run.slice(0, 16).replace("T", " ")}</span>}
                  </div>
                </div>
                <Button size="sm" onClick={() => onRun(w.id)} disabled={busyId === w.id}>
                  {busyId === w.id
                    ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/50 border-t-white" />
                    : <Icons.play className="h-3.5 w-3.5" />}
                  Run now
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
