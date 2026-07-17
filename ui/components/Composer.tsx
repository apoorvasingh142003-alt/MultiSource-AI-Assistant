"use client";
import React from "react";
import { Button, Icons, cn } from "./ui";
import { AiSettingsState } from "./AiSettingsPanel";
import CustomizePanel from "./CustomizePanel";

/* ============================================================================
 * The ChatGPT-style composer: a rounded input with an attach (📎) affordance for
 * in-chat PDF upload, a "Customize" popover (role + instructions — the persona-
 * picker replacement), and send. Streaming/busy state disables send and shows a
 * spinner. Enter sends, Shift+Enter newlines.
 * ========================================================================== */
export default function Composer({
  value, onChange, onSend, onAttach, busy, warming, pdfBusy,
  settings, onUpdateSettings,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onAttach: (files: File[]) => void;
  busy: boolean;
  warming: boolean;
  pdfBusy: boolean;
  settings: AiSettingsState;
  onUpdateSettings: (patch: Partial<AiSettingsState>) => void;
}) {
  const [customizeOpen, setCustomizeOpen] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const hasCustom =
    !!settings.agentRole || !!settings.customSystemPrompt || settings.output !== "auto"
    || settings.multiAgent || settings.agentMode;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
  };

  const pick = (list: FileList | null) => {
    if (list && list.length) onAttach(Array.from(list));
  };

  return (
    <div className="relative mx-auto w-full max-w-3xl">
      <div className="surface flex items-end gap-2 rounded-3xl p-2 shadow-lg ring-1 ring-line/60 transition focus-within:ring-accent/40">
        {/* attach */}
        <div className="flex items-center gap-1 pb-0.5 pl-1">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={pdfBusy}
            title="Attach a PDF"
            className={cn(
              "inline-flex h-9 w-9 items-center justify-center rounded-full text-muted transition hover:bg-surface-2 hover:text-fg disabled:opacity-50",
              pdfBusy && "cursor-wait",
            )}
          >
            {pdfBusy
              ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
              : <Icons.upload className="h-[18px] w-[18px]" />}
          </button>
          <input ref={fileRef} type="file" accept=".pdf" multiple className="hidden"
            onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />

          {/* customize */}
          <div className="relative">
            <button
              onClick={() => setCustomizeOpen((o) => !o)}
              title="Customize responses"
              className={cn(
                "inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-[12.5px] font-medium transition",
                hasCustom || customizeOpen
                  ? "bg-accent-soft text-accent ring-1 ring-inset ring-accent/25"
                  : "text-muted hover:bg-surface-2 hover:text-fg",
              )}
            >
              <Icons.spark className="h-4 w-4" />
              <span className="hidden sm:inline">Customize</span>
              {hasCustom && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
            </button>
            {customizeOpen && (
              <CustomizePanel
                settings={settings}
                onUpdate={onUpdateSettings}
                onClose={() => setCustomizeOpen(false)}
                anchor="bottom"
              />
            )}
          </div>
        </div>

        {/* text */}
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKey}
          rows={1}
          placeholder="Message Nexus AI…"
          className="scroll-thin max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-relaxed text-fg outline-none placeholder:text-faint"
        />

        {/* send */}
        <Button
          size="md"
          onClick={onSend}
          disabled={busy || warming || !value.trim()}
          className="mb-0.5 h-10 w-10 rounded-full px-0"
          title={warming ? "Warming up…" : "Send"}
        >
          {busy || warming
            ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/50 border-t-white" />
            : <Icons.send className="h-[18px] w-[18px]" />}
        </Button>
      </div>

      {/* active-customization hint */}
      <div className="mt-1.5 flex items-center justify-center gap-2 px-2 text-[11px] text-faint">
        {settings.agentMode && <span className="rounded bg-accent-soft px-1.5 py-0.5 font-medium text-accent ring-1 ring-inset ring-accent/25">Agent mode</span>}
        {settings.multiAgent && <span className="rounded bg-accent-soft px-1.5 py-0.5 font-medium text-accent ring-1 ring-inset ring-accent/25">Multi-agent</span>}
        {settings.agentRole && <span className="max-w-[220px] truncate rounded bg-surface-2 px-1.5 py-0.5 font-medium text-muted ring-1 ring-inset ring-line">as {settings.agentRole}</span>}
        <span className="hidden sm:inline">
          Answers are grounded &amp; cited, or clearly labeled when they aren&apos;t.
        </span>
      </div>
    </div>
  );
}
