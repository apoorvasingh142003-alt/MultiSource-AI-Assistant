"use client";
import React from "react";
import { Card, Icons, cn } from "./ui";

/* ============================================================================
 * Single source of truth for all AI/answer settings (persisted to localStorage).
 * Replaces the old split between "Output Mode" and "Output Format" with ONE merged
 * Output control; adds temperature + agent mode. Every feature reads from here.
 * ========================================================================== */

export const PRESET_ROLES = [
  { label: "Auto (Best Fit)", value: "" },
  { label: "Business Analyst", value: "Business Analyst" },
  { label: "Software Engineer", value: "Software Engineer" },
  { label: "Data Analyst", value: "Data Analyst" },
  { label: "Doctor", value: "Medical Doctor" },
  { label: "Lawyer", value: "Legal Expert" },
  { label: "Financial Advisor", value: "Financial Advisor" },
  { label: "Teacher", value: "Teacher & Educator" },
  { label: "Consultant", value: "Strategic Consultant" },
];

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

const MAX_PROMPT_CHARS = 500;

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

/* ---------------- the inline panel (lives beside the chat) ---------------- */
export default function AiSettingsPanel({
  settings,
  onUpdate,
  defaultOpen = false,
}: {
  settings: AiSettingsState;
  onUpdate: (patch: Partial<AiSettingsState>) => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  const hasCustom =
    settings.agentRole || settings.customSystemPrompt || settings.output !== "auto"
    || settings.multiAgent || settings.agentMode || settings.temperature > 0;
  const currentOutput = OUTPUT_OPTIONS.find((o) => o.value === settings.output) ?? OUTPUT_OPTIONS[0];

  return (
    <Card>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-t-[14px] px-4 py-3 text-left transition hover:bg-slate-50"
      >
        <span className="flex items-center gap-2.5 text-sm font-semibold text-slate-800">
          <Icons.chevron className={cn("h-3.5 w-3.5 text-slate-400 transition-transform", open && "rotate-90")} />
          <Icons.spark className="h-4 w-4 text-indigo-500" />
          AI Settings
        </span>
        {hasCustom && <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />}
      </button>

      {open && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-3.5">
          {/* Agent Role */}
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Response Role
            </label>
            <div className="flex gap-2">
              <select
                value={PRESET_ROLES.some((r) => r.value === settings.agentRole) ? settings.agentRole : ""}
                onChange={(e) => onUpdate({ agentRole: e.target.value })}
                className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 transition hover:border-indigo-300"
              >
                {PRESET_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
              <input
                type="text" value={settings.agentRole}
                onChange={(e) => onUpdate({ agentRole: e.target.value })}
                placeholder="Or type a custom role…"
                className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400 transition hover:border-indigo-300"
              />
            </div>
          </div>

          {/* Merged Output control */}
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Output
            </label>
            <select
              value={settings.output}
              onChange={(e) => onUpdate({ output: e.target.value })}
              className="focus-ring w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] font-medium text-slate-700 transition hover:border-indigo-300"
            >
              {OUTPUT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{currentOutput.desc}</p>
          </div>

          {/* Custom System Prompt */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Custom Instructions
              </label>
              <span className={cn("text-[10.5px]",
                MAX_PROMPT_CHARS - settings.customSystemPrompt.length < 50 ? "text-amber-600" : "text-slate-400")}>
                {MAX_PROMPT_CHARS - settings.customSystemPrompt.length} left
              </span>
            </div>
            <textarea
              value={settings.customSystemPrompt}
              onChange={(e) => { if (e.target.value.length <= MAX_PROMPT_CHARS) onUpdate({ customSystemPrompt: e.target.value }); }}
              rows={3}
              placeholder="e.g. 'Focus on financial implications', 'Use formal language'…"
              className="focus-ring w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400 transition hover:border-indigo-300"
            />
          </div>

          {/* Agent mode (iterative LangGraph agent) */}
          <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
            <span className="text-[12px] font-medium text-slate-600">
              Agent mode
              <span className="block text-[10.5px] font-normal text-slate-400">
                Iterative reasoning — the AI uses tools step by step (SQL → docs → answer)
              </span>
            </span>
            <input type="checkbox" checked={settings.agentMode}
              onChange={(e) => onUpdate({ agentMode: e.target.checked })}
              className="h-4 w-4 accent-indigo-600" />
          </label>

          {/* Multi-agent reasoning */}
          <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
            <span className="text-[12px] font-medium text-slate-600">
              Multi-agent reasoning
              <span className="block text-[10.5px] font-normal text-slate-400">
                Decompose complex questions, answer in parallel, then synthesize
              </span>
            </span>
            <input type="checkbox" checked={settings.multiAgent}
              onChange={(e) => onUpdate({ multiAgent: e.target.checked })}
              className="h-4 w-4 accent-indigo-600" />
          </label>

          {hasCustom && (
            <button
              onClick={() => onUpdate({ ...DEFAULT_SETTINGS })}
              className="text-[11px] font-medium text-slate-400 transition hover:text-rose-500"
            >
              Reset to defaults
            </button>
          )}
        </div>
      )}
    </Card>
  );
}
