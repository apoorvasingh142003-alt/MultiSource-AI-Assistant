"use client";
import React from "react";
import type { AnswerState, AskResponse } from "@/lib/types";
import { Icons, cn } from "./ui";

/* ============================================================================
 * The compact tri-state chip shown inline on every assistant message in the
 * clean chat. Same wall, smaller footprint: the full AnswerStateBanner lives in
 * the inspector's Answer tab. The three states NEVER share a look — a cited fact
 * and a model guess must be visually distinct at a glance.
 *   grounded     → emerald, shield
 *   reasoned     → amber,  spark    (model knowledge, not your sources)
 *   insufficient → slate,  question (honest decline)
 * ========================================================================== */

const CHIP: Record<AnswerState, {
  cls: string; Icon: (p: { className?: string }) => JSX.Element; label: string;
}> = {
  grounded: {
    cls: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30",
    Icon: Icons.shield,
    label: "Grounded & cited",
  },
  reasoned: {
    cls: "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-500/30",
    Icon: Icons.spark,
    label: "Reasoned advice — not from your sources",
  },
  insufficient: {
    cls: "bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10",
    Icon: Icons.question,
    label: "Insufficient evidence",
  },
};

export default function AnswerStateChip({ resp }: { resp: AskResponse }) {
  const state: AnswerState =
    resp.answer_state ?? (resp.insufficient ? "insufficient" : "grounded");
  const c = CHIP[state];
  return (
    <span
      title={c.label}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset",
        c.cls,
      )}
    >
      <c.Icon className="h-3.5 w-3.5" />
      {c.label}
    </span>
  );
}
