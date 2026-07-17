"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import { Button, Card, Icons, Pill, RouteBadge, SectionTitle, cn, isRTL } from "./ui";
import { CitationChips, CitedText, EvidenceItem, useCiteHighlight } from "./trace";
import { segmentAnswer } from "@/lib/tableParser";
import AnswerTable from "./AnswerTable";
import ReadAloud from "./ReadAloud";
import VerificationBadge from "./VerificationBadge";
import AnswerStateBanner from "./AnswerStateBanner";
import ExplainabilityPanel from "./ExplainabilityPanel";
import MultiAgentTrace from "./MultiAgentTrace";

export default function AnswerPanel({
  resp, onOpenInspector,
}: { resp: AskResponse; onOpenInspector?: () => void }) {
  const t = resp.trace;
  const { highlight, onCite } = useCiteHighlight();
  const rtlAnswer = isRTL(resp.answer);
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
  const risk = resp.hallucination_risk_score;
  // The tri-state grounding wall — the single explicit label the backend computed.
  const state = resp.answer_state ?? (resp.insufficient ? "insufficient" : "grounded");
  // Grounding-first: the router can return NONE yet the document safety net recovers a real,
  // grounded answer. Without this, the "NONE · Insufficient evidence" badge would contradict
  // the cited answer shown below it.
  const recoveredFromDocs =
    t.route?.route === "NONE" && t.evidence.length > 0 && !resp.insufficient;

  // Ctrl+E (dispatched from the page) toggles the explainability panel.
  React.useEffect(() => {
    const toggle = () => setShowExplain((v) => !v);
    window.addEventListener("aba:toggle-explain", toggle);
    return () => window.removeEventListener("aba:toggle-explain", toggle);
  }, []);

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
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-faint">Routed to</span>
          {t.route ? <RouteBadge route={t.route.route} withLabel /> : <Pill>—</Pill>}
          {recoveredFromDocs && (
            <span title="The router declined, but a direct document search recovered a grounded, cited answer.">
              <Pill tone="emerald">
                <Icons.check className="h-3 w-3" />
                recovered from documents
              </Pill>
            </span>
          )}
        </div>
        {t.route && (
          <span
            className="text-[12px] text-muted"
            title="How confident the router was about which source to use — not a measure of answer correctness."
          >
            {(t.route.confidence * 100).toFixed(0)}% router confidence
            {t.route.agentic && " · agentic"}
          </span>
        )}
        {retrievalSummary && (
          <span className="flex items-center gap-1.5 text-[12px] text-muted">
            <Icons.search className="h-3.5 w-3.5 text-sky-500" />{retrievalSummary}
          </span>
        )}

        <span className="ml-auto flex items-center gap-1.5 text-[12px]">
          <VerificationBadge resp={resp} onClick={() => setShowExplain((v) => !v)} />
        </span>
      </Card>

      {/* The tri-state grounding wall — prominent, full-width, one unmistakable label. */}
      <AnswerStateBanner resp={resp} riskPct={risk != null ? risk * 100 : null} />

      {/* Verification warning */}
      {resp.verification_warning && (
        <Card className="flex items-start gap-2 px-4 py-3 text-[13px] text-amber-700 ring-1 ring-amber-200 dark:text-amber-300 dark:ring-amber-500/30">
          <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />
          {resp.verification_warning}
        </Card>
      )}

      {/* answer */}
      <Card className={cn("p-5",
        state === "insufficient" && "ring-1 ring-slate-200 dark:ring-white/10",
        state === "reasoned" && "ring-1 ring-amber-200 dark:ring-amber-500/30")}>
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
          <div className="mt-4 border-t border-line pt-3.5">
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

      {/* Agent (iterative) timeline */}
      {resp.agent_trace && resp.agent_trace.steps?.length > 0 && (
        <Card className="p-4">
          <SectionTitle hint={`${resp.agent_trace.iterations} round(s) · ${resp.agent_trace.tools_used.join(", ")}`}>
            Agent reasoning
          </SectionTitle>
          <div className="space-y-2">
            {resp.agent_trace.steps.map((s, i) => (
              <div key={i} className="rounded-xl border border-line bg-surface-2/60 p-2.5">
                <div className="flex items-center gap-2 text-[12px]">
                  <Pill tone="indigo">step {s.iteration}</Pill>
                  <span className="font-mono text-[11px] text-indigo-600 dark:text-indigo-300">{s.tool}</span>
                  {typeof (s.args as any)?.query === "string" && (
                    <span className="truncate text-muted">“{String((s.args as any).query)}”</span>
                  )}
                </div>
                {s.observation && (
                  <p className="mt-1.5 whitespace-pre-wrap text-[11.5px] leading-relaxed text-muted">{s.observation}</p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* supporting evidence — only the passages/rows the answer is grounded in */}
      {supporting.length > 0 && (
        <Card className="p-4">
          <SectionTitle hint={supportingHint}>Supporting evidence</SectionTitle>
          <p className="-mt-1 mb-2.5 text-[11.5px] text-faint">
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
