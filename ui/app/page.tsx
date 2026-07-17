"use client";
import React from "react";
import {
  ask, askStream, fetchConfig, fetchExamples, fetchInventory, fetchSources,
  fetchSessions, createSession, deleteSession, renameSession, fetchMessages,
  editMessage, deleteMessage, regenerateMessage, fetchHealth,
  ingestPdf, ingestSqlite, resetWorkspace,
  type AskScope, type AskOptions, type AgentStep,
} from "@/lib/api";
import type {
  AppConfig, ExampleQuestion, Inventory, Message, Session, SourceInfo,
} from "@/lib/types";
import { Icons, IconButton, cn } from "@/components/ui";
import AccountMenu from "@/components/AccountMenu";
import ChatSidebar from "@/components/ChatSidebar";
import ChatThread, { type ChatTurn } from "@/components/ChatThread";
import Composer from "@/components/Composer";
import InspectorPanel, { type InspectorTab } from "@/components/InspectorPanel";
import SettingsPanel from "@/components/SettingsPanel";
import { useAiSettings, resolveOutput } from "@/components/AiSettingsPanel";

const SESSION_KEY = "nexus-active-session";

let _tid = 0;
const tempId = () => `t${++_tid}-${Date.now()}`;

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [examples, setExamples] = React.useState<ExampleQuestion[]>([]);
  const [, setSources] = React.useState<SourceInfo[]>([]);
  const [inventory, setInventory] = React.useState<Inventory | null>(null);
  const [connecting, setConnecting] = React.useState(true);
  // "warming" → backend reachable but the engine is still building its index (cold start).
  const [warming, setWarming] = React.useState(false);

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

  // inspector drawer
  const [inspectorOpen, setInspectorOpen] = React.useState(false);
  const [inspectorTab, setInspectorTab] = React.useState<InspectorTab>("answer");
  const [inspectId, setInspectId] = React.useState<string | null>(null);

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

  // The response currently shown in the inspector: the selected turn, else the latest answer.
  const inspectResp = React.useMemo(() => {
    const sel = turns.find((t) => t.id === inspectId)?.resp;
    if (sel) return sel;
    return [...turns].reverse().find((t) => t.resp)?.resp ?? null;
  }, [turns, inspectId]);

  // ---- bootstrap ----
  const bootstrap = React.useCallback(() => {
    let cancelled = false;
    let tries = 0;
    const tick = async () => {
      try {
        // /health never 500s. If the backend is reachable but still building its index on a
        // cold start, it reports {ready:false} — we show a calm "warming up" banner and keep
        // polling instead of erroring. Only an unreachable backend counts as "connecting".
        const h = await fetchHealth();
        if (cancelled) return;
        setConnecting(false);
        if (!h.ready) {
          setWarming(true);
          tries += 1;
          if (tries < 120) setTimeout(tick, 700);
          return;
        }
        setWarming(false);
        const c = await fetchConfig();
        if (cancelled) return;
        setConfig(c);
        fetchExamples().then(setExamples).catch(() => {});
        fetchSources().then(setSources).catch(() => {});
        fetchInventory().then(setInventory).catch(() => {});
        fetchSessions().then(setSessions).catch(() => {});
      } catch {
        if (cancelled) return;
        tries += 1;
        setConnecting(true);
        setWarming(false);
        if (tries < 120) setTimeout(tick, 700);
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
      if ((e.metaKey || e.ctrlKey) && e.key === "e") { e.preventDefault(); setInspectorOpen((v) => !v); }
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

  // ---- inspector wiring ----
  const openInspector = (turn: ChatTurn, tab: InspectorTab) => {
    setInspectId(turn.id);
    setInspectorTab(tab);
    setInspectorOpen(true);
  };
  const openCitation = (turn: ChatTurn, evId: string) => {
    setInspectId(turn.id);
    setInspectorTab("answer");
    setInspectorOpen(true);
    // let the panel render, then scroll the evidence into view + pulse it
    setTimeout(() => {
      const el = document.getElementById(`ev-${evId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.classList.add("cite-pulse");
      setTimeout(() => el?.classList.remove("cite-pulse"), 1700);
    }, 260);
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
      setTurns([]); setInput("");
    } catch { /* ignore */ }
  };
  const handleSelectSession = async (id: string) => {
    setActiveSessionId(id); await loadSession(id);
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
  const addSystemNote = (text: string, error = false) =>
    setTurns((prev) => [...prev, { id: tempId(), question: text, system: true, error: error ? text : null }]);

  const handlePdf = async (files: File[]) => {
    setPdfBusy(true); setPdfMsg(null); setPdfErr(null);
    try {
      const res = await ingestPdf(files);
      setInventory(res.inventory);
      const failed = res.documents.filter((d) => d.status === "error");
      if (failed.length) {
        const msg = failed.map((f) => `${f.name}: ${f.error || "failed"}`).join("; ");
        setPdfErr(msg); addSystemNote(`Upload failed — ${msg}`, true);
      } else {
        setPdfMsg(res.message);
        const names = res.documents.map((d) => d.name).join(", ");
        addSystemNote(`Added ${res.documents.length} document(s): ${names}. Ask away — answers can now cite them.`);
      }
      refreshSources();
    } catch (e: any) {
      const msg = e?.message || "Upload failed.";
      setPdfErr(msg); addSystemNote(`Upload failed — ${msg}`, true);
    }
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

  const uploadedCount =
    (inventory?.documents.filter((d) => d.origin === "uploaded").length ?? 0) +
    (inventory?.databases.filter((d) => d.origin === "uploaded").length ?? 0);

  const sourcesProps = {
    inventory, onUploadPdf: handlePdf, onUploadSqlite: handleSqlite, onReset: handleReset,
    pdfBusy, sqliteBusy, resetting, pdfMsg, pdfErr, dbMsg, dbErr,
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
        <header className="glass sticky top-0 z-20 border-b border-line">
          <div className="flex items-center gap-x-3 px-5 py-2.5">
            <div className="flex items-center gap-2.5">
              <div className="bg-brand-gradient flex h-8 w-8 items-center justify-center rounded-xl text-white shadow-glow">
                <Icons.layers className="h-4.5 w-4.5" />
              </div>
              <div>
                <h1 className="text-[14px] font-bold leading-tight text-fg">Nexus AI</h1>
                <p className="text-[10.5px] leading-tight text-faint">Grounded multi-source assistant</p>
              </div>
            </div>

            <div className="ml-auto flex items-center gap-2">
              {config && (
                <span className="hidden items-center gap-1.5 rounded-lg bg-surface-2 px-2.5 py-1.5 text-[11px] font-medium text-muted ring-1 ring-inset ring-line sm:inline-flex">
                  <span className={cn("h-1.5 w-1.5 rounded-full", config.mode === "live" ? "bg-emerald-500 shadow-[0_0_0_3px] shadow-emerald-500/20" : "bg-amber-500")} />
                  {config.mode === "live" ? `Live · ${config.provider}` : "Offline"}
                </span>
              )}
              <IconButton onClick={() => { setInspectorTab("sources"); setInspectorOpen(true); }}
                title="Sources & uploads" active={inspectorOpen && inspectorTab === "sources"}>
                <Icons.doc className="h-4 w-4" />
                {uploadedCount > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[9px] font-bold text-white">{uploadedCount}</span>
                )}
              </IconButton>
              <IconButton onClick={() => setInspectorOpen((v) => !v)} title="Inspector (Ctrl+E)" active={inspectorOpen}>
                <Icons.inspect className="h-4 w-4" />
              </IconButton>
              <IconButton onClick={() => setDark((d) => !d)} title={dark ? "Switch to light mode" : "Switch to dark mode"}>
                {dark ? <Icons.sun className="h-4 w-4" /> : <Icons.moon className="h-4 w-4" />}
              </IconButton>
              <IconButton onClick={() => setSettingsOpen(true)} title="Settings">
                <Icons.gear className="h-4 w-4" />
              </IconButton>
              <div className="ml-0.5"><AccountMenu /></div>
            </div>
          </div>
        </header>

        <main className="flex flex-1 flex-col overflow-hidden">
          {connecting && (
            <div className="mx-auto mt-4 flex max-w-3xl items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-[13px] text-muted shadow-sm">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
              Connecting to the engine… (this can take a few seconds while it starts up)
            </div>
          )}

          {!connecting && warming && (
            <div className="mx-auto mt-4 flex max-w-3xl items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] font-medium text-amber-800 shadow-sm dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-amber-300 border-t-amber-600" />
              Warming up — building the knowledge index. This only happens on a cold start; your
              first answer will be ready in a moment.
            </div>
          )}

          {/* scrollable thread */}
          <div className="scroll-thin flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-4 py-6">
              {turns.length === 0 ? (
                <Welcome examples={examples} onPick={run} onUpload={() => { setInspectorTab("sources"); setInspectorOpen(true); }} />
              ) : (
                <ChatThread
                  turns={turns} busy={busy}
                  onEditQuestion={editTurn} onDeleteTurn={deleteTurn} onRegenerate={regenerateTurn}
                  onInspect={openInspector} onCite={openCitation} activeInspectId={inspectId}
                />
              )}
            </div>
          </div>

          {/* composer */}
          <div className="border-t border-line bg-app/60 px-4 py-3 backdrop-blur">
            <Composer
              value={input} onChange={setInput} onSend={() => run(input)} onAttach={handlePdf}
              busy={busy} warming={warming} pdfBusy={pdfBusy}
              settings={settings} onUpdateSettings={updateSettings}
            />
          </div>
        </main>
      </div>

      <InspectorPanel
        open={inspectorOpen} resp={inspectResp} tab={inspectorTab}
        onTabChange={setInspectorTab} onClose={() => setInspectorOpen(false)}
        sources={sourcesProps}
      />

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

/* ---- empty-state welcome ---- */
function Welcome({
  examples, onPick, onUpload,
}: {
  examples: ExampleQuestion[];
  onPick: (q: string) => void;
  onUpload: () => void;
}) {
  return (
    <div className="fade-up flex min-h-[52vh] flex-col items-center justify-center text-center">
      <div className="bg-brand-gradient mb-5 flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-glow">
        <Icons.spark className="h-7 w-7" />
      </div>
      <h2 className="text-[22px] font-bold text-fg">What do you want to know?</h2>
      <p className="mt-2 max-w-md text-[13.5px] leading-relaxed text-muted">
        Ask across your documents and data. Every answer is labeled by how much to trust it —{" "}
        <span className="font-medium text-emerald-600 dark:text-emerald-400">grounded &amp; cited</span>,{" "}
        <span className="font-medium text-amber-600 dark:text-amber-400">reasoned advice</span>, or an honest{" "}
        <span className="font-medium text-slate-500 dark:text-slate-400">not-found</span>.
      </p>

      {examples.length > 0 && (
        <div className="mt-7 grid w-full max-w-xl gap-2 sm:grid-cols-2">
          {examples.slice(0, 4).map((ex) => (
            <button key={ex.question} onClick={() => onPick(ex.question)} title={ex.question}
              className="group flex items-start gap-2.5 rounded-xl border border-line bg-surface px-3.5 py-3 text-left transition hover:border-accent/40 hover:bg-accent-soft">
              <Icons.arrowR className="mt-0.5 h-4 w-4 shrink-0 text-faint transition group-hover:text-accent" />
              <span className="text-[13px] leading-snug text-body group-hover:text-accent">
                {ex.label || ex.question.slice(0, 60)}
              </span>
            </button>
          ))}
        </div>
      )}

      <button onClick={onUpload}
        className="mt-6 inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted transition hover:text-accent">
        <Icons.upload className="h-4 w-4" />Upload your own PDF or database
      </button>
    </div>
  );
}
