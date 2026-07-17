"use client";
import React from "react";

/* ============================================================================
 * Single source of truth for all AI/answer settings (persisted to localStorage).
 * Replaces the old split between "Output Mode" and "Output Format" with ONE merged
 * Output control; adds temperature + agent mode. Every feature reads from here.
 *
 * Phase 2: the 13-persona picker is gone — `agentRole` + `customSystemPrompt` are now
 * free text ("respond as …" / "how should it respond?"), edited from the composer's
 * Customize popover (CustomizePanel) exactly like ChatGPT's custom instructions.
 * ========================================================================== */

/** Merged Output control — each option resolves to the backend (output_mode, output_format)
 * pair. Overlapping concepts (e.g. Executive Summary, Table) are collapsed to one entry. */
export const OUTPUT_OPTIONS = [
  { value: "auto", label: "Auto", desc: "Let the AI choose the best format", mode: "Standard Response", format: "auto" },
  { value: "prose", label: "Prose", desc: "Flowing, readable paragraphs", mode: "Standard Response", format: "prose" },
  { value: "executive_summary", label: "Executive Summary", desc: "Leadership-ready summary + key points + actions", mode: "Executive Summary", format: "executive_summary" },
  { value: "detailed_report", label: "Detailed Report", desc: "Structured, in-depth analysis with evidence", mode: "Detailed Report", format: "auto" },
  { value: "bullet_points", label: "Bullet Points", desc: "Concise bulleted claims, each cited", mode: "Standard Response", format: "bullet_points" },
  { value: "table", label: "Table", desc: "Structured comparison table", mode: "Comparison Table", format: "table" },
  { value: "timeline", label: "Timeline", desc: "Chronological timeline table", mode: "Timeline", format: "timeline_table" },
  { value: "risk_assessment", label: "Risk Assessment", desc: "Risks, likelihood, impact, and actions", mode: "Risk Assessment", format: "auto" },
  { value: "action_plan", label: "Action Plan", desc: "Prioritized, actionable next steps", mode: "Action Plan", format: "auto" },
  { value: "swot", label: "SWOT Analysis", desc: "Strengths, weaknesses, opportunities, threats", mode: "SWOT Analysis", format: "auto" },
  { value: "json", label: "JSON", desc: "Machine-readable JSON object", mode: "Standard Response", format: "json" },
] as const;

export function resolveOutput(value: string): { output_mode: string; output_format: string } {
  const o = OUTPUT_OPTIONS.find((x) => x.value === value) ?? OUTPUT_OPTIONS[0];
  return { output_mode: o.mode, output_format: o.format };
}

export interface AiSettingsState {
  agentRole: string;
  customSystemPrompt: string;
  output: string;       // merged output key (see OUTPUT_OPTIONS)
  multiAgent: boolean;
  agentMode: boolean;   // LangGraph iterative agent
  temperature: number;  // 0..1, applied to final generation
}

const STORAGE_KEY = "nexus-settings";
export const DEFAULT_SETTINGS: AiSettingsState = {
  agentRole: "", customSystemPrompt: "", output: "auto",
  multiAgent: false, agentMode: false, temperature: 0,
};

function loadSettings(): AiSettingsState {
  if (typeof window === "undefined") return { ...DEFAULT_SETTINGS };
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
    // migrate the old key (ai-settings) if present
    const legacy = localStorage.getItem("ai-settings");
    if (legacy) {
      const l = JSON.parse(legacy);
      return { ...DEFAULT_SETTINGS, agentRole: l.agentRole || "", customSystemPrompt: l.customSystemPrompt || "", multiAgent: !!l.multiAgent };
    }
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_SETTINGS };
}

function saveSettings(s: AiSettingsState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export function useAiSettings() {
  const [settings, setSettings] = React.useState<AiSettingsState>(DEFAULT_SETTINGS);
  // hydrate from localStorage after mount (avoids SSR mismatch)
  React.useEffect(() => { setSettings(loadSettings()); }, []);

  const update = React.useCallback((patch: Partial<AiSettingsState>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveSettings(next);
      return next;
    });
  }, []);

  const reset = React.useCallback(() => {
    saveSettings(DEFAULT_SETTINGS);
    setSettings({ ...DEFAULT_SETTINGS });
  }, []);

  return { settings, update, reset };
}

// The old inline "AI Settings" panel (with the 13-persona dropdown) was removed in
// Phase 2. Role + instructions now live in CustomizePanel (composer popover) and the
// dedicated SettingsPanel; both read/write this same settings store.
