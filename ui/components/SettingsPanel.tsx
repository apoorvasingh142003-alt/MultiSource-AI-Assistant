"use client";
import React from "react";
import { Button, Icons, cn } from "./ui";
import { fetchModelMode, setModelMode } from "@/lib/api";
import type { ModelModeStatus } from "@/lib/types";
import {
  AiSettingsState, OUTPUT_OPTIONS,
} from "./AiSettingsPanel";

/* Dedicated Settings modal. Temperature is live here and is actually applied to
 * generation (sent as `temperature` on every ask). API-key + local-model management
 * are scaffolded but deferred. */
export default function SettingsPanel({
  settings, onUpdate, dark, onToggleDark, onClose,
}: {
  settings: AiSettingsState;
  onUpdate: (patch: Partial<AiSettingsState>) => void;
  dark: boolean;
  onToggleDark: () => void;
  onClose: () => void;
}) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tempLabel =
    settings.temperature === 0 ? "Precise (deterministic)"
    : settings.temperature <= 0.3 ? "Focused"
    : settings.temperature <= 0.7 ? "Balanced"
    : "Creative";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="surface relative z-10 max-h-[88vh] w-full max-w-2xl overflow-y-auto p-0">
        {/* header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface/90 px-5 py-3.5 backdrop-blur">
          <h2 className="flex items-center gap-2 text-[15px] font-bold text-fg">
            <Icons.spark className="h-4 w-4 text-indigo-500" /> Settings
          </h2>
          <button onClick={onClose} className="inline-flex h-7 w-7 items-center justify-center rounded-md text-faint transition hover:bg-surface-2 hover:text-fg">
            <Icons.x className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 px-5 py-5">
          {/* Generation */}
          <Section title="Generation" hint="how the model produces answers">
            {/* Temperature */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-[13px] font-semibold text-fg">Temperature</label>
                <span className="flex items-center gap-2 text-[12px] text-muted">
                  <span className="rounded-md bg-indigo-50 px-2 py-0.5 font-medium text-indigo-600 ring-1 ring-inset ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30">
                    {settings.temperature.toFixed(1)}
                  </span>
                  {tempLabel}
                </span>
              </div>
              <input
                type="range" min={0} max={1} step={0.1}
                value={settings.temperature}
                onChange={(e) => onUpdate({ temperature: parseFloat(e.target.value) })}
                className="w-full accent-indigo-600"
              />
              <div className="mt-1 flex justify-between text-[10.5px] text-faint">
                <span>0 · deterministic, grounded</span>
                <span>1 · creative, varied</span>
              </div>
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-faint">
                Applies to final answer generation. Routing and SQL stay deterministic for reliability.
              </p>
            </div>

            {/* Default role — free text, ChatGPT-style (replaces the old persona picker) */}
            <div>
              <label className="mb-1 block text-[13px] font-semibold text-fg">Default role</label>
              <input
                type="text"
                value={settings.agentRole}
                onChange={(e) => onUpdate({ agentRole: e.target.value })}
                placeholder="e.g. a senior financial analyst (leave blank for auto)"
                className="focus-ring w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-fg placeholder:text-faint"
              />
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-faint">
                Applied to every answer. You can also set this per-message from the composer&apos;s Customize button.
              </p>
            </div>

            {/* Default instructions — free text */}
            <div>
              <label className="mb-1 block text-[13px] font-semibold text-fg">Custom instructions</label>
              <textarea
                value={settings.customSystemPrompt}
                onChange={(e) => { if (e.target.value.length <= 500) onUpdate({ customSystemPrompt: e.target.value }); }}
                rows={2}
                placeholder="How should the assistant respond? e.g. 'Be concise; focus on financial risk.'"
                className="focus-ring w-full resize-y rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-fg placeholder:text-faint"
              />
            </div>

            {/* Default output */}
            <div>
              <label className="mb-1 block text-[13px] font-semibold text-fg">Default output format</label>
              <select
                value={settings.output}
                onChange={(e) => onUpdate({ output: e.target.value })}
                className="focus-ring w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-fg"
              >
                {OUTPUT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>

            {/* Reasoning toggles */}
            <div className="grid grid-cols-2 gap-2">
              <Toggle label="Deep research" hint="Iterate retrieval until sufficient" checked={settings.deepResearch}
                onChange={(v) => onUpdate({ deepResearch: v })} />
              <Toggle label="Agent mode" hint="Iterative tool use" checked={settings.agentMode}
                onChange={(v) => onUpdate({ agentMode: v })} />
              <Toggle label="Multi-agent" hint="Decompose + synthesize" checked={settings.multiAgent}
                onChange={(v) => onUpdate({ multiAgent: v })} />
            </div>
          </Section>

          {/* Appearance */}
          <Section title="Appearance">
            <Toggle label="Dark mode" hint="Switch the interface theme" checked={dark} onChange={onToggleDark} />
          </Section>

          {/* Model source — API vs local */}
          <Section title="Model source">
            <ModelModeToggle />
          </Section>

          <div className="flex justify-end">
            <Button size="md" onClick={onClose}>Done</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ModelModeToggle() {
  const [status, setStatus] = React.useState<ModelModeStatus | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => { fetchModelMode().then(setStatus).catch(() => {}); }, []);

  const choose = async (mode: "api" | "local") => {
    if (busy || status?.mode === mode) return;
    setBusy(true); setErr(null);
    try { setStatus(await setModelMode(mode)); }
    catch { setErr("Could not switch model source."); }
    finally { setBusy(false); }
  };

  const Opt = ({ mode, title, sub }: { mode: "api" | "local"; title: string; sub: string }) => {
    const active = status?.mode === mode;
    return (
      <button onClick={() => choose(mode)} disabled={busy}
        className={cn("flex-1 rounded-xl border px-3.5 py-3 text-left transition disabled:opacity-60",
          active ? "border-indigo-300 bg-indigo-50 ring-1 ring-inset ring-indigo-200 dark:bg-indigo-500/10 dark:border-indigo-500/50 dark:ring-indigo-500/30" : "border-line bg-surface-2 hover:border-indigo-200")}>
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-semibold text-fg">{title}</span>
          {active && <span className="h-2 w-2 rounded-full bg-indigo-500" />}
        </div>
        <p className="mt-0.5 text-[11px] leading-relaxed text-faint">{sub}</p>
      </button>
    );
  };

  return (
    <div>
      <div className="flex gap-2">
        <Opt mode="api" title="API" sub="Server-configured provider (cloud)" />
        <Opt mode="local" title="Local model" sub="Ollama / local server — no key needed" />
      </div>
      {status && (
        <p className="mt-2 text-[11px] text-faint">
          Active: <span className="font-medium text-body">{status.model}</span>
          {" · "}{status.provider}{status.live ? "" : " · offline"}
          {status.mode === "local" && <> · expects Ollama at <span className="font-mono">{status.base_url}</span></>}
        </p>
      )}
      {err && <p className="mt-1.5 text-[11px] text-rose-500 dark:text-rose-400">{err}</p>}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-2.5 flex items-baseline justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{title}</h3>
        {hint && <span className="text-[11px] text-faint">{hint}</span>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Toggle({ label, hint, checked, onChange }: {
  label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={cn("flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 ring-1 ring-inset transition",
      checked ? "bg-indigo-50 ring-indigo-200 dark:bg-indigo-500/10 dark:ring-indigo-500/30" : "bg-surface-2 ring-line")}>
      <span className="text-[12.5px] font-medium text-fg">
        {label}
        {hint && <span className="block text-[10.5px] font-normal text-faint">{hint}</span>}
      </span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-indigo-600" />
    </label>
  );
}
