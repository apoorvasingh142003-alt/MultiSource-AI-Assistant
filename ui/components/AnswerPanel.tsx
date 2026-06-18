"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import { Button, Card, Icons, Pill, RouteBadge, SectionTitle, cn, isRTL } from "./ui";
import { CitationChips, CitedText, EvidenceItem, useCiteHighlight } from "./trace";
import { segmentAnswer } from "@/lib/tableParser";
import AnswerTable from "./AnswerTable";
import ReadAloud from "./ReadAloud";
import VerificationBadge from "./VerificationBadge";
import ExplainabilityPanel from "./ExplainabilityPanel";
import MultiAgentTrace from "./MultiAgentTrace";

export default function AnswerPanel({
  resp, onOpenInspector,
}: { resp: AskResponse; onOpenInspector?: () => void }) {
  const t = resp.trace;
  const { highlight, onCite } = useCiteHighlight();
  const rtlAnswer = isRTL(resp.answer) || t.languages.includes("he");
  const docSel = t.document_retrieval?.candidates.filter((c) => c.selected).length ?? 0;
  const sqlRows = t.sql_executions.filter((s) => s.purpose !== "entity_link").reduce((a, s) => a + s.row_count, 0);
  const retrievalSummary = [
    t.sql_executions.length ? `${sqlRows} database row(s)` : "",
    docSel ? `${docSel} document passage(s)` : "",
  ].filter(Boolean).join(" · ");
  const supporting = t.evidence.filter((e) => e.used);
  const supportingHint = supporting.length === t.evidence.length
    ? `${supporting.length} item(s)`
    : `${supporting.length} of ${t.evidence.length} retrieved`;

  const [showExplain, setShowExplain] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const isGK = t.route?.route === "GENERAL_KNOWLEDGE";

  // Parse answer segments for table detection
  const segments = segmentAnswer(resp.answer);
  const hasTables = segments.some((s) => s.type === "table");

  const copyAnswer = async () => {
    await navigator.clipboard.writeText(resp.answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fade-up space-y-4">
      {/* routing summary */}
      <Card className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <div className="flex items-center gap-2">
          <Icons.route className="h-4 w-4 text-indigo-500" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">Routed to</span>
          {t.route ? <RouteBadge route={t.route.route} withLabel /> : <Pill>—</Pill>}
        </div>
        {t.route && (
          <span className="text-[12px] text-slate-500">
            {(t.route.confidence * 100).toFixed(0)}% confidence
            {t.route.agentic && " · agentic"}
          </span>
        )}
        {retrievalSummary && (
          <span className="flex items-center gap-1.5 text-[12px] text-slate-500">
            <Icons.search className="h-3.5 w-3.5 text-sky-500" />{retrievalSummary}
          </span>
        )}

        {/* General Knowledge note */}
        {isGK && (
          <span className="flex items-center gap-1.5 text-[12px] text-blue-600">
            <Icons.info className="h-3.5 w-3.5" />
            Answered from model knowledge — no indexed source contributed.
          </span>
        )}

        <span className="ml-auto flex items-center gap-1.5 text-[12px]">
          <VerificationBadge resp={resp} onClick={() => setShowExplain((v) => !v)} />
        </span>
      </Card>

      {/* Verification warning */}
      {resp.verification_warning && (
        <Card className="flex items-start gap-2 px-4 py-3 text-[13px] text-amber-700 ring-1 ring-amber-200">
          <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />
          {resp.verification_warning}
        </Card>
      )}

      {/* answer */}
      <Card className={cn("p-5", resp.insufficient && "ring-1 ring-amber-200")}>
        <div className="mb-3 flex items-center justify-between">
          <SectionTitle>Answer</SectionTitle>
          <div className="flex items-center gap-1.5">
            <ReadAloud text={resp.answer} />
            <Button variant="ghost" size="sm" onClick={() => setShowExplain((v) => !v)}>
              <Icons.search className="h-3.5 w-3.5" />Explain
            </Button>
            <Button variant="ghost" size="sm" onClick={copyAnswer}>
              <Icons.layers className="h-3.5 w-3.5" />
              {copied ? "Copied!" : "Copy"}
            </Button>
            {onOpenInspector && (
              <Button variant="ghost" size="sm" onClick={onOpenInspector}>
                <Icons.inspect className="h-3.5 w-3.5" />Trace
              </Button>
            )}
          </div>
        </div>
        {resp.insufficient && (
          <div className="mb-3"><Pill tone="amber"><Icons.alert className="h-3 w-3" />Insufficient evidence — not answered</Pill></div>
        )}

        {/* Render answer with inline tables */}
        {hasTables ? (
          <div>
            {segments.map((seg, i) =>
              seg.type === "text" ? (
                <CitedText key={i} text={seg.content} onCite={onCite} rtl={rtlAnswer} />
              ) : (
                <AnswerTable key={i} table={seg.table} />
              )
            )}
          </div>
        ) : (
          <CitedText text={resp.answer} onCite={onCite} rtl={rtlAnswer} />
        )}

        {resp.citations.length > 0 && (
          <div className="mt-4 border-t border-slate-100 pt-3.5">
            <SectionTitle>Sources</SectionTitle>
            <CitationChips citations={resp.citations} onCite={onCite} />
          </div>
        )}
      </Card>

      {/* Explainability panel */}
      {showExplain && <ExplainabilityPanel resp={resp} />}

      {/* Multi-agent trace */}
      {resp.multi_agent_trace && (
        <MultiAgentTrace trace={resp.multi_agent_trace} />
      )}

      {/* supporting evidence — only the passages/rows the answer is grounded in */}
      {supporting.length > 0 && (
        <Card className="p-4">
          <SectionTitle hint={supportingHint}>Supporting evidence</SectionTitle>
          <p className="-mt-1 mb-2.5 text-[11.5px] text-slate-400">
            The exact passages and records this answer is grounded in.
            {supporting.length < t.evidence.length && " Open the trace to see everything that was retrieved."}
          </p>
          <div className="space-y-2">
            {supporting.map((e) => <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} compact />)}
          </div>
        </Card>
      )}
    </div>
  );
}
