"use client";
import React from "react";
import type { AskResponse, Evidence, GenerationStep } from "@/lib/types";
import { Card, Icons, Pill, RouteBadge, SectionTitle, cn } from "./ui";

/* ---------- Step Flow ---------- */
function StepChip({
  step,
  color,
}: {
  step: GenerationStep;
  color: string;
}) {
  return (
    <div className="flex flex-col items-center text-center">
      <div
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-sm",
          color
        )}
      >
        {step.step === "routing" && <Icons.route className="h-4 w-4" />}
        {step.step === "sql_generation" && <Icons.db className="h-4 w-4" />}
        {step.step === "document_retrieval" && <Icons.search className="h-4 w-4" />}
        {step.step === "generation" && <Icons.spark className="h-4 w-4" />}
        {step.step === "verification" && <Icons.shield className="h-4 w-4" />}
      </div>
      <span className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {step.step.replace("_", " ")}
      </span>
      <span className="mt-0.5 text-[11px] text-slate-600">
        {step.duration_ms}ms
      </span>
      {step.decision && (
        <span className="mt-0.5 text-[10px] text-slate-400 max-w-[80px] truncate">
          {step.decision}
        </span>
      )}
    </div>
  );
}

const STEP_COLORS: Record<string, string> = {
  routing: "bg-indigo-500",
  sql_generation: "bg-sky-500",
  document_retrieval: "bg-emerald-500",
  generation: "bg-amber-500",
  verification: "bg-green-500",
};

function StepFlow({ steps }: { steps: GenerationStep[] }) {
  if (steps.length === 0) return null;
  return (
    <div className="flex items-start gap-1 overflow-x-auto py-2">
      {steps.map((s, i) => (
        <React.Fragment key={s.step}>
          <StepChip step={s} color={STEP_COLORS[s.step] ?? "bg-slate-500"} />
          {i < steps.length - 1 && (
            <div className="mt-4 flex items-center px-1 text-slate-300">
              <Icons.arrowR className="h-3.5 w-3.5" />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

/* ---------- Source Contribution Bar ---------- */
function ContributionBar({
  evidence,
}: {
  evidence: Evidence[];
}) {
  // Group by source
  const sources: Record<string, { count: number; kind: string; pct: number }> = {};
  const usedEvidence = evidence.filter((e) => e.used);
  for (const e of usedEvidence) {
    const key = e.source_name;
    if (!sources[key]) sources[key] = { count: 0, kind: e.source_kind, pct: 0 };
    sources[key].count++;
  }
  // Compute percentages
  const total = usedEvidence.length || 1;
  for (const key of Object.keys(sources)) {
    sources[key].pct = Math.round((sources[key].count / total) * 100);
  }

  const entries = Object.entries(sources).sort((a, b) => b[1].pct - a[1].pct);
  const colors = ["bg-indigo-500", "bg-emerald-500", "bg-sky-500", "bg-amber-500", "bg-rose-500"];

  return (
    <div className="space-y-2">
      {entries.map(([name, { pct, kind }], i) => (
        <div key={name}>
          <div className="mb-1 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[11.5px] font-medium text-slate-700">
              {kind === "relational" ? (
                <Icons.db className="h-3 w-3 text-sky-500" />
              ) : (
                <Icons.doc className="h-3 w-3 text-emerald-500" />
              )}
              {name}
            </span>
            <span className="text-[11px] font-semibold text-slate-500">{pct}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn("h-full rounded-full transition-all", colors[i % colors.length])}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Trust Details ---------- */
function TrustItem({ e }: { e: Evidence }) {
  const tf = e.trust_factors;
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-2.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11.5px] font-medium text-slate-700">
          <span className="rounded bg-indigo-50 px-1 py-0.5 font-mono text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200">
            {e.id}
          </span>
          {e.citation_label}
        </span>
        {e.contribution_percentage != null && (
          <Pill tone="indigo">{e.contribution_percentage}%</Pill>
        )}
      </div>
      {tf && (
        <div className="mt-1.5 flex flex-wrap gap-2 text-[10.5px] text-slate-500">
          {tf.retrieval_score != null && (
            <span>retrieval: {tf.retrieval_score.toFixed(3)}</span>
          )}
          {tf.rerank_score != null && (
            <span>rerank: {tf.rerank_score.toFixed(3)}</span>
          )}
          {tf.is_primary_source && <Pill tone="emerald">primary</Pill>}
          {tf.trust_summary && (
            <span className="text-slate-400">{tf.trust_summary}</span>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- Citation Map (Section 6.2e) ---------- */
function CitationMap({ answer, evidence }: { answer: string; evidence: Evidence[] }) {
  const [active, setActive] = React.useState<string | null>(null);
  const byId = React.useMemo(() => new Map(evidence.map((e) => [e.id, e])), [evidence]);
  // Split the answer into text + clickable [eN] marker tokens.
  const tokens = React.useMemo(() => answer.split(/(\[e\d+\])/g), [answer]);

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {/* left: answer with clickable citations */}
      <div className="rounded-lg border border-slate-200 bg-white p-3 text-[12.5px] leading-relaxed text-slate-700">
        {tokens.map((tok, i) => {
          const m = tok.match(/^\[(e\d+)\]$/);
          if (m && byId.has(m[1])) {
            const id = m[1];
            return (
              <button
                key={i}
                onClick={() => setActive(id)}
                className={cn(
                  "mx-0.5 rounded px-1 text-[10px] font-bold ring-1 transition",
                  active === id
                    ? "bg-indigo-600 text-white ring-indigo-600"
                    : "bg-indigo-50 text-indigo-600 ring-indigo-200 hover:bg-indigo-100"
                )}
              >
                {id}
              </button>
            );
          }
          return <span key={i}>{tok}</span>;
        })}
      </div>
      {/* right: evidence passages, highlighted on selection */}
      <div className="space-y-2">
        {evidence.map((e) => (
          <div
            key={e.id}
            className={cn(
              "rounded-lg border p-2.5 text-[11.5px] leading-relaxed transition",
              active === e.id
                ? "border-indigo-300 bg-indigo-50/60 ring-1 ring-indigo-200"
                : "border-slate-200 bg-slate-50/40"
            )}
          >
            <div className="mb-1 flex items-center gap-1.5">
              <span className="rounded bg-indigo-50 px-1 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200">{e.id}</span>
              <span className="truncate font-medium text-slate-500">{e.citation_label}</span>
            </div>
            <p className="line-clamp-4 text-slate-600">{e.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Main Panel ---------- */
export default function ExplainabilityPanel({
  resp,
}: {
  resp: AskResponse;
}) {
  const t = resp.trace;
  const steps = t.generation_steps ?? [];
  const usedEvidence = t.evidence.filter((e) => e.used);

  return (
    <Card className="p-4 space-y-5 fade-up">
      <SectionTitle>🔍 How This Answer Was Produced</SectionTitle>

      {/* Step flowchart */}
      {steps.length > 0 && (
        <div>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Pipeline Steps
          </h4>
          <StepFlow steps={steps} />
        </div>
      )}

      {/* Source contribution */}
      {usedEvidence.length > 0 && (
        <div>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Source Contribution
          </h4>
          <ContributionBar evidence={t.evidence} />
        </div>
      )}

      {/* Trust details */}
      {usedEvidence.some((e) => e.trust_factors || e.contribution_percentage != null) && (
        <div>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Trust Details
          </h4>
          <div className="space-y-1.5">
            {usedEvidence.map((e) => (
              <TrustItem key={e.id} e={e} />
            ))}
          </div>
        </div>
      )}

      {/* SQL details (only for SQL/HYBRID) */}
      {t.sql_executions.length > 0 && (
        <div>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            SQL Details
          </h4>
          <div className="space-y-2">
            {t.sql_executions.map((s, i) => (
              <div
                key={i}
                className="rounded-lg border border-slate-200 bg-slate-50/60 p-2.5"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <Pill tone="sky">{s.purpose}</Pill>
                  <Pill>{s.row_count} rows</Pill>
                  <Pill>
                    <Icons.clock className="h-3 w-3" />
                    {s.duration_ms}ms
                  </Pill>
                </div>
                <pre className="code-surface scroll-thin overflow-x-auto p-2 text-[10.5px] leading-relaxed">
                  {s.validated_sql || s.generated_sql}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Citation Map (Section 6.2e) */}
      {usedEvidence.length > 0 && /\[e\d+\]/.test(resp.answer) && (
        <div>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Citation Map
          </h4>
          <CitationMap answer={resp.answer} evidence={usedEvidence} />
        </div>
      )}

      {/* Timing summary */}
      {t.timings.length > 0 && (
        <div>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Timing Breakdown
          </h4>
          <div className="flex flex-wrap gap-2">
            {t.timings.map((tm) => (
              <Pill key={tm.name}>
                {tm.name}: {tm.duration_ms}ms
              </Pill>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
