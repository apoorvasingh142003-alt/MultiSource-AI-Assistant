"use client";
import React from "react";
import type { ActionResult, ProposedAction } from "@/lib/types";
import { executeAction } from "@/lib/api";
import { Icons, cn } from "./ui";

/* ============================================================================
 * ActionCard (Phase 6) — the confirm-to-execute surface for an action proposal.
 *
 * Deliberately its OWN visual category (violet "external action" identity, never
 * the tri-state grounding palette): an action is a write to the client's other
 * tools, not an answer, so it must never read as a grounded/reasoned claim.
 * Params stay editable until the user confirms; nothing is dispatched before
 * that. A `suggested` proposal (escalate-when-unsure) renders the same card in
 * a compact framing under the honest decline it accompanies.
 * ========================================================================== */
export default function ActionCard({
  proposal, sessionId,
}: {
  proposal: ProposedAction;
  sessionId?: string | null;
}) {
  const [params, setParams] = React.useState<Record<string, string>>(proposal.params);
  const [sending, setSending] = React.useState(false);
  const [result, setResult] = React.useState<ActionResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dismissed, setDismissed] = React.useState(false);

  const missing = proposal.required.filter((p) => !(params[p] || "").trim());
  const suggested = proposal.origin === "suggested";

  const confirm = async () => {
    if (sending || missing.length > 0) return;
    setSending(true);
    setError(null);
    try {
      const clean = Object.fromEntries(
        Object.entries(params).filter(([, v]) => (v || "").trim()),
      );
      setResult(await executeAction(proposal.action, clean, sessionId));
    } catch {
      setError("Could not execute the action. Please try again.");
    }
    setSending(false);
  };

  if (dismissed) return null;

  return (
    <div className={cn(
      "rounded-2xl border p-3.5",
      result?.status === "executed"
        ? "border-violet-300 bg-violet-50/60 dark:border-violet-500/40 dark:bg-violet-500/10"
        : "border-violet-200 bg-surface dark:border-violet-500/30",
    )}>
      {/* header — the explicit external-write label */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300">
            <Icons.bolt className="h-4 w-4" />
          </span>
          <div>
            <div className="text-[13px] font-bold text-fg">{proposal.title}</div>
            <div className="text-[10.5px] font-medium uppercase tracking-wider text-violet-600 dark:text-violet-300">
              External action · sends to your n8n workflow
            </div>
          </div>
        </div>
        {!result && suggested && (
          <button onClick={() => setDismissed(true)} title="Dismiss"
            className="rounded-md p-1 text-faint transition hover:bg-surface-2 hover:text-fg">
            <Icons.x className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <p className="mt-2 text-[12.5px] leading-relaxed text-muted">{proposal.description}</p>

      {/* params — editable until confirmed */}
      {!result && (
        <div className="mt-2.5 grid gap-1.5 sm:grid-cols-2">
          {Object.keys(proposal.params).map((p) => (
            <label key={p} className="block">
              <span className="mb-0.5 block text-[10.5px] font-semibold uppercase tracking-wider text-faint">
                {p}{proposal.required.includes(p) && <span className="text-violet-500"> *</span>}
              </span>
              <input
                value={params[p] ?? ""}
                onChange={(e) => setParams((prev) => ({ ...prev, [p]: e.target.value }))}
                placeholder={proposal.required.includes(p) ? "required" : "optional"}
                className="focus-ring w-full rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-fg placeholder:text-faint"
              />
            </label>
          ))}
        </div>
      )}

      {/* result / controls */}
      {result ? (
        <div className={cn(
          "mt-2.5 flex items-start gap-2 rounded-xl px-3 py-2 text-[12.5px] ring-1 ring-inset",
          result.status === "executed"
            ? "bg-violet-100/70 text-violet-800 ring-violet-300 dark:bg-violet-500/15 dark:text-violet-200 dark:ring-violet-500/40"
            : result.status === "simulated"
              ? "bg-surface-2 text-muted ring-line"
              : "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/30",
        )}>
          {result.status === "error"
            ? <Icons.alert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            : <Icons.check className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span>
            <span className="font-semibold capitalize">{result.status}</span> — {result.detail}
          </span>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] text-faint">
            {proposal.configured
              ? "Webhook configured — confirming sends it for real."
              : "No webhook configured — confirming records a simulated run."}
            {missing.length > 0 && ` Fill in: ${missing.join(", ")}.`}
          </span>
          <button
            onClick={confirm} disabled={sending || missing.length > 0}
            className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-[12px] font-semibold text-white shadow-sm transition hover:bg-violet-700 disabled:opacity-50">
            {sending
              ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              : <Icons.send className="h-3.5 w-3.5" />}
            {sending ? "Sending…" : "Confirm & send"}
          </button>
        </div>
      )}

      {error && (
        <div className="mt-2 flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2 text-[12px] text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/30">
          <Icons.alert className="mt-0.5 h-3.5 w-3.5 shrink-0" />{error}
        </div>
      )}
    </div>
  );
}
