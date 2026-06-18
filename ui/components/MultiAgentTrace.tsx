"use client";
import React from "react";
import type { MultiAgentTrace as MultiAgentTraceType } from "@/lib/types";
import { Card, Icons, Pill, RouteBadge, SectionTitle, cn } from "./ui";

export default function MultiAgentTrace({
  trace,
}: {
  trace: MultiAgentTraceType;
}) {
  const [expanded, setExpanded] = React.useState<number | null>(null);

  return (
    <Card className="p-4 space-y-4 fade-up">
      <SectionTitle>Multi-Agent Reasoning</SectionTitle>

      {/* Root question */}
      <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-3">
        <div className="flex items-center gap-2 mb-1">
          <Icons.spark className="h-4 w-4 text-indigo-500" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">
            Original Question
          </span>
        </div>
        <p className="text-[13px] text-slate-700">{trace.original_question}</p>
      </div>

      {/* Sub-questions tree */}
      <div className="space-y-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Decomposed into {trace.sub_questions.length} Sub-Questions
        </h4>
        {trace.sub_answers.map((sa, i) => (
          <div
            key={i}
            className={cn(
              "rounded-xl border p-3 transition",
              expanded === i
                ? "border-indigo-200 bg-white shadow-sm"
                : "border-slate-200 bg-slate-50/50"
            )}
          >
            <button
              onClick={() => setExpanded(expanded === i ? null : i)}
              className="flex w-full items-center justify-between text-left"
            >
              <span className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-100 text-[11px] font-bold text-indigo-600">
                  {i + 1}
                </span>
                <span className="text-[12.5px] font-medium text-slate-700">
                  {sa.sub_question}
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <RouteBadge route={sa.route} small />
                <Icons.chevron
                  className={cn(
                    "h-3 w-3 text-slate-400 transition-transform",
                    expanded === i && "rotate-90"
                  )}
                />
              </span>
            </button>

            {expanded === i && (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <p className="text-[12.5px] leading-relaxed text-slate-600">
                  {sa.answer}
                </p>
                {sa.evidence_ids.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {sa.evidence_ids.map((id) => (
                      <span
                        key={id}
                        className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Synthesis */}
      {trace.synthesis_reasoning && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
          <div className="flex items-center gap-2 mb-1">
            <Icons.layers className="h-4 w-4 text-emerald-500" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-600">
              Synthesis Reasoning
            </span>
          </div>
          <p className="text-[12.5px] leading-relaxed text-slate-700">
            {trace.synthesis_reasoning}
          </p>
        </div>
      )}
    </Card>
  );
}
