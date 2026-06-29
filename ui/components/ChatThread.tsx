"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import type { AgentStep } from "@/lib/api";
import { Button, Card, Icons, Pill, RouteBadge, cn } from "./ui";
import { CitedText } from "./trace";
import AnswerPanel from "./AnswerPanel";

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
}

export default function ChatThread({
  turns, onOpenInspector, onEditQuestion, onDeleteTurn, onRegenerate, busy,
}: {
  turns: ChatTurn[];
  onOpenInspector?: () => void;
  onEditQuestion: (turn: ChatTurn, newText: string) => void;
  onDeleteTurn: (turn: ChatTurn) => void;
  onRegenerate: (turn: ChatTurn) => void;
  busy: boolean;
}) {
  const endRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  return (
    <div className="space-y-6">
      {turns.map((turn) => (
        <Turn
          key={turn.id} turn={turn}
          onOpenInspector={onOpenInspector}
          onEditQuestion={onEditQuestion}
          onDeleteTurn={onDeleteTurn}
          onRegenerate={onRegenerate}
          busy={busy}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}

function Turn({
  turn, onOpenInspector, onEditQuestion, onDeleteTurn, onRegenerate, busy,
}: {
  turn: ChatTurn;
  onOpenInspector?: () => void;
  onEditQuestion: (turn: ChatTurn, newText: string) => void;
  onDeleteTurn: (turn: ChatTurn) => void;
  onRegenerate: (turn: ChatTurn) => void;
  busy: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(turn.question);

  return (
    <div className="fade-up space-y-3">
      {/* user message — right aligned bubble */}
      <div className="flex justify-end">
        <div className="group max-w-[80%]">
          {editing ? (
            <div className="rounded-2xl rounded-tr-sm bg-white p-2 shadow-sm ring-1 ring-slate-200">
              <textarea
                value={draft} onChange={(e) => setDraft(e.target.value)} rows={2}
                className="focus-ring w-full resize-y rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[14px] text-slate-800"
              />
              <div className="mt-1.5 flex justify-end gap-1.5">
                <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setDraft(turn.question); }}>Cancel</Button>
                <Button size="sm" disabled={busy || !draft.trim()}
                  onClick={() => { setEditing(false); onEditQuestion(turn, draft.trim()); }}>
                  <Icons.refresh className="h-3.5 w-3.5" />Save &amp; rerun
                </Button>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-sm">
              <span className="whitespace-pre-wrap">{turn.question}</span>
            </div>
          )}
          {!editing && (
            <div className="mt-1 flex items-center justify-end gap-2 opacity-0 transition group-hover:opacity-100">
              {turn.edited && <span className="text-[10px] text-slate-400">edited</span>}
              <button onClick={() => { setDraft(turn.question); setEditing(true); }}
                disabled={busy} title="Edit & rerun"
                className="text-[11px] font-medium text-slate-400 transition hover:text-indigo-500 disabled:opacity-40">
                Edit
              </button>
              <button onClick={() => onDeleteTurn(turn)} disabled={busy} title="Delete this turn"
                className="text-[11px] font-medium text-slate-400 transition hover:text-rose-500 disabled:opacity-40">
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
            <div>
              <AnswerPanel resp={turn.resp} onOpenInspector={onOpenInspector} />
              <div className="mt-1.5 flex items-center gap-2 pl-1">
                <button onClick={() => onRegenerate(turn)} disabled={busy}
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 transition hover:text-indigo-500 disabled:opacity-40">
                  <Icons.refresh className="h-3 w-3" />Regenerate
                </button>
              </div>
            </div>
          ) : turn.error ? (
            <Card className="flex items-start gap-2 px-4 py-3 text-[13px] text-amber-700 ring-1 ring-amber-200">
              <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />{turn.error}
            </Card>
          ) : (
            /* historical turn — text only (no persisted trace) */
            <Card className="p-4">
              <div className="mb-2 flex items-center gap-2">
                {turn.route && <RouteBadge route={turn.route as any} small withLabel />}
                <span className="text-[10.5px] uppercase tracking-wider text-slate-400">Previous answer</span>
              </div>
              <CitedText text={turn.text || ""} onCite={() => {}} rtl={false} />
              <div className="mt-2 flex items-center gap-2">
                <button onClick={() => onRegenerate(turn)} disabled={busy}
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 transition hover:text-indigo-500 disabled:opacity-40">
                  <Icons.refresh className="h-3 w-3" />Regenerate
                </button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function StreamingAssistant({ turn }: { turn: ChatTurn }) {
  const steps = turn.agentSteps ?? [];
  return (
    <Card className="p-5">
      {steps.length > 0 && (
        <div className="mb-3 space-y-1.5 rounded-xl bg-slate-50 p-3 ring-1 ring-inset ring-slate-200">
          <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-indigo-500">
            <Icons.route className="h-3.5 w-3.5" />Agent reasoning
          </div>
          {steps.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-[12px] text-slate-600">
              <Pill tone="indigo">{s.iteration}</Pill>
              <span className="font-mono text-[11px] text-indigo-600">{s.tool}</span>
              <span className="truncate text-slate-400">
                {typeof s.args?.query === "string" ? `“${s.args.query}”` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-indigo-500">
        <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
        {steps.length > 0 ? "Composing answer" : "Streaming answer"}
      </div>
      <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-slate-700">
        {turn.streamingText}
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-indigo-400 align-middle" />
      </p>
    </Card>
  );
}
