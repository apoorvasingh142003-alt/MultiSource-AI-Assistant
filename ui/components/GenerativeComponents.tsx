"use client";
import React from "react";
import type { AnswerComponent, Evidence } from "@/lib/types";
import { Icons, cn, isRTL } from "./ui";
import AnswerTable from "./AnswerTable";

/* ============================================================================
 * Generative components (Phase 3) — the inline "generative UI".
 *
 * Each component is a STRUCTURED VIEW OVER GROUNDED EVIDENCE, built deterministically
 * on the backend (app/generation/components.py) from the exact SQL rows / passages the
 * answer cites — never invented by the model. The backend only emits these for a
 * `grounded` answer, so a chart/table/timeline can never lend confident structure to a
 * reasoned or insufficient answer (the tri-state wall stays intact).
 *
 *   table    — the cited rows, sortable + copy/export (reuses AnswerTable).
 *   chart    — a self-contained SVG bar chart (no chart-lib dependency).
 *   timeline — a vertical, chronological SVG-accented list.
 *   artifact — a quoted document clause/section, with a jump-to-evidence action.
 *
 * `evidence_ids` link every component to the same [eN] evidence in the inspector, so a
 * click on "cited rows" / "source" opens exactly what it was built from.
 * ========================================================================== */

export default function GenerativeComponents({
  components, citations, onCite, onInspect,
}: {
  components: AnswerComponent[];
  citations: Evidence[];
  onCite: (id: string) => void;
  onInspect?: () => void;
}) {
  if (!components || components.length === 0) return null;
  return (
    <div className="space-y-3">
      {components.map((c, i) => (
        <ComponentCard key={i} c={c} citations={citations} onCite={onCite} onInspect={onInspect} />
      ))}
    </div>
  );
}

function ComponentCard({
  c, citations, onCite, onInspect,
}: {
  c: AnswerComponent;
  citations: Evidence[];
  onCite: (id: string) => void;
  onInspect?: () => void;
}) {
  const Icon =
    c.kind === "chart" ? Icons.chart
    : c.kind === "timeline" ? Icons.timeline
    : c.kind === "artifact" ? Icons.doc
    : Icons.table;

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-sm">
      {/* header */}
      <div className="flex items-center gap-2 border-b border-line bg-surface-2/50 px-3.5 py-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 ring-1 ring-inset ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <span className="text-[12.5px] font-semibold text-fg">{c.title}</span>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30">
          <Icons.shield className="h-3 w-3" />grounded
        </span>
      </div>

      {/* body */}
      <div className="px-1.5 pb-1.5">
        {c.kind === "table" && (
          <AnswerTable table={{ headers: c.columns, rows: c.rows, startIndex: 0, endIndex: 0 }} />
        )}
        {c.kind === "chart" && <BarChart c={c} />}
        {c.kind === "timeline" && <Timeline c={c} />}
        {c.kind === "artifact" && <Artifact c={c} />}
      </div>

      {/* footer: provenance + cited-evidence chips */}
      {(c.caption || c.evidence_ids.length > 0) && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-3.5 py-2">
          {c.caption && <span className="text-[10.5px] text-faint">{c.caption}</span>}
          {c.evidence_ids.length > 0 && (
            <div className="ml-auto flex flex-wrap items-center gap-1">
              <span className="text-[10px] font-medium text-faint">cited:</span>
              {c.evidence_ids.slice(0, 8).map((id) => (
                <button key={id} onClick={() => onCite(id)} title={`Jump to ${id} in the inspector`}
                  className="rounded-md bg-indigo-50 px-1.5 text-[10px] font-bold text-indigo-600 ring-1 ring-inset ring-indigo-200 transition hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30">
                  {id}
                </button>
              ))}
              {c.evidence_ids.length > 8 && (
                <span className="text-[10px] text-faint">+{c.evidence_ids.length - 8}</span>
              )}
              {onInspect && (
                <button onClick={onInspect} title="Open the full trace"
                  className="ml-1 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-faint transition hover:bg-surface-2 hover:text-accent">
                  <Icons.inspect className="h-3 w-3" />trace
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- bar chart (self-contained SVG, no dependency) ---------- */
function BarChart({ c }: { c: AnswerComponent }) {
  const points = c.points ?? [];
  const max = Math.max(1, ...points.map((p) => Math.abs(p.value)));
  const fmt = (n: number) =>
    Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 });

  return (
    <div className="px-3 py-3">
      {c.y_label && (
        <div className="mb-2 text-[10.5px] font-medium uppercase tracking-wider text-faint">{c.y_label}</div>
      )}
      <div className="space-y-1.5">
        {points.map((p, i) => {
          const pct = Math.max(2, (Math.abs(p.value) / max) * 100);
          return (
            <div key={i} className="flex items-center gap-2">
              <span className="w-[34%] shrink-0 truncate text-right text-[11.5px] text-muted" title={p.label}>
                {p.label}
              </span>
              <div className="relative h-5 flex-1 overflow-hidden rounded-md bg-surface-2">
                <div
                  className="bar-grow flex h-full items-center justify-end rounded-md bg-gradient-to-r from-indigo-400 to-indigo-600 pr-1.5"
                  style={{ width: `${pct}%` }}
                >
                  <span className="text-[10px] font-bold text-white/95 tabular-nums">{fmt(p.value)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {c.x_label && (
        <div className="mt-2 text-right text-[10.5px] font-medium uppercase tracking-wider text-faint">{c.x_label}</div>
      )}
    </div>
  );
}

/* ---------- timeline (vertical, chronological) ---------- */
function Timeline({ c }: { c: AnswerComponent }) {
  const events = c.events ?? [];
  return (
    <div className="px-3 py-3">
      <ol className="relative ml-2 space-y-3 border-l-2 border-indigo-200 pl-4 dark:border-indigo-500/30">
        {events.map((e, i) => (
          <li key={i} className="relative">
            <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-indigo-500 ring-2 ring-surface" />
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-mono text-[11px] font-bold text-indigo-600 dark:text-indigo-300">{e.date}</span>
              <span className="text-[13px] font-semibold text-fg">{e.title}</span>
            </div>
            {e.details && <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">{e.details}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ---------- document / clause artifact ---------- */
function Artifact({ c }: { c: AnswerComponent }) {
  const rtl = isRTL(c.body);
  return (
    <div className="px-3 py-3">
      {c.subtitle && (
        <div className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-surface-2 px-2 py-1 font-mono text-[10.5px] text-muted ring-1 ring-inset ring-line">
          <Icons.doc className="h-3 w-3 text-emerald-500" />{c.subtitle}
        </div>
      )}
      <blockquote
        dir={rtl ? "rtl" : "ltr"}
        className={cn(
          "rounded-lg border-l-[3px] border-l-emerald-400 bg-emerald-50/40 px-3 py-2 text-[12.5px] leading-relaxed text-body dark:bg-emerald-500/5",
          rtl && "border-l-0 border-r-[3px] border-r-emerald-400 text-right",
        )}
      >
        {c.body}
      </blockquote>
    </div>
  );
}
