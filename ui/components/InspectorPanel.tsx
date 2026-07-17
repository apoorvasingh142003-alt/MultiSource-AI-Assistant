"use client";
import React from "react";
import type { AskResponse, Inventory } from "@/lib/types";
import { Icons, EmptyState, cn } from "./ui";
import { EvidenceItem, useCiteHighlight } from "./trace";
import AnswerPanel from "./AnswerPanel";
import Inspector from "./Inspector";
import Workspace from "./Workspace";

export type InspectorTab = "answer" | "trace" | "evidence" | "sources";

const TABS: { id: InspectorTab; label: string; icon: (p: { className?: string }) => JSX.Element }[] = [
  { id: "answer", label: "Answer", icon: Icons.spark },
  { id: "trace", label: "Trace", icon: Icons.route },
  { id: "evidence", label: "Evidence", icon: Icons.layers },
  { id: "sources", label: "Sources", icon: Icons.doc },
];

export interface SourcesProps {
  inventory: Inventory | null;
  onUploadPdf: (files: File[]) => void;
  onUploadSqlite: (files: File[]) => void;
  onReset: () => void;
  pdfBusy: boolean; sqliteBusy: boolean; resetting: boolean;
  pdfMsg: string | null; pdfErr: string | null; dbMsg: string | null; dbErr: string | null;
}

/* ============================================================================
 * The inspector drawer — the "one panel away" surface. Slides in from the right
 * (overlay on small screens, docked column on wide ones). Everything heavy that
 * used to crowd the answer lives here, split into four tabs:
 *   Answer   — the tri-state banner + answer + citations + supporting evidence
 *   Trace    — routing, SQL, hybrid retrieval, cost/timings (full pipeline)
 *   Evidence — every retrieved passage/row
 *   Sources  — uploaded PDFs/DBs + upload dropzones
 * Reuses the existing rich components verbatim so nothing about the trace/
 * grounding rendering changes — only where it lives.
 * ========================================================================== */
export default function InspectorPanel({
  open, resp, tab, onTabChange, onClose, sources,
}: {
  open: boolean;
  resp: AskResponse | null;
  tab: InspectorTab;
  onTabChange: (t: InspectorTab) => void;
  onClose: () => void;
  sources: SourcesProps;
}) {
  const { highlight } = useCiteHighlight();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && open) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* scrim — mobile/overlay only */}
      <div
        className={cn(
          "fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-sm transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />

      <aside
        className={cn(
          "fixed right-0 top-0 z-40 flex h-full w-full max-w-[440px] flex-col border-l border-line bg-app shadow-pop transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
        aria-hidden={!open}
      >
        {/* header + tabs */}
        <div className="glass sticky top-0 z-10 border-b border-line">
          <div className="flex items-center justify-between px-4 pt-3">
            <span className="flex items-center gap-2 text-[13px] font-bold text-fg">
              <Icons.inspect className="h-4 w-4 text-accent" /> Inspector
            </span>
            <button onClick={onClose} title="Close inspector"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-faint transition hover:bg-surface-2 hover:text-fg">
              <Icons.x className="h-4 w-4" />
            </button>
          </div>
          <div className="flex gap-1 px-3 pb-2 pt-2">
            {TABS.map((t) => {
              const active = tab === t.id;
              return (
                <button key={t.id} onClick={() => onTabChange(t.id)}
                  className={cn(
                    "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] font-semibold transition",
                    active ? "bg-accent text-white shadow-sm" : "text-muted hover:bg-surface-2 hover:text-fg",
                  )}>
                  <t.icon className="h-3.5 w-3.5" />{t.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* body */}
        <div className="scroll-thin flex-1 overflow-y-auto px-4 py-4">
          {tab === "sources" ? (
            <Workspace
              inventory={sources.inventory}
              onUploadPdf={sources.onUploadPdf}
              onUploadSqlite={sources.onUploadSqlite}
              onReset={sources.onReset}
              pdfBusy={sources.pdfBusy} sqliteBusy={sources.sqliteBusy} resetting={sources.resetting}
              pdfMsg={sources.pdfMsg} pdfErr={sources.pdfErr} dbMsg={sources.dbMsg} dbErr={sources.dbErr}
            />
          ) : !resp ? (
            <EmptyState icon={<Icons.inspect className="h-6 w-6" />} title="No answer selected yet">
              Ask a question, then open the inspector on any answer to see the tri-state grounding,
              the full retrieval trace, and every piece of evidence.
            </EmptyState>
          ) : tab === "answer" ? (
            <AnswerPanel resp={resp} />
          ) : tab === "trace" ? (
            <Inspector resp={resp} />
          ) : (
            /* evidence */
            resp.trace.evidence.length > 0 ? (
              <div className="space-y-2">
                <p className="text-[11.5px] text-faint">
                  Everything retrieved for this answer. Items marked{" "}
                  <span className="font-medium text-emerald-600 dark:text-emerald-400">used in answer</span>{" "}
                  are what the response is grounded in.
                </p>
                {resp.trace.evidence.map((e) => (
                  <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} showUsed />
                ))}
              </div>
            ) : (
              <EmptyState icon={<Icons.layers className="h-6 w-6" />} title="No evidence retrieved">
                This answer wasn&apos;t grounded in any retrieved passages or rows.
              </EmptyState>
            )
          )}
        </div>
      </aside>
    </>
  );
}
