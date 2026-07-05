"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import { Icons, Pill, cn } from "./ui";

export default function VerificationBadge({
  resp,
  onClick,
}: {
  resp: AskResponse;
  onClick?: () => void;
}) {
  const t = resp.trace;
  const verified = t.citation_check?.verified;
  const hasContradictions =
    resp.contradictions?.some((c) => c.contradiction) ?? false;
  const riskScore = resp.hallucination_risk_score;

  // General knowledge route — ungrounded; warn rather than reassure.
  if (t.route?.route === "GENERAL_KNOWLEDGE") {
    const pill = (
      <Pill tone="amber" className={cn(onClick && "cursor-pointer transition hover:ring-amber-300")}>
        <Icons.alert className="h-3 w-3" />
        ungrounded — model knowledge
        {riskScore != null && riskScore >= 0.4 && (
          <span className="ml-1 opacity-70">(risk: {(riskScore * 100).toFixed(0)}%)</span>
        )}
      </Pill>
    );
    return onClick ? (
      <button onClick={onClick} className="inline-flex">{pill}</button>
    ) : pill;
  }

  if (hasContradictions) {
    return (
      <button onClick={onClick} className="inline-flex">
        <Pill tone="amber" className="cursor-pointer transition hover:ring-amber-300">
          <Icons.alert className="h-3 w-3" />
          contradictions detected
          {riskScore != null && (
            <span className="ml-1 opacity-70">
              (risk: {(riskScore * 100).toFixed(0)}%)
            </span>
          )}
        </Pill>
      </button>
    );
  }

  if (verified) {
    return (
      <button onClick={onClick} className="inline-flex">
        <Pill tone="emerald" className="cursor-pointer transition hover:ring-emerald-300">
          <Icons.shield className="h-3 w-3" />
          citations verified
        </Pill>
      </button>
    );
  }

  if (t.evidence.length > 0) {
    return (
      <button onClick={onClick} className="inline-flex">
        <Pill tone="amber" className="cursor-pointer transition hover:ring-amber-300">
          citations unverified
        </Pill>
      </button>
    );
  }

  return null;
}
