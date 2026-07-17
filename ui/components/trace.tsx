"use client";
import React from "react";
import type {
  AskResponse, Evidence, RetrievalCandidate, SqlExecutionTrace,
} from "@/lib/types";
import { Icons, OriginTag, Pill, RouteBadge, ScoreBar, cn, isRTL } from "./ui";

/* ---------- cite → scroll/highlight ---------- */
export function useCiteHighlight() {
  const [highlight, setHighlight] = React.useState<string | null>(null);
  const onCite = React.useCallback((id: string) => {
    setHighlight(id);
    document.getElementById(`ev-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => setHighlight(null), 1700);
  }, []);
  return { highlight, onCite };
}

/* ---------- answer text with clickable [eN] markers ---------- */
export function CitedText({ text, onCite, rtl }: { text: string; onCite: (id: string) => void; rtl: boolean }) {
  const parts = text.split(/(\[e\d+\])/g);
  return (
    <div dir={rtl ? "rtl" : "ltr"}
      className={cn("whitespace-pre-wrap text-[15px] leading-[1.75] text-body", rtl && "text-right")}>
      {parts.map((p, i) => {
        const m = p.match(/^\[(e\d+)\]$/);
        if (m) return (
          <button key={i} onClick={() => onCite(m[1])}
            className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded-md bg-indigo-50 px-1.5 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200 transition hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30">
            {m[1]}
          </button>
        );
        return <span key={i}>{p}</span>;
      })}
    </div>
  );
}

/* ---------- evidence ---------- */
export function EvidenceItem({ e, highlight, compact, showUsed }: {
  e: Evidence; highlight: boolean; compact?: boolean; showUsed?: boolean;
}) {
  const rtl = isRTL(e.content);
  const bodyRef = React.useRef<HTMLParagraphElement>(null);
  const [clipped, setClipped] = React.useState(false);
  React.useEffect(() => {
    const el = bodyRef.current;
    if (el) setClipped(el.scrollHeight > el.clientHeight + 2);
  }, [e.content, compact]);
  // Evidence is never truncated — full text is always shown (scrollable when long) so
  // citations can be verified in full. `compact` only caps the visible height.
  return (
    <div id={`ev-${e.id}`}
      className={cn("rounded-xl border p-3 transition",
        highlight ? "cite-pulse border-indigo-300 bg-indigo-50/60 dark:bg-indigo-500/10" : "border-line bg-surface")}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30">{e.id}</span>
        <Pill tone={e.source_kind === "relational" ? "sky" : "emerald"}>
          {e.source_kind === "relational" ? <Icons.db className="h-3 w-3" /> : <Icons.doc className="h-3 w-3" />}
          {e.source_kind === "relational" ? "database" : "document"}
        </Pill>
        <span className="font-mono text-[11px] text-muted">{e.citation_label}</span>
        <OriginTag origin={e.origin} />
        {showUsed && e.used && <Pill tone="emerald"><Icons.check className="h-3 w-3" />used in answer</Pill>}
        {e.score != null && <span className="ml-auto font-mono text-[10px] text-faint">score {e.score.toFixed(3)}</span>}
      </div>
      <p ref={bodyRef} dir={rtl ? "rtl" : "ltr"}
        className={cn("scroll-thin overflow-y-auto whitespace-pre-wrap text-[12.5px] leading-relaxed text-body",
          rtl && "text-right", compact ? "max-h-44" : "")}>
        {e.content}
      </p>
      {compact && clipped && (
        <p className="mt-1 flex items-center gap-1 text-[10.5px] font-medium text-faint">
          <Icons.chevron className="h-3 w-3 rotate-90" />
          scroll for full text
        </p>
      )}
    </div>
  );
}

export function CitationChips({ citations, onCite }: { citations: Evidence[]; onCite: (id: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {citations.map((c) => (
        <button key={c.id} onClick={() => onCite(c.id)}
          title={c.origin === "uploaded" ? "From your upload" : c.origin === "sample" ? "From sample data" : undefined}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2 py-1 text-[11px] transition hover:border-indigo-300 hover:bg-indigo-50">
          <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">{c.id}</span>
          {c.source_kind === "relational" ? <Icons.db className="h-3 w-3 text-sky-500" /> : <Icons.doc className="h-3 w-3 text-emerald-500" />}
          <span className="text-muted">{c.citation_label}</span>
          {c.origin === "uploaded" && <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />}
        </button>
      ))}
    </div>
  );
}

/* ---------- SQL block ---------- */
export function SqlBlock({ s }: { s: SqlExecutionTrace }) {
  const cols = s.columns.length ? s.columns : Object.keys(s.rows[0] ?? {});
  return (
    <div className="rounded-xl border border-line bg-surface-2/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill tone="sky">{s.purpose}</Pill>
        {s.valid ? <Pill tone="emerald"><Icons.check className="h-3 w-3" />read-only · validated</Pill>
                 : <Pill tone="rose">rejected</Pill>}
        <Pill>{s.row_count} rows</Pill>
        <Pill><Icons.clock className="h-3 w-3" />{s.duration_ms} ms</Pill>
        {s.tables.length > 0 && <Pill>{s.tables.join(", ")}</Pill>}
      </div>
      <pre className="scroll-thin code-surface overflow-x-auto p-2.5 font-mono text-[11px] leading-relaxed">{s.validated_sql || s.generated_sql}</pre>
      {s.validation_error && <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-400">error: {s.validation_error}</p>}
      {s.rows.length > 0 && (
        <div className="scroll-thin mt-2 max-h-56 overflow-auto rounded-lg border border-line">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-surface-2/95 text-muted backdrop-blur">
              <tr>{cols.map((c) => <th key={c} className="px-2.5 py-1.5 font-medium">{c}</th>)}</tr>
            </thead>
            <tbody className="font-mono text-body">
              {s.rows.slice(0, 12).map((r, i) => (
                <tr key={i} className="border-t border-line hover:bg-surface-2">
                  {cols.map((c) => <td key={c} className="px-2.5 py-1.5">{String((r as any)[c] ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {s.rows.length > 12 && (
        <p className="mt-1.5 flex items-center gap-1.5 text-[11px] font-medium text-amber-700 dark:text-amber-400">
          <Icons.alert className="h-3 w-3" />
          +{s.rows.length - 12} more row(s) (truncated in view) — open the full trace to see all {s.row_count}.
        </p>
      )}
    </div>
  );
}

/* ---------- retrieval candidates ---------- */
export function CandidatesTable({ rows }: { rows: RetrievalCandidate[] }) {
  return (
    <div className="scroll-thin max-h-72 overflow-auto rounded-lg border border-line">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-surface-2/95 text-muted backdrop-blur">
          <tr>{["#", "document", "p.", "dense", "bm25", "rrf", "rerank", ""].map((h) =>
            <th key={h} className="px-2.5 py-1.5 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.chunk_id} className={cn("border-t border-line", c.selected ? "bg-indigo-50/70 dark:bg-indigo-500/10" : "hover:bg-surface-2")}>
              <td className="px-2.5 py-1.5 font-mono text-muted">{c.final_rank}</td>
              <td className="px-2.5 py-1.5"><span className="text-fg">{c.document}</span>
                {c.keyword_hit && <span className="ml-1.5 rounded bg-amber-50 px-1 py-0.5 text-[9px] font-semibold text-amber-700 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30">exact</span>}
                {c.section && <span className="ml-1 text-faint" title={c.section}>· {c.section}</span>}</td>
              <td className="px-2.5 py-1.5 font-mono text-muted">{c.page ?? "—"}</td>
              <td className="px-2.5 py-1.5 font-mono text-muted">{c.dense_rank ? `#${c.dense_rank}` : "—"}</td>
              <td className="px-2.5 py-1.5 font-mono text-muted">{c.bm25_rank ? `#${c.bm25_rank}` : "—"}</td>
              <td className="px-2.5 py-1.5"><ScoreBar value={c.rrf_score} max={0.05} /></td>
              <td className="px-2.5 py-1.5 font-mono text-muted">{c.rerank_score != null ? c.rerank_score.toFixed(2) : "—"}</td>
              <td className="px-2.5 py-1.5">{c.selected && <Pill tone="indigo">selected</Pill>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- pipeline stepper ---------- */
function StageNode({ icon, label, value, accent }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; accent: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center px-1 text-center">
      <div className={cn("mb-2 flex h-9 w-9 items-center justify-center rounded-xl ring-1 ring-inset", accent)}>
        {icon}
      </div>
      <div className="text-[9.5px] font-semibold uppercase tracking-[0.1em] text-faint">{label}</div>
      <div className="mt-0.5 truncate text-[13px] font-medium text-fg">{value}</div>
    </div>
  );
}

export function Stepper({ resp }: { resp: AskResponse }) {
  const t = resp.trace;
  const docSel = t.document_retrieval?.candidates.filter((c) => c.selected).length ?? 0;
  const sqlRows = t.sql_executions.filter((s) => s.purpose !== "entity_link").reduce((a, s) => a + s.row_count, 0);
  const retrieval = [t.sql_executions.length ? `${sqlRows} rows` : "", docSel ? `${docSel} passages` : ""]
    .filter(Boolean).join(" · ") || "—";
  const verified = t.citation_check?.verified;

  const stages = [
    { icon: <Icons.question className="text-muted" />, label: "Question", accent: "bg-surface-2 text-muted ring-line",
      value: t.languages.includes("de") ? "German" : "English" },
    { icon: <Icons.route className="text-indigo-500" />, label: "Route", accent: "bg-indigo-50 ring-indigo-200 dark:bg-indigo-500/10 dark:ring-indigo-500/30",
      value: t.route ? <RouteBadge route={t.route.route} small /> : "—" },
    { icon: <Icons.search className="text-sky-500" />, label: "Retrieval", accent: "bg-sky-50 ring-sky-200 dark:bg-sky-500/10 dark:ring-sky-500/30", value: retrieval },
    { icon: <Icons.layers className="text-cyan-500" />, label: "Evidence", accent: "bg-cyan-50 ring-cyan-200 dark:bg-cyan-500/10 dark:ring-cyan-500/30", value: `${t.evidence.length}` },
    { icon: <Icons.spark className={resp.insufficient ? "text-amber-500" : "text-emerald-500"} />, label: "Answer",
      accent: resp.insufficient ? "bg-amber-50 ring-amber-200 dark:bg-amber-500/10 dark:ring-amber-500/30" : "bg-emerald-50 ring-emerald-200 dark:bg-emerald-500/10 dark:ring-emerald-500/30",
      value: resp.insufficient ? "insufficient" : "grounded" },
    { icon: <Icons.shield className={verified ? "text-emerald-500" : "text-rose-500"} />, label: "Citations",
      accent: verified ? "bg-emerald-50 ring-emerald-200 dark:bg-emerald-500/10 dark:ring-emerald-500/30" : "bg-rose-50 ring-rose-200 dark:bg-rose-500/10 dark:ring-rose-500/30",
      value: t.citation_check ? <span className={verified ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}>
        {t.citation_check.cited_ids.length} {verified ? "✓" : "✗"}</span> : "—" },
  ];

  return (
    <div className="flex items-start">
      {stages.map((s, i) => (
        <React.Fragment key={s.label}>
          <StageNode {...s} />
          {i < stages.length - 1 && (
            <div className="mt-4 flex shrink-0 items-center px-0.5 text-faint">
              <Icons.arrowR className="h-3.5 w-3.5" />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}
