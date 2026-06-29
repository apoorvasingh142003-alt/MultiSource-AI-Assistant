"use client";
import React from "react";
import {
  ask, askStream, fetchConfig, fetchExamples, fetchInventory, fetchSources,
  fetchSessions, createSession, deleteSession, renameSession, fetchMessages,
  editMessage, deleteMessage, regenerateMessage,
  ingestPdf, ingestSqlite, resetWorkspace,
  type AskScope, type AskOptions, type AgentStep,
} from "@/lib/api";
import type {
  AppConfig, AskResponse, ExampleQuestion, Inventory, Message, Session, SourceInfo,
} from "@/lib/types";
import { Icons, Tabs, Button, Card, EmptyState, cn } from "@/components/ui";
import Workspace from "@/components/Workspace";
import WorkspaceView from "@/components/WorkspaceView";
import Inspector from "@/components/Inspector";
import ChatSidebar from "@/components/ChatSidebar";
import ChatThread, { type ChatTurn } from "@/components/ChatThread";
import SettingsPanel from "@/components/SettingsPanel";
import { useAiSettings, resolveOutput } from "@/components/AiSettingsPanel";

type TabId = "chat" | "workspace" | "studio" | "inspector";
const SESSION_KEY = "nexus-active-session";

let _tid = 0;
const tempId = () => `t${++_tid}-${Date.now()}`;

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [examples, setExamples] = React.useState<ExampleQuestion[]>([]);
  const [, setSources] = React.useState<SourceInfo[]>([]);
  const [inventory, setInventory] = React.useState<Inventory | null>(null);
  const [connecting, setConnecting] = React.useState(true);

  const [tab, setTab] = React.useState<TabId>("chat");
  const [input, setInput] = React.useState("");
  const [turns, setTurns] = React.useState<ChatTurn[]>([]);
  const [busy, setBusy] = React.useState(false);
  const scope: AskScope = "all";   // answer from sample + uploaded sources

  const { settings, update: updateSettings } = useAiSettings();

  // sessions
  const [sessions, setSessions] = React.useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = React.useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);

  // dark mode
  const [dark, setDark] = React.useState(false);
  React.useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("theme") : null;
    const prefers = typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    setDark(saved ? saved === "dark" : !!prefers);
  }, []);
  React.useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  }, [dark]);

  // upload state
  const [pdfBusy, setPdfBusy] = React.useState(false);
  const [sqliteBusy, setSqliteBusy] = React.useState(false);
  const [resetting, setResetting] = React.useState(false);
  const [pdfMsg, setPdfMsg] = React.useState<string | null>(null);
  const [pdfErr, setPdfErr] = React.useState<string | null>(null);
  const [dbMsg, setDbMsg] = React.useState<string | null>(null);
  const [dbErr, setDbErr] = React.useState<string | null>(null);

  const lastResp = React.useMemo(
    () => [...turns].reverse().find((t) => t.resp)?.resp ?? null, [turns]);

  // ---- bootstrap ----
  const bootstrap = React.useCallback(() => {
    let cancelled = false;
    let tries = 0;
    const tick = async () => {
      try {
        const c = await fetchConfig();
        if (cancelled) return;
        setConfig(c);
        setConnecting(false);
        fetchExamples().then(setExamples).catch(() => {});
        fetchSources().then(setSources).catch(() => {});
        fetchInventory().then(setInventory).catch(() => {});
        fetchSessions().then(setSessions).catch(() => {});
      } catch {
        if (cancelled) return;
        tries += 1;
        setConnecting(true);
        if (tries < 80) setTimeout(tick, 700);
      }
    };
    tick();
    return () => { cancelled = true; };
  }, []);
  React.useEffect(() => bootstrap(), [bootstrap]);

  // restore last session
  React.useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem(SESSION_KEY) : null;
    if (saved) { setActiveSessionId(saved); loadSession(saved); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  React.useEffect(() => {
    try {
      if (activeSessionId) localStorage.setItem(SESSION_KEY, activeSessionId);
      else localStorage.removeItem(SESSION_KEY);
    } catch { /* ignore */ }
  }, [activeSessionId]);

  // keyboard shortcuts
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); handleNewSession(); }
      if ((e.metaKey || e.ctrlKey) && e.key === "e") { e.preventDefault(); window.dispatchEvent(new CustomEvent("aba:toggle-explain")); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- helpers ----
  const askOpts = React.useCallback((): AskOptions => {
    const { output_mode, output_format } = resolveOutput(settings.output);
    return {
      scope,
      output_mode, output_format,
      agent_role: settings.agentRole || null,
      custom_system_prompt: settings.customSystemPrompt || null,
      multi_agent: settings.multiAgent,
      agent_mode: settings.agentMode,
      temperature: settings.temperature > 0 ? settings.temperature : null,
    };
  }, [settings]);

  const patchTurn = (id: string, patch: Partial<ChatTurn>) =>
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  function messagesToTurns(msgs: Message[]): ChatTurn[] {
    const out: ChatTurn[] = [];
    let pendingUser: Message | null = null;
    for (const m of msgs) {
      if (m.role === "user") {
        if (pendingUser) out.push({ id: pendingUser.id, userMessageId: pendingUser.id, question: pendingUser.content, edited: !!pendingUser.edited_at });
        pendingUser = m;
      } else {
        out.push({
          id: m.id, userMessageId: pendingUser?.id, assistantMessageId: m.id,
          question: pendingUser?.content ?? "", text: m.content, route: m.route,
          edited: !!(pendingUser?.edited_at || m.edited_at),
        });
        pendingUser = null;
      }
    }
    if (pendingUser) out.push({ id: pendingUser.id, userMessageId: pendingUser.id, question: pendingUser.content });
    return out;
  }

  async function loadSession(id: string) {
    try {
      const msgs = await fetchMessages(id);
      setTurns(messagesToTurns(msgs));
    } catch { setTurns([]); }
  }

  async function ensureSession(): Promise<string> {
    if (activeSessionId) return activeSessionId;
    const s = await createSession();
    setSessions((prev) => [s, ...prev]);
    setActiveSessionId(s.id);
    return s.id;
  }

  // ---- ask ----
  const run = async (q: string) => {
    const query = q.trim();
    if (!query || busy) return;
    setTab("chat");
    setInput("");
    setBusy(true);
    const sid = await ensureSession();
    const id = tempId();
    setTurns((prev) => [...prev, { id, question: query, streaming: true, streamingText: "", agentSteps: [] }]);

    const opts: AskOptions = { ...askOpts(), session_id: sid };
    let acc = "";
    const steps: AgentStep[] = [];
    try {
      await askStream(query, opts, {
        onAgentStep: (s) => { steps.push(s); patchTurn(id, { agentSteps: [...steps] }); },
        onDelta: (t) => { acc += t; patchTurn(id, { streamingText: acc }); },
        onDone: (r) => { patchTurn(id, { resp: r, streaming: false }); },
        onError: () => { throw new Error("stream"); },
      });
    } catch {
      // fallback to non-streaming
      try {
        const r = await ask(query, opts);
        patchTurn(id, { resp: r, streaming: false });
      } catch {
        patchTurn(id, { streaming: false, error: "Could not reach the engine. Please try again." });
      }
    }
    // capture message ids for edit/delete/regenerate
    try {
      const msgs = await fetchMessages(sid);
      const lastA = [...msgs].reverse().find((m) => m.role === "assistant");
      const lastU = [...msgs].reverse().find((m) => m.role === "user");
      patchTurn(id, { assistantMessageId: lastA?.id, userMessageId: lastU?.id });
    } catch { /* ignore */ }
    fetchSessions().then(setSessions).catch(() => {});
    setBusy(false);
  };

  // ---- per-turn actions ----
  const regenerateTurn = async (turn: ChatTurn) => {
    if (!activeSessionId || !turn.assistantMessageId || busy) return;
    setBusy(true);
    patchTurn(turn.id, { streaming: true, streamingText: "", resp: undefined, text: undefined, agentSteps: [] });
    try {
      const r = await regenerateMessage(activeSessionId, turn.assistantMessageId, askOpts());
      patchTurn(turn.id, { resp: r, streaming: false });
    } catch {
      patchTurn(turn.id, { streaming: false, error: "Regeneration failed. Please try again." });
    }
    setBusy(false);
  };

  const editTurn = async (turn: ChatTurn, newText: string) => {
    if (!activeSessionId || !turn.userMessageId || busy) return;
    setBusy(true);
    patchTurn(turn.id, { question: newText, edited: true, streaming: true, streamingText: "", resp: undefined, text: undefined, agentSteps: [] });
    try {
      await editMessage(activeSessionId, turn.userMessageId, newText);
      if (turn.assistantMessageId) {
        const r = await regenerateMessage(activeSessionId, turn.assistantMessageId, askOpts());
        patchTurn(turn.id, { resp: r, streaming: false });
      } else {
        patchTurn(turn.id, { streaming: false });
      }
    } catch {
      patchTurn(turn.id, { streaming: false, error: "Could not update the message." });
    }
    fetchSessions().then(setSessions).catch(() => {});
    setBusy(false);
  };

  const deleteTurn = async (turn: ChatTurn) => {
    if (!activeSessionId) return;
    try {
      if (turn.userMessageId) await deleteMessage(activeSessionId, turn.userMessageId);
      if (turn.assistantMessageId) await deleteMessage(activeSessionId, turn.assistantMessageId);
    } catch { /* ignore */ }
    setTurns((prev) => prev.filter((t) => t.id !== turn.id));
    fetchSessions().then(setSessions).catch(() => {});
  };

  // ---- session management ----
  const handleNewSession = async () => {
    try {
      const s = await createSession();
      setSessions((prev) => [s, ...prev]);
      setActiveSessionId(s.id);
      setTurns([]); setInput(""); setTab("chat");
    } catch { /* ignore */ }
  };
  const handleSelectSession = async (id: string) => {
    setActiveSessionId(id); setTab("chat"); await loadSession(id);
  };
  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) { setActiveSessionId(null); setTurns([]); }
    } catch { /* ignore */ }
  };
  const handleRenameSession = async (id: string, title: string) => {
    try {
      await renameSession(id, title);
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    } catch { /* ignore */ }
  };

  // ---- uploads ----
  const refreshSources = () => { fetchSources().then(setSources).catch(() => {}); };
  const handlePdf = async (files: File[]) => {
    setPdfBusy(true); setPdfMsg(null); setPdfErr(null);
    try {
      const res = await ingestPdf(files);
      setInventory(res.inventory);
      const failed = res.documents.filter((d) => d.status === "error");
      if (failed.length) setPdfErr(failed.map((f) => `${f.name}: ${f.error || "failed"}`).join("; "));
      else setPdfMsg(res.message);
      refreshSources();
    } catch (e: any) { setPdfErr(e?.message || "Upload failed."); }
    finally { setPdfBusy(false); }
  };
  const handleSqlite = async (files: File[]) => {
    setSqliteBusy(true); setDbMsg(null); setDbErr(null);
    try {
      const res = await ingestSqlite(files);
      setInventory(res.inventory);
      const failed = res.databases.filter((d) => d.status === "error");
      if (failed.length) setDbErr(failed.map((f) => `${f.name}: ${f.error || "failed"}`).join("; "));
      else setDbMsg(res.message);
      refreshSources();
    } catch (e: any) { setDbErr(e?.message || "Upload failed."); }
    finally { setSqliteBusy(false); }
  };
  const handleReset = async () => {
    setResetting(true);
    try {
      const inv = await resetWorkspace();
      setInventory(inv);
      setPdfMsg(null); setPdfErr(null); setDbMsg(null); setDbErr(null);
      refreshSources();
    } catch { /* ignore */ }
    finally { setResetting(false); }
  };

  const tabs: { id: TabId; label: string; icon?: React.ReactNode }[] = [
    { id: "chat", label: "Chat", icon: <Icons.spark className="h-3.5 w-3.5" /> },
    { id: "workspace", label: "Workspace", icon: <Icons.grid className="h-3.5 w-3.5" /> },
    { id: "studio", label: "Studio", icon: <Icons.layers className="h-3.5 w-3.5" /> },
    { id: "inspector", label: "Inspector", icon: <Icons.inspect className="h-3.5 w-3.5" /> },
  ];

  const onComposerKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(input); }
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <ChatSidebar
        sessions={sessions} activeSessionId={activeSessionId} collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
        onSelectSession={handleSelectSession} onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession} onRenameSession={handleRenameSession}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* top app bar */}
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur-xl">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
                <Icons.layers className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-[15px] font-bold leading-tight text-slate-900">Nexus AI</h1>
                <p className="text-[11px] leading-tight text-slate-400">Adaptive Multi-Domain Intelligence Agent</p>
              </div>
            </div>

            <div className="order-3 w-full sm:order-2 sm:mx-auto sm:w-auto">
              <Tabs tabs={tabs} active={tab} onChange={setTab} />
            </div>

            <div className="order-2 ml-auto flex items-center gap-1.5 sm:order-3">
              <button onClick={() => setDark((d) => !d)}
                title={dark ? "Switch to light mode" : "Switch to dark mode"} aria-label="Toggle dark mode"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 ring-1 ring-inset ring-slate-200 transition hover:bg-slate-50">
                {dark ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                    <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
                  </svg>
                )}
              </button>
              <button onClick={() => setSettingsOpen(true)} title="Settings" aria-label="Open settings"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 ring-1 ring-inset ring-slate-200 transition hover:bg-slate-50">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.2.61.78 1.05 1.51 1.05H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
                </svg>
              </button>
              {(settings.agentRole || settings.customSystemPrompt || settings.agentMode || settings.output !== "auto") && (
                <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-1 text-[11px] font-medium text-indigo-600 ring-1 ring-inset ring-indigo-200">
                  <Icons.spark className="h-3 w-3" />{settings.agentMode ? "Agent" : "Customized"}
                </span>
              )}
              {config && (
                <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
                  <span className={cn("h-1.5 w-1.5 rounded-full", config.mode === "live" ? "bg-emerald-500" : "bg-amber-500")} />
                  {config.mode === "live" ? `Live · ${config.provider}` : "Offline"}
                </span>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          {connecting && (
            <div className="mx-auto mt-4 flex max-w-3xl items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[13px] text-slate-500 shadow-sm">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-500" />
              Connecting to the engine… (this can take a few seconds while it starts up)
            </div>
          )}

          {tab === "chat" && (
            <div className="mx-auto flex h-full max-w-3xl flex-col px-4 py-5">
              <div className="flex-1">
                {turns.length === 0 ? (
                  <Card className="mt-6">
                    <EmptyState icon={<Icons.spark className="h-6 w-6" />} title="Ask anything">
                      Have a two-way conversation grounded in your documents and data. Answers stream live with
                      verifiable citations; follow-up questions keep context. Turn on <b>Agent mode</b> in settings
                      for step-by-step tool reasoning.
                    </EmptyState>
                    {examples.length > 0 && (
                      <div className="flex flex-wrap justify-center gap-2 px-4 pb-5">
                        {examples.slice(0, 6).map((ex) => (
                          <button key={ex.question} onClick={() => run(ex.question)} title={ex.question}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[12px] text-slate-600 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-600">
                            {ex.label || ex.question.slice(0, 40)}
                          </button>
                        ))}
                      </div>
                    )}
                  </Card>
                ) : (
                  <ChatThread
                    turns={turns} busy={busy}
                    onOpenInspector={() => setTab("inspector")}
                    onEditQuestion={editTurn} onDeleteTurn={deleteTurn} onRegenerate={regenerateTurn}
                  />
                )}
              </div>

              {/* composer */}
              <div className="sticky bottom-0 mt-4 pb-1">
                <Card className="p-2.5 shadow-lg">
                  <textarea
                    value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onComposerKey}
                    rows={2} placeholder="Message Nexus AI…  (Enter to send, Shift+Enter for newline)"
                    className="focus-ring max-h-40 w-full resize-y rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-[15px] text-slate-800 placeholder:text-slate-400" />
                  <div className="mt-2 flex items-center justify-between">
                    <span className="flex items-center gap-2 text-[11px] text-slate-400">
                      {settings.agentMode && <span className="rounded bg-indigo-50 px-1.5 py-0.5 font-medium text-indigo-600">Agent mode</span>}
                      {settings.temperature > 0 && <span>temp {settings.temperature.toFixed(1)}</span>}
                    </span>
                    <Button size="md" onClick={() => run(input)} disabled={busy || !input.trim()}>
                      {busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/50 border-t-white" /> : <Icons.arrowR className="h-4 w-4" />}
                      {busy ? "Working…" : "Send"}
                    </Button>
                  </div>
                </Card>
              </div>
            </div>
          )}

          {tab === "workspace" && (
            <div className="px-5 py-6">
              <Workspace
                inventory={inventory}
                onUploadPdf={handlePdf} onUploadSqlite={handleSqlite} onReset={handleReset}
                pdfBusy={pdfBusy} sqliteBusy={sqliteBusy} resetting={resetting}
                pdfMsg={pdfMsg} pdfErr={pdfErr} dbMsg={dbMsg} dbErr={dbErr}
              />
            </div>
          )}
          {tab === "studio" && <div className="px-5 py-6"><div className="mx-auto max-w-7xl"><WorkspaceView /></div></div>}
          {tab === "inspector" && <div className="px-5 py-6"><div className="mx-auto max-w-7xl"><Inspector resp={lastResp} /></div></div>}
        </main>

        <footer className="px-5 pb-3 pt-1 text-center text-[11px] leading-relaxed text-slate-400">
          PDF + SQLite · agentic chat · hybrid retrieval (dense + BM25 + RRF + rerank) · grounded generation ·
          citation verification · Ctrl+K new chat
        </footer>
      </div>

      {settingsOpen && (
        <SettingsPanel
          settings={settings} onUpdate={updateSettings}
          dark={dark} onToggleDark={() => setDark((d) => !d)}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
