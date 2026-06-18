"use client";
import React from "react";
import { Card, Icons, SectionTitle, cn } from "./ui";

const PRESET_ROLES = [
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

const OUTPUT_FORMATS = [
  { label: "Auto", value: "auto" },
  { label: "Prose", value: "prose" },
  { label: "Structured Table", value: "table" },
  { label: "Timeline Table", value: "timeline_table" },
  { label: "JSON", value: "json" },
  { label: "Bullet Points", value: "bullet_points" },
  { label: "Executive Summary", value: "executive_summary" },
];

const MAX_PROMPT_CHARS = 500;

interface AiSettingsState {
  agentRole: string;
  customSystemPrompt: string;
  outputFormat: string;
}

const STORAGE_KEY = "ai-settings";

function loadSettings(): AiSettingsState {
  if (typeof window === "undefined") {
    return { agentRole: "", customSystemPrompt: "", outputFormat: "auto" };
  }
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved);
  } catch {
    /* ignore */
  }
  return { agentRole: "", customSystemPrompt: "", outputFormat: "auto" };
}

function saveSettings(s: AiSettingsState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export function useAiSettings() {
  const [settings, setSettings] = React.useState<AiSettingsState>(loadSettings);

  const update = React.useCallback(
    (patch: Partial<AiSettingsState>) => {
      setSettings((prev) => {
        const next = { ...prev, ...patch };
        saveSettings(next);
        return next;
      });
    },
    []
  );

  return { settings, update };
}

export default function AiSettingsPanel({
  settings,
  onUpdate,
}: {
  settings: AiSettingsState;
  onUpdate: (patch: Partial<AiSettingsState>) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const hasCustom =
    settings.agentRole || settings.customSystemPrompt || settings.outputFormat !== "auto";

  return (
    <Card>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-t-[14px] px-4 py-3 text-left transition hover:bg-slate-50"
      >
        <span className="flex items-center gap-2.5 text-sm font-semibold text-slate-800">
          <Icons.chevron
            className={cn(
              "h-3.5 w-3.5 text-slate-400 transition-transform",
              open && "rotate-90"
            )}
          />
          <Icons.spark className="h-4 w-4 text-indigo-500" />
          AI Settings
        </span>
        <span className="flex items-center gap-2">
          {hasCustom && (
            <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
          )}
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-3.5">
          {/* Agent Role */}
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Agent Role
            </label>
            <div className="flex gap-2">
              <select
                value={settings.agentRole}
                onChange={(e) => onUpdate({ agentRole: e.target.value })}
                className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 transition hover:border-indigo-300"
              >
                {PRESET_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={settings.agentRole}
                onChange={(e) => onUpdate({ agentRole: e.target.value })}
                placeholder="Or type a custom role…"
                className="focus-ring flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400 transition hover:border-indigo-300"
              />
            </div>
          </div>

          {/* Custom System Prompt */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Custom System Prompt
              </label>
              <span
                className={cn(
                  "text-[10.5px]",
                  MAX_PROMPT_CHARS - settings.customSystemPrompt.length < 50
                    ? "text-amber-600"
                    : "text-slate-400"
                )}
              >
                {MAX_PROMPT_CHARS - settings.customSystemPrompt.length} chars remaining
              </span>
            </div>
            <textarea
              value={settings.customSystemPrompt}
              onChange={(e) => {
                const v = e.target.value;
                if (v.length <= MAX_PROMPT_CHARS) {
                  onUpdate({ customSystemPrompt: v });
                }
              }}
              rows={3}
              placeholder="Add custom instructions for the AI (e.g., 'Focus on financial implications', 'Use formal language', 'Include risk assessment')…"
              className="focus-ring w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400 transition hover:border-indigo-300"
            />
          </div>

          {/* Output Format */}
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Output Format
            </label>
            <div className="flex flex-wrap gap-1.5">
              {OUTPUT_FORMATS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => onUpdate({ outputFormat: f.value })}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-[12px] font-medium transition",
                    settings.outputFormat === f.value
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Reset */}
          {hasCustom && (
            <button
              onClick={() =>
                onUpdate({
                  agentRole: "",
                  customSystemPrompt: "",
                  outputFormat: "auto",
                })
              }
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
