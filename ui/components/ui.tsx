"use client";
import React from "react";
import type { Route } from "@/lib/types";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function isRTL(text: string | null | undefined): boolean {
  return !!text && /[֐-׿]/.test(text);
}

/* ---------------- icons (inline, stroke) ---------------- */
type IconProps = { className?: string };
const S = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
       strokeLinecap="round" strokeLinejoin="round"
       className={cn("h-4 w-4", className)}>{children}</svg>
);
export const Icons = {
  question: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M9.2 9a2.8 2.8 0 0 1 5.3 1c0 1.8-2.5 2-2.5 3.5" /><path d="M12 17.5h.01" /></S>,
  route: (p: IconProps) => <S {...p}><circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="18" r="2.2" /><path d="M8 6h6a3 3 0 0 1 3 3v6.5" /><path d="M6 8v4a3 3 0 0 0 3 3h3" /></S>,
  search: (p: IconProps) => <S {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-3.5-3.5" /></S>,
  layers: (p: IconProps) => <S {...p}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></S>,
  spark: (p: IconProps) => <S {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="M12 8.5 13.4 11 16 12l-2.6 1L12 15.5 10.6 13 8 12l2.6-1L12 8.5Z" /></S>,
  check: (p: IconProps) => <S {...p}><path d="M20 6 9 17l-5-5" /></S>,
  chevron: (p: IconProps) => <S {...p}><path d="m9 18 6-6-6-6" /></S>,
  chevronDown: (p: IconProps) => <S {...p}><path d="m6 9 6 6 6-6" /></S>,
  db: (p: IconProps) => <S {...p}><ellipse cx="12" cy="5.5" rx="7" ry="2.8" /><path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13" /><path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" /></S>,
  doc: (p: IconProps) => <S {...p}><path d="M14 3v4a1 1 0 0 0 1 1h4" /><path d="M19 8.5V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6l6 5.5Z" /><path d="M9 13h6M9 17h4" /></S>,
  clock: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7.5V12l3 2" /></S>,
  coin: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9.5 9.2a2.4 2.4 0 0 1 2.5-1.7c1.3 0 2.4.8 2.4 1.9 0 2.4-4.8 1.2-4.8 3.4 0 1.1 1.1 1.9 2.4 1.9a2.4 2.4 0 0 0 2.5-1.7" /></S>,
  shield: (p: IconProps) => <S {...p}><path d="M12 3 5 6v5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9V6l-7-3Z" /><path d="m9.2 12 2 2 3.6-3.8" /></S>,
  bolt: (p: IconProps) => <S {...p}><path d="M13 3 5 13h6l-1 8 8-10h-6l1-8Z" /></S>,
  arrowR: (p: IconProps) => <S {...p}><path d="M5 12h14M13 6l6 6-6 6" /></S>,
  send: (p: IconProps) => <S {...p}><path d="M4 12 20 4l-3.5 16-4.5-6-8-2Z" /><path d="m12 14 8-10" /></S>,
  upload: (p: IconProps) => <S {...p}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M5 16v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" /></S>,
  plus: (p: IconProps) => <S {...p}><path d="M12 5v14M5 12h14" /></S>,
  refresh: (p: IconProps) => <S {...p}><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></S>,
  table: (p: IconProps) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M3 14.5h18M9 4v16" /></S>,
  info: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></S>,
  alert: (p: IconProps) => <S {...p}><path d="M12 3 2.5 19.5h19L12 3Z" /><path d="M12 10v4M12 17h.01" /></S>,
  x: (p: IconProps) => <S {...p}><path d="M18 6 6 18M6 6l12 12" /></S>,
  inspect: (p: IconProps) => <S {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3-3" /><path d="M11 8v6M8 11h6" /></S>,
  grid: (p: IconProps) => <S {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></S>,
  play: (p: IconProps) => <S {...p}><path d="M7 5v14l11-7L7 5Z" /></S>,
  gear: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c0 .74.44 1.32 1.05 1.55H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" /></S>,
  sun: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></S>,
  moon: (p: IconProps) => <S {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" /></S>,
  logout: (p: IconProps) => <S {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></S>,
  external: (p: IconProps) => <S {...p}><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></S>,
  link: (p: IconProps) => <S {...p}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></S>,
  sidebar: (p: IconProps) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></S>,
  copy: (p: IconProps) => <S {...p}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></S>,
};

/* ---------------- route badge ---------------- */
export const ROUTE_STYLE: Record<Route, { pill: string; dot: string; label: string }> = {
  PDF: { pill: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30", dot: "bg-emerald-500", label: "Documents" },
  SQL: { pill: "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/30", dot: "bg-sky-500", label: "Database" },
  HYBRID: { pill: "bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30", dot: "bg-indigo-500", label: "Hybrid" },
  NONE: { pill: "bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10", dot: "bg-slate-400", label: "Insufficient evidence" },
  GENERAL_KNOWLEDGE: { pill: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30", dot: "bg-amber-500", label: "Ungrounded" },
};

export function RouteBadge({ route, small, withLabel }: { route: Route; small?: boolean; withLabel?: boolean }) {
  const s = ROUTE_STYLE[route];
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-md font-semibold ring-1 ring-inset",
      s.pill, small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs")}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {route}{withLabel && <span className="font-medium opacity-70">· {s.label}</span>}
    </span>
  );
}

export function Pill({
  children, tone = "slate", className,
}: {
  children: React.ReactNode;
  tone?: "slate" | "emerald" | "amber" | "sky" | "indigo" | "rose";
  className?: string;
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-50 text-slate-600 ring-slate-200 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10",
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30",
    amber: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30",
    sky: "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/30",
    indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30",
    rose: "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/30",
  };
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
      tones[tone], className)}>
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("surface", className)}>{children}</div>;
}

/* ---------------- provenance tag (uploaded vs sample) ---------------- */
export function OriginTag({ origin }: { origin?: "sample" | "uploaded" | null }) {
  if (!origin) return null;
  return origin === "uploaded" ? (
    <Pill tone="indigo">Your upload</Pill>
  ) : (
    <Pill tone="slate">Sample data</Pill>
  );
}

export function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{children}</h3>
      {hint && <span className="text-[11px] text-faint">{hint}</span>}
    </div>
  );
}

/* ---------------- button ---------------- */
export function Button({
  children, onClick, variant = "primary", size = "md", disabled, type = "button", className, title,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  const variants: Record<string, string> = {
    primary: "bg-indigo-600 text-white shadow-sm hover:bg-indigo-500 disabled:bg-indigo-400/50 disabled:text-white/70",
    secondary: "bg-surface text-body ring-1 ring-inset ring-line hover:bg-surface-2 disabled:opacity-50",
    ghost: "text-muted hover:bg-surface-2 hover:text-fg disabled:opacity-50",
    danger: "bg-surface text-rose-600 ring-1 ring-inset ring-rose-200 hover:bg-rose-50 disabled:opacity-50 dark:text-rose-400 dark:ring-rose-500/30 dark:hover:bg-rose-500/10",
  };
  const sizes: Record<string, string> = {
    sm: "h-8 px-3 text-[13px] gap-1.5 rounded-lg",
    md: "h-10 px-4 text-sm gap-2 rounded-lg",
    lg: "h-12 px-5 text-sm gap-2 rounded-xl",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title}
      className={cn("focus-ring inline-flex shrink-0 items-center justify-center font-semibold transition active:scale-[0.98]",
        variants[variant], sizes[size], className)}>
      {children}
    </button>
  );
}

/* ---------------- icon button (square, ghost) ---------------- */
export function IconButton({
  children, onClick, title, active, className,
}: {
  children: React.ReactNode; onClick?: () => void; title?: string; active?: boolean; className?: string;
}) {
  return (
    <button onClick={onClick} title={title} aria-label={title}
      className={cn(
        "focus-ring inline-flex h-8 w-8 items-center justify-center rounded-lg ring-1 ring-inset transition active:scale-95",
        active
          ? "bg-accent-soft text-accent ring-accent/30"
          : "text-muted ring-line hover:bg-surface-2 hover:text-fg",
        className)}>
      {children}
    </button>
  );
}

/* ---------------- segmented tab control ---------------- */
export function Tabs<T extends string>({
  tabs, active, onChange,
}: {
  tabs: { id: T; label: string; icon?: React.ReactNode }[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-xl border border-line bg-surface/80 p-1 shadow-sm backdrop-blur">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-[13px] font-semibold transition",
            active === t.id
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-muted hover:bg-surface-2 hover:text-fg")}>
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------- collapsible ---------------- */
export function Collapsible({
  title, icon, defaultOpen = true, right, children,
}: {
  title: React.ReactNode;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <Card>
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-t-[14px] px-4 py-3 text-left transition hover:bg-surface-2">
        <span className="flex items-center gap-2.5 text-sm font-semibold text-fg">
          <Icons.chevron className={cn("h-3.5 w-3.5 text-faint transition-transform", open && "rotate-90")} />
          {icon && <span className="text-accent">{icon}</span>}
          {title}
        </span>
        <span className="flex items-center gap-2">{right}</span>
      </button>
      {open && <div className="border-t border-line px-4 py-3.5">{children}</div>}
    </Card>
  );
}

/* ---------------- score bar ---------------- */
export function ScoreBar({ value, max = 1 }: { value?: number | null; max?: number }) {
  if (value == null) return <span className="text-faint">—</span>;
  const pct = Math.max(4, Math.min(100, (value / max) * 100));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-2">
        <span className="block h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono text-[10px] text-muted">{value.toFixed(3)}</span>
    </span>
  );
}

/* ---------------- empty state ---------------- */
export function EmptyState({
  icon, title, children,
}: { icon?: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-soft text-accent ring-1 ring-accent/20">
          {icon}
        </div>
      )}
      <h3 className="text-[15px] font-semibold text-fg">{title}</h3>
      {children && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">{children}</div>}
    </div>
  );
}
