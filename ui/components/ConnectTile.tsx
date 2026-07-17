"use client";
import React from "react";
import { BRAND } from "@/components/BrandIcons";
import { Icons, cn } from "@/components/ui";

// Accordion-style connected-app row used inside the AccountMenu. Shows the official brand mark,
// a live connection status, and expands its own connect/manage UI inline when opened.
export default function ConnectTile({
  brand, connected, open, onToggle, children,
}: {
  brand: keyof typeof BRAND;
  connected: boolean | null;   // null → status still loading
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;    // the expanded body
}) {
  const b = BRAND[brand];
  const Mark = b.Mark;
  return (
    <div className={cn("overflow-hidden rounded-xl border transition", open ? "border-accent/40 bg-surface-2" : "border-line")}>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-surface-2"
      >
        <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg ring-1 ring-inset", b.glow, b.ring)}>
          <Mark className="h-[18px] w-[18px]" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-semibold text-fg">{b.label}</span>
          <span className={cn("flex items-center gap-1.5 text-[11px]",
            connected ? "text-emerald-600 dark:text-emerald-400" : "text-muted")}>
            <span className={cn("h-1.5 w-1.5 rounded-full",
              connected == null ? "bg-faint" : connected ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600")} />
            {connected == null ? "Checking…" : connected ? "Connected" : "Not connected"}
          </span>
        </span>
        <Icons.chevronDown className={cn("h-4 w-4 text-faint transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t border-line px-3 py-3">{children}</div>}
    </div>
  );
}

/* small shared control styles for the expanded bodies */
export const connectInput =
  "focus-ring w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-fg placeholder:text-faint";
export function ConnectButton({
  children, onClick, disabled, tone = "accent",
}: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; tone?: "accent" | "emerald" | "sky" | "green" | "orange" }) {
  const tones: Record<string, string> = {
    accent: "bg-indigo-600 hover:bg-indigo-500",
    emerald: "bg-emerald-600 hover:bg-emerald-500",
    sky: "bg-sky-600 hover:bg-sky-500",
    green: "bg-green-600 hover:bg-green-500",
    orange: "bg-orange-500 hover:bg-orange-400",
  };
  return (
    <button onClick={onClick} disabled={disabled}
      className={cn("w-full rounded-lg px-3 py-2 text-sm font-semibold text-white transition active:scale-[0.99] disabled:opacity-50", tones[tone])}>
      {children}
    </button>
  );
}
