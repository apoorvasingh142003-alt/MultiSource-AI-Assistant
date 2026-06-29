"use client";
import React from "react";
import type { ProjectMemory, MemoryType } from "@/lib/types";
import { fetchMemories, addMemory, deleteMemory } from "@/lib/api";
import { Button, Card, EmptyState, Icons, Pill, SectionTitle, cn } from "./ui";

const TYPE_TONE: Record<MemoryType, "indigo" | "emerald" | "sky" | "amber"> = {
  fact: "indigo",
  preference: "emerald",
  context: "sky",
  entity: "amber",
};

const MEMORY_TYPES: MemoryType[] = ["fact", "preference", "context", "entity"];

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200">
        <div
          className={cn("h-full rounded-full",
            pct >= 75 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-rose-400")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10.5px] tabular-nums text-slate-400">{pct}%</span>
    </div>
  );
}

export default function MemoryViewer({ workspaceId }: { workspaceId: string }) {
  const [items, setItems] = React.useState<ProjectMemory[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [adding, setAdding] = React.useState(false);
  const [form, setForm] = React.useState<{ memory_type: MemoryType; key: string; value: string }>({
    memory_type: "fact", key: "", value: "",
  });

  const load = React.useCallback(() => {
    setLoading(true);
    fetchMemories(workspaceId)
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  React.useEffect(() => { load(); }, [load]);

  const onForget = async (id: string) => {
    setItems((prev) => prev.filter((m) => m.id !== id));
    try { await deleteMemory(workspaceId, id); } catch { load(); }
  };

  const onAdd = async () => {
    if (!form.key.trim() || !form.value.trim()) return;
    try {
      const created = await addMemory(workspaceId, form.memory_type, form.key.trim(), form.value.trim());
      setItems((prev) => [created, ...prev]);
      setForm({ memory_type: "fact", key: "", value: "" });
      setAdding(false);
    } catch { /* ignore */ }
  };

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <SectionTitle hint="facts the assistant remembers across this workspace">
          Project Memory
        </SectionTitle>
        <Button variant="ghost" size="sm" onClick={() => setAdding((a) => !a)}>
          <Icons.plus className="h-3.5 w-3.5" />Add memory
        </Button>
      </div>

      {adding && (
        <div className="mb-3 space-y-2 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <div className="flex gap-2">
            <select
              value={form.memory_type}
              onChange={(e) => setForm((f) => ({ ...f, memory_type: e.target.value as MemoryType }))}
              className="focus-ring rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-[12px] text-slate-700"
            >
              {MEMORY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input
              value={form.key}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              placeholder="key (e.g. preferred_format)"
              className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px]"
            />
          </div>
          <textarea
            value={form.value}
            onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
            placeholder="value"
            rows={2}
            className="focus-ring w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[12px]"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setAdding(false)}>Cancel</Button>
            <Button size="sm" onClick={onAdd} disabled={!form.key.trim() || !form.value.trim()}>Save</Button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="py-6 text-center text-[12px] text-slate-400">Loading memory…</p>
      ) : items.length === 0 ? (
        <EmptyState icon={<Icons.spark className="h-6 w-6" />} title="No memory yet">
          As you generate artifacts in this workspace, the assistant extracts durable facts,
          entities, and preferences here — and uses them on later questions.
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {items.map((m) => (
            <li key={m.id} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Pill tone={TYPE_TONE[m.memory_type]}>{m.memory_type}</Pill>
                    <span className="truncate font-mono text-[12px] font-medium text-slate-700">{m.key}</span>
                  </div>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-slate-600">{m.value}</p>
                </div>
                <button
                  onClick={() => onForget(m.id)}
                  title="Forget this"
                  className="shrink-0 rounded-md p-1 text-slate-400 transition hover:bg-rose-50 hover:text-rose-500"
                >
                  <Icons.x className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <ConfidenceBar value={m.confidence} />
                <span className="text-[10.5px] text-slate-400">used {m.last_used?.slice(0, 10)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
