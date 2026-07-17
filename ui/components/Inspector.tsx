"use client";
import React from "react";
import type { AskResponse, ResearchRound, ResearchTrace } from "@/lib/types";
import { Card, Collapsible, EmptyState, Icons, Pill, RouteBadge, SectionTitle } from "./ui";
import {
  CandidatesTable, EvidenceItem, SqlBlock, Stepper, useCiteHighlight,
} from "./trace";

export default function Inspector({ resp }: { resp: AskResponse | null }) {
  const { highlight } = useCiteHighlight();
  if (!resp) {
    return (
      <Card>
        <EmptyState icon={<Icons.inspect className="h-6 w-6" />} title="No retrieval trace yet">
          Ask a question in the Workspace. Every answer is recorded here in full — routing decision,
          generated SQL, hybrid retrieval scores, evidence aggregation, citation verification, timing,
          and token usage.
        </EmptyState>
      </Card>
    );
  }

  const t = resp.trace;

  return (
    <div className="fade-up space-y-4">
      <Card className="px-4 py-4"><Stepper resp={resp} /></Card>

      <Card className="flex flex-wrap items-center gap-2 px-4 py-3">
        <Pill tone="indigo">Output: {t.output_mode || "Standard Response"}</Pill>
        {t.role && <Pill>Role: {t.role}</Pill>}
      </Card>

      {t.route && (
        <Collapsible icon={<Icons.route />} title={<>Routing decision <RouteBadge route={t.route.route} small /></>}
          right={<Pill tone="indigo">{(t.route.confidence * 100).toFixed(0)}% confidence</Pill>}>
          <div className="space-y-2 text-[12.5px] text-body">
            <p>{t.route.reasoning}</p>
            {t.route.route === "NONE" && (
              <p className="text-muted">No matching evidence found in uploaded sources.</p>
            )}
            <div className="flex flex-wrap gap-2">
              {t.route.agentic && <Pill tone="indigo"><Icons.bolt className="h-3 w-3" />agentic: SQL → entities → documents</Pill>}
              <Pill>languages: {t.route.languages.join(", ")}</Pill>
              {t.route.strategy_note && <Pill>{t.route.strategy_note}</Pill>}
            </div>
            {t.route.sql_subquery && <p className="text-muted"><span className="text-faint">sql sub-query:</span> {t.route.sql_subquery}</p>}
            {t.route.document_subquery && <p className="text-muted"><span className="text-faint">document sub-query:</span> {t.route.document_subquery}</p>}
          </div>
        </Collapsible>
      )}

      {t.notes.length > 0 && (
        <Collapsible icon={<Icons.layers />} title="Orchestrator trace" right={<Pill>{t.notes.length} steps</Pill>}>
          <ol className="space-y-2">
            {t.notes.map((n, i) => (
              <li key={i} className="flex gap-2.5 text-[12.5px] text-body">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-indigo-50 font-mono text-[9px] text-indigo-600 ring-1 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30">{i + 1}</span>
                <span>{n}</span>
              </li>
            ))}
          </ol>
        </Collapsible>
      )}

      {t.research_trace && (
        <Collapsible icon={<Icons.search />} title="Deep research — iterative retrieval" defaultOpen
          right={<Pill tone="indigo">{t.research_trace.total_rounds} round(s)</Pill>}>
          <ResearchPanel rt={t.research_trace} />
        </Collapsible>
      )}

      {t.sql_executions.length > 0 && (
        <Collapsible icon={<Icons.db />} title="SQL branch" right={<Pill tone="sky">{t.sql_executions.length} query</Pill>}>
          <div className="space-y-3">{t.sql_executions.map((s, i) => <SqlBlock key={i} s={s} />)}</div>
        </Collapsible>
      )}

      {t.document_retrieval && (
        <Collapsible icon={<Icons.search />} title="Document retrieval — dense + BM25 → RRF → rerank"
          right={<Pill tone="emerald">{t.document_retrieval.candidates.length} candidates</Pill>}>
          {t.document_retrieval.strategy && (
            <p className="mb-2.5 text-[12.5px] leading-relaxed text-body">
              {t.document_retrieval.strategy}
            </p>
          )}
          <div className="mb-2.5 flex flex-wrap gap-2 text-[11px]">
            {t.document_retrieval.intent && (
              <Pill tone={t.document_retrieval.intent === "keyword" ? "amber" : "slate"}>
                intent: {t.document_retrieval.intent}
              </Pill>
            )}
            {t.document_retrieval.intent === "keyword" && !!t.document_retrieval.search_terms?.length && (
              <Pill tone="amber">terms: {t.document_retrieval.search_terms.join(", ")}</Pill>
            )}
            {!!t.document_retrieval.exact_hits && (
              <Pill tone="amber">{t.document_retrieval.exact_hits} exact match(es)</Pill>
            )}
            <Pill>embed: {t.document_retrieval.embedding_backend}</Pill>
            <Pill>rerank: {t.document_retrieval.reranker_backend}</Pill>
            {Object.entries(t.document_retrieval.params).map(([k, v]) => <Pill key={k}>{k}: {String(v)}</Pill>)}
            {!!(t.document_retrieval.filters as any)?.documents && (
              <Pill tone="indigo"><Icons.bolt className="h-3 w-3" />filtered → {(t.document_retrieval.filters as any).documents.length} doc(s)</Pill>)}
          </div>
          <CandidatesTable rows={t.document_retrieval.candidates} />
        </Collapsible>
      )}

      {t.evidence.length > 0 && (
        <Collapsible icon={<Icons.layers />} title="Evidence (single source of truth)" right={<Pill>{t.evidence.length} items</Pill>}>
          <p className="mb-2.5 text-[11.5px] text-faint">
            Everything retrieved for this answer. Items marked <span className="font-medium text-emerald-600 dark:text-emerald-400">used in answer</span> are
            what the response is actually grounded in.
          </p>
          <div className="space-y-2">{t.evidence.map((e) => <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} showUsed />)}</div>
        </Collapsible>
      )}

      <Card className="p-4">
        <div className="grid gap-5 sm:grid-cols-3">
          <div>
            <SectionTitle>Cost &amp; tokens</SectionTitle>
            {t.cost && (
              <div className="space-y-1 text-[12px]">
                <div className="flex items-center gap-1.5 font-mono text-fg"><Icons.coin className="h-3.5 w-3.5 text-amber-500" />${t.cost.total_usd.toFixed(4)}</div>
                <div className="text-muted">{t.cost.input_tokens} in / {t.cost.output_tokens} out · {t.cost.live_calls} live</div>
                <div className="text-[11px] text-faint">{t.cost.note}</div>
              </div>
            )}
          </div>
          <div>
            <SectionTitle>Timings</SectionTitle>
            <div className="space-y-1 text-[12px]">
              {t.timings.map((ti) => (
                <div key={ti.name} className="flex justify-between font-mono text-muted">
                  <span>{ti.name}</span><span>{ti.duration_ms} ms</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <SectionTitle>Citation check</SectionTitle>
            {t.citation_check && (
              <div className="text-[12px]">
                <Pill tone={t.citation_check.verified ? "emerald" : "rose"}>
                  {t.citation_check.verified ? <><Icons.check className="h-3 w-3" />verified</> : "failed"}
                </Pill>
                <p className="mt-1.5 text-[11px] text-muted">{t.citation_check.note}</p>
              </div>
            )}
          </div>
        </div>
        {t.llm_calls.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
            {t.llm_calls.map((c, i) => (
              <Pill key={i} tone={c.mode === "live" ? "emerald" : "slate"}>{c.purpose}: {c.model} ({c.mode})</Pill>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---------- deep research (Phase 4): the iterative-search timeline ---------- */

const STOP_LABELS: Record<string, string> = {
  sufficient: "evidence sufficient",
  max_rounds: "round limit reached",
  time_budget: "time budget reached",
  no_progress: "no new evidence found",
  evidence_cap: "evidence cap reached",
  exhausted: "no further queries to try",
  off_topic: "retrieved passages were off-topic — declined",
};

function ResearchRoundBlock({ r }: { r: ResearchRound }) {
  const v = r.verdict;
  return (
    <div className="rounded-xl border border-line bg-surface-2/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill tone="indigo">round {r.round}</Pill>
        {v && (
          <Pill tone={v.sufficient ? "emerald" : "amber"}>
            {v.sufficient ? <><Icons.check className="h-3 w-3" />sufficient</> : "needs more"}
          </Pill>
        )}
        {v && <Pill>coverage {Math.round(v.coverage * 100)}%</Pill>}
        {v && <Pill>{v.source === "llm" ? "LLM-checked" : "heuristic check"}</Pill>}
      </div>
      <div className="space-y-1.5">
        {r.actions.map((a, i) => (
          <div key={i} className="flex items-start gap-2 text-[12px] text-body">
            <span className="mt-0.5 font-mono text-[10.5px] text-accent">
              {a.tool === "sql_query" ? "sql" : "search"}
            </span>
            <span className="min-w-0">
              <span className="text-fg">“{a.query}”</span>
              {!!a.documents?.length && (
                <span className="text-muted"> in {a.documents.join(", ")}</span>
              )}
              <span className="text-muted"> → {a.found} found, {a.added} new</span>
              {a.reason && <span className="block text-[11px] text-faint">{a.reason}</span>}
            </span>
          </div>
        ))}
      </div>
      {v && (
        <p className="mt-2 text-[11.5px] leading-relaxed text-muted">{v.reasoning}</p>
      )}
    </div>
  );
}

function ResearchPanel({ rt }: { rt: ResearchTrace }) {
  return (
    <div className="space-y-3">
      <p className="text-[11.5px] text-faint">
        Retrieve → sufficiency check → reformulate, repeated until the evidence actually
        answers the question (bounded). Every round below is what the engine searched and
        why it kept going or stopped.
      </p>
      <div className="space-y-2">
        {rt.rounds.map((r) => <ResearchRoundBlock key={r.round} r={r} />)}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={rt.stop_reason === "sufficient" ? "emerald" : "amber"}>
          stopped: {STOP_LABELS[rt.stop_reason] ?? rt.stop_reason}
        </Pill>
        <Pill>{rt.evidence_count} evidence item(s)</Pill>
        <Pill>{rt.documents_covered.length} document(s) covered</Pill>
        <Pill><Icons.clock className="h-3 w-3" />{rt.duration_ms} ms</Pill>
      </div>
      {rt.documents_covered.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {rt.documents_covered.map((d) => (
            <span key={d} className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10.5px] text-muted ring-1 ring-inset ring-line">{d}</span>
          ))}
        </div>
      )}
    </div>
  );
}
