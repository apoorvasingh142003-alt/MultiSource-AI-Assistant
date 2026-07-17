"use client";
import React from "react";
import type { AnswerState, AskResponse } from "@/lib/types";
import { Icons, cn } from "./ui";

/* ============================================================================
 * The tri-state grounding wall — THE product moat, made visible.
 *
 * Every answer is exactly one of three states, and the three NEVER share the same
 * visual weight (a cited fact and a model guess must never look alike). This banner
 * is driven ONLY by resp.answer_state (computed once on the backend), so the label
 * can never disagree with itself the way the old scattered inference did.
 *
 *   grounded     → emerald, shield   — trust it, it's cited.
 *   reasoned     → amber,  lightbulb — model knowledge / advice, NOT your sources.
 *   insufficient → slate,  question  — the honest decline.
 * ========================================================================== */

type StateStyle = {
  ring: string;
  bg: string;
  text: string;
  iconWrap: string;
  Icon: (p: { className?: string }) => JSX.Element;
  title: string;
  sub: string;
};

const STATES: Record<AnswerState, StateStyle> = {
  grounded: {
    ring: "ring-emerald-200 dark:ring-emerald-500/30",
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
    text: "text-emerald-800 dark:text-emerald-200",
    iconWrap: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300",
    Icon: Icons.shield,
    title: "Grounded in your sources",
    sub: "Every claim is cited and verified against retrieved evidence.",
  },
  reasoned: {
    ring: "ring-amber-200 dark:ring-amber-500/30",
    bg: "bg-amber-50 dark:bg-amber-500/10",
    text: "text-amber-900 dark:text-amber-200",
    iconWrap: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
    Icon: Icons.spark,
    title: "Reasoned advice — not from your sources",
    sub: "Model knowledge, not grounded in your documents or database. Verify before relying on it.",
  },
  insufficient: {
    ring: "ring-slate-200 dark:ring-white/10",
    bg: "bg-slate-50 dark:bg-white/5",
    text: "text-slate-700 dark:text-slate-200",
    iconWrap: "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300",
    Icon: Icons.question,
    title: "Insufficient evidence — not answered",
    sub: "No source could ground an answer. The assistant declines rather than guessing.",
  },
};

export default function AnswerStateBanner({
  resp,
  riskPct,
}: {
  resp: AskResponse;
  riskPct?: number | null;
}) {
  // Fall back to deriving from insufficient if the backend field is absent (older payloads).
  const state: AnswerState =
    resp.answer_state ?? (resp.insufficient ? "insufficient" : "grounded");
  const s = STATES[state];
  const showRisk = state === "reasoned" && riskPct != null && riskPct >= 40;

  return (
    <div
      role="status"
      aria-label={`Answer state: ${s.title}`}
      className={cn(
        "flex items-start gap-3 rounded-2xl px-4 py-3 ring-1 ring-inset",
        s.bg, s.ring,
      )}
    >
      <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full", s.iconWrap)}>
        <s.Icon className="h-4 w-4" />
      </span>
      <div className={cn("min-w-0 flex-1 leading-snug", s.text)}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13.5px] font-semibold">{s.title}</span>
          {showRisk && (
            <span className="inline-flex items-center rounded-md bg-amber-100 px-1.5 py-0.5 text-[10.5px] font-bold text-amber-800 ring-1 ring-inset ring-amber-300 dark:bg-amber-500/20 dark:text-amber-100 dark:ring-amber-400/30">
              hallucination risk {riskPct!.toFixed(0)}%
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[11.5px] opacity-80">{s.sub}</p>
      </div>
    </div>
  );
}
