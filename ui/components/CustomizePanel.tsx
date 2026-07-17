"use client";
import React from "react";
import { Icons, cn } from "./ui";
import { AiSettingsState, OUTPUT_OPTIONS } from "./AiSettingsPanel";

/* ============================================================================
 * ChatGPT-style "Customize" popover — the replacement for the old 13-persona
 * picker. Two free-text fields (role + instructions) map to the backend's
 * existing `agent_role` / `custom_system_prompt`; the output format + a couple
 * of reasoning toggles round it out. No preset personas — the user describes the
 * assistant in their own words, exactly like ChatGPT's custom instructions.
 * ========================================================================== */

const MAX_PROMPT_CHARS = 500;

export default function CustomizePanel({
  settings, onUpdate, onClose, anchor = "bottom",
}: {
  settings: AiSettingsState;
  onUpdate: (patch: Partial<AiSettingsState>) => void;
  onClose: () => void;
  anchor?: "bottom" | "top";
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    // defer so the opening click doesn't immediately close it
    const t = setTimeout(() => window.addEventListener("mousedown", onClick), 0);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
      clearTimeout(t);
    };
  }, [onClose]);

  const hasCustom =
    settings.agentRole || settings.customSystemPrompt || settings.output !== "auto"
    || settings.multiAgent || settings.agentMode || settings.deepResearch;

  return (
    <div
      ref={ref}
      className={cn(
        "animate-scale-in absolute z-40 w-[340px] rounded-2xl border border-line bg-overlay p-4 shadow-pop",
        anchor === "bottom" ? "bottom-full mb-2" : "top-full mt-2",
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2 text-[13px] font-semibold text-fg">
          <Icons.spark className="h-4 w-4 text-accent" /> Customize responses
        </span>
        <button onClick={onClose}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-faint transition hover:bg-surface-2 hover:text-fg">
          <Icons.x className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="space-y-3.5">
        {/* Role */}
        <div>
          <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted">
            Respond as
          </label>
          <input
            type="text" value={settings.agentRole}
            onChange={(e) => onUpdate({ agentRole: e.target.value })}
            placeholder="e.g. a senior financial analyst"
            className="focus-ring w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-fg placeholder:text-faint"
          />
        </div>

        {/* Instructions */}
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              Custom instructions
            </label>
            <span className={cn("text-[10.5px]",
              MAX_PROMPT_CHARS - settings.customSystemPrompt.length < 50 ? "text-amber-600 dark:text-amber-400" : "text-faint")}>
              {MAX_PROMPT_CHARS - settings.customSystemPrompt.length} left
            </span>
          </div>
          <textarea
            value={settings.customSystemPrompt}
            onChange={(e) => { if (e.target.value.length <= MAX_PROMPT_CHARS) onUpdate({ customSystemPrompt: e.target.value }); }}
            rows={3}
            placeholder="How should the assistant respond? e.g. 'Be concise and focus on financial risk.'"
            className="focus-ring w-full resize-y rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-fg placeholder:text-faint"
          />
        </div>

        {/* Output format */}
        <div>
          <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted">
            Output format
          </label>
          <select
            value={settings.output}
            onChange={(e) => onUpdate({ output: e.target.value })}
            className="focus-ring w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] font-medium text-fg"
          >
            {OUTPUT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        {/* Reasoning toggles */}
        <div className="grid grid-cols-2 gap-2">
          <Toggle label="Deep research" hint="Iterate until enough" checked={settings.deepResearch}
            onChange={(v) => onUpdate({ deepResearch: v })} />
          <Toggle label="Agent mode" hint="Iterative tools" checked={settings.agentMode}
            onChange={(v) => onUpdate({ agentMode: v })} />
          <Toggle label="Multi-agent" hint="Decompose" checked={settings.multiAgent}
            onChange={(v) => onUpdate({ multiAgent: v })} />
        </div>

        {hasCustom && (
          <button
            onClick={() => onUpdate({ agentRole: "", customSystemPrompt: "", output: "auto", multiAgent: false, agentMode: false, deepResearch: false })}
            className="text-[11px] font-medium text-faint transition hover:text-rose-500"
          >
            Reset customizations
          </button>
        )}
      </div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: {
  label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={cn("flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-2 ring-1 ring-inset transition",
      checked ? "bg-accent-soft ring-accent/30" : "bg-surface-2 ring-line")}>
      <span className="text-[11.5px] font-medium text-fg">
        {label}
        {hint && <span className="block text-[10px] font-normal text-faint">{hint}</span>}
      </span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 accent-indigo-600" />
    </label>
  );
}
