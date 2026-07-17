"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import type { AgentStep } from "@/lib/api";
import { Icons, RouteBadge, cn } from "./ui";
import { CitedText, CitationChips } from "./trace";
import { segmentAnswer } from "@/lib/tableParser";
import AnswerTable from "./AnswerTable";
import AnswerStateChip from "./AnswerStateChip";
import type { InspectorTab } from "./InspectorPanel";

export interface ChatTurn {
  id: string;
  userMessageId?: string;
  assistantMessageId?: string;
  question: string;
  resp?: AskResponse | null;     // full response (generated this session)
  text?: string;                 // stored text only (historical turns)
  route?: string | null;
  streaming?: boolean;
  streamingText?: string;
  agentSteps?: AgentStep[];
  edited?: boolean;
  error?: string | null;
  system?: boolean;              // system note (e.g. "uploaded X") — not a Q/A turn
}

export default function ChatThread({
  turns, onEditQuestion, onDeleteTurn, onRegenerate, onInspect, onCite, activeInspectId, busy,
}: {
  turns: ChatTurn[];
  onEditQuestion: (turn: ChatTurn, newText: string) => void;
  onDeleteTurn: (turn: ChatTurn) => void;
  onRegenerate: (turn: ChatTurn) => void;
  onInspect: (turn: ChatTurn, tab: InspectorTab) => void;
  onCite: (turn: ChatTurn, id: string) => void;
  activeInspectId: string | null;
  busy: boolean;
}) {
  const endRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  return (
    <div className="space-y-7">
      {turns.map((turn) =>
        turn.system ? (
          <SystemNote key={turn.id} turn={turn} />
        ) : (
          <Turn
            key={turn.id} turn={turn}
            onEditQuestion={onEditQuestion}
            onDeleteTurn={onDeleteTurn}
            onRegenerate={onRegenerate}
            onInspect={onInspect}
            onCite={onCite}
            active={activeInspectId === turn.id}
            busy={busy}
          />
        )
      )}
      <div ref={endRef} />
    </div>
  );
}

function SystemNote({ turn }: { turn: ChatTurn }) {
  return (
    <div className="fade-up flex justify-center">
      <span className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11.5px] font-medium ring-1 ring-inset",
        turn.error
          ? "bg-rose-50 text-rose-600 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/30"
          : "bg-surface-2 text-muted ring-line")}>
        {turn.error ? <Icons.alert className="h-3.5 w-3.5" /> : <Icons.check className="h-3.5 w-3.5" />}
        {turn.error || turn.question}
      </span>
    </div>
  );
}

function Turn({
  turn, onEditQuestion, onDeleteTurn, onRegenerate, onInspect, onCite, active, busy,
}: {
  turn: ChatTurn;
  onEditQuestion: (turn: ChatTurn, newText: string) => void;
  onDeleteTurn: (turn: ChatTurn) => void;
  onRegenerate: (turn: ChatTurn) => void;
  onInspect: (turn: ChatTurn, tab: InspectorTab) => void;
  onCite: (turn: ChatTurn, id: string) => void;
  active: boolean;
  busy: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(turn.question);
  const [copied, setCopied] = React.useState(false);

  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="fade-up space-y-3">
      {/* user message — right aligned bubble */}
      <div className="flex justify-end">
        <div className="group max-w-[80%]">
          {editing ? (
            <div className="rounded-2xl rounded-tr-sm bg-surface p-2 shadow-sm ring-1 ring-line">
              <textarea
                value={draft} onChange={(e) => setDraft(e.target.value)} rows={2}
                className="focus-ring w-full resize-y rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-[14px] text-fg"
              />
              <div className="mt-1.5 flex justify-end gap-1.5">
                <button onClick={() => { setEditing(false); setDraft(turn.question); }}
                  className="rounded-lg px-2.5 py-1 text-[12px] font-medium text-muted transition hover:bg-surface-2">Cancel</button>
                <button disabled={busy || !draft.trim()}
                  onClick={() => { setEditing(false); onEditQuestion(turn, draft.trim()); }}
                  className="inline-flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-[12px] font-semibold text-white transition hover:bg-accent-strong disabled:opacity-50">
                  <Icons.refresh className="h-3.5 w-3.5" />Save &amp; rerun
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-brand-gradient rounded-2xl rounded-tr-sm px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-md shadow-indigo-600/20">
              <span className="whitespace-pre-wrap">{turn.question}</span>
            </div>
          )}
          {!editing && (
            <div className="mt-1 flex items-center justify-end gap-2 opacity-0 transition group-hover:opacity-100">
              {turn.edited && <span className="text-[10px] text-faint">edited</span>}
              <button onClick={() => { setDraft(turn.question); setEditing(true); }}
                disabled={busy} title="Edit & rerun"
                className="text-[11px] font-medium text-faint transition hover:text-accent disabled:opacity-40">
                Edit
              </button>
              <button onClick={() => onDeleteTurn(turn)} disabled={busy} title="Delete this turn"
                className="text-[11px] font-medium text-faint transition hover:text-rose-500 disabled:opacity-40">
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* assistant message */}
      <div className="flex justify-start">
        <div className="w-full">
          {turn.streaming ? (
            <StreamingAssistant turn={turn} />
          ) : turn.resp ? (
            <AssistantAnswer
              turn={turn} resp={turn.resp} active={active} busy={busy} copied={copied}
              onCopy={copy} onInspect={onInspect} onCite={onCite} onRegenerate={onRegenerate}
            />
          ) : turn.error ? (
            <div className="flex items-start gap-2 rounded-2xl bg-amber-50 px-4 py-3 text-[13px] text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30">
              <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />{turn.error}
            </div>
          ) : (
            /* historical turn — text only (no persisted trace) */
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {turn.route && <RouteBadge route={turn.route as any} small withLabel />}
                <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[10.5px] text-faint ring-1 ring-inset ring-line">
                  <Icons.clock className="h-3 w-3" />previous answer · not re-verified
                </span>
              </div>
              <CitedText text={turn.text || ""} onCite={() => {}} rtl={false} />
              <TurnActions>
                <ActionBtn icon={<Icons.refresh className="h-3.5 w-3.5" />} label="Regenerate"
                  onClick={() => onRegenerate(turn)} disabled={busy} />
              </TurnActions>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AssistantAnswer({
  turn, resp, active, busy, copied, onCopy, onInspect, onCite, onRegenerate,
}: {
  turn: ChatTurn; resp: AskResponse; active: boolean; busy: boolean; copied: boolean;
  onCopy: (t: string) => void;
  onInspect: (turn: ChatTurn, tab: InspectorTab) => void;
  onCite: (turn: ChatTurn, id: string) => void;
  onRegenerate: (turn: ChatTurn) => void;
}) {
  const rtl = /[֐-׿]/.test(resp.answer);
  const segments = segmentAnswer(resp.answer);
  const hasTables = segments.some((s) => s.type === "table");

  return (
    <div className={cn(
      "space-y-3 rounded-2xl px-1 py-0.5 transition",
      active && "ring-2 ring-accent/20",
    )}>
      {/* tri-state chip + verification warning */}
      <div className="flex flex-wrap items-center gap-2">
        <AnswerStateChip resp={resp} />
        {resp.trace.route && (
          <button onClick={() => onInspect(turn, "trace")} title="Open the retrieval trace">
            <RouteBadge route={resp.trace.route.route} small withLabel />
          </button>
        )}
      </div>

      {resp.verification_warning && (
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[12.5px] text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30">
          <Icons.alert className="mt-0.5 h-3.5 w-3.5 shrink-0" />{resp.verification_warning}
        </div>
      )}

      {/* answer body (with inline tables) */}
      {hasTables ? (
        <div className="space-y-2">
          {segments.map((seg, i) =>
            seg.type === "text"
              ? <CitedText key={i} text={seg.content} onCite={(id) => onCite(turn, id)} rtl={rtl} />
              : <AnswerTable key={i} table={seg.table} />
          )}
        </div>
      ) : (
        <CitedText text={resp.answer} onCite={(id) => onCite(turn, id)} rtl={rtl} />
      )}

      {/* source chips */}
      {resp.citations.length > 0 && (
        <div className="pt-0.5">
          <CitationChips citations={resp.citations} onCite={(id) => onCite(turn, id)} />
        </div>
      )}

      {/* actions */}
      <TurnActions>
        <ActionBtn icon={<Icons.inspect className="h-3.5 w-3.5" />} label="Inspect"
          onClick={() => onInspect(turn, "answer")} active={active} />
        <ActionBtn icon={<Icons.copy className="h-3.5 w-3.5" />} label={copied ? "Copied!" : "Copy"}
          onClick={() => onCopy(resp.answer)} />
        <ActionBtn icon={<Icons.refresh className="h-3.5 w-3.5" />} label="Regenerate"
          onClick={() => onRegenerate(turn)} disabled={busy} />
      </TurnActions>
    </div>
  );
}

function TurnActions({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-1 pl-0.5">{children}</div>;
}

function ActionBtn({ icon, label, onClick, disabled, active }: {
  icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean; active?: boolean;
}) {
  return (
    <button onClick={onClick} disabled={disabled} title={label}
      className={cn(
        "inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-medium transition disabled:opacity-40",
        active ? "bg-accent-soft text-accent" : "text-faint hover:bg-surface-2 hover:text-accent",
      )}>
      {icon}<span className="hidden sm:inline">{label}</span>
    </button>
  );
}

function StreamingAssistant({ turn }: { turn: ChatTurn }) {
  const steps = turn.agentSteps ?? [];
  return (
    <div className="space-y-3">
      {steps.length > 0 && (
        <div className="space-y-1.5 rounded-xl bg-surface-2 p-3 ring-1 ring-inset ring-line">
          <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-accent">
            <Icons.route className="h-3.5 w-3.5" />Agent reasoning
          </div>
          {steps.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-[12px] text-body">
              <span className="rounded bg-accent-soft px-1.5 py-0.5 font-mono text-[10px] font-bold text-accent ring-1 ring-inset ring-accent/25">{s.iteration}</span>
              <span className="font-mono text-[11px] text-accent">{s.tool}</span>
              <span className="truncate text-muted">
                {typeof s.args?.query === "string" ? `“${s.args.query}”` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-accent">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
        {steps.length > 0 ? "Composing answer" : "Thinking"}
      </div>
      {turn.streamingText ? (
        <p className="whitespace-pre-wrap text-[15px] leading-[1.75] text-body">
          {turn.streamingText}
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" />
        </p>
      ) : (
        <div className="space-y-2">
          <div className="skeleton h-3.5 w-3/4" />
          <div className="skeleton h-3.5 w-full" />
          <div className="skeleton h-3.5 w-5/6" />
        </div>
      )}
    </div>
  );
}
