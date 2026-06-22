"use client";
import React from "react";
import {
  ask, askStream, fetchConfig, fetchExamples, fetchInventory, fetchSources,
  fetchSessions, createSession, deleteSession, renameSession, fetchMessages,
  ingestPdf, ingestSqlite, resetWorkspace, type AskScope,
} from "@/lib/api";
import type {
  AppConfig, AskResponse, ExampleQuestion, Inventory, Message, Session, SourceInfo,
} from "@/lib/types";
import { Icons, Tabs, cn } from "@/components/ui";
import Workspace from "@/components/Workspace";
import WorkspaceView from "@/components/WorkspaceView";
import Inspector from "@/components/Inspector";
import Demo from "@/components/Demo";
import ChatSidebar from "@/components/ChatSidebar";
import { useAiSettings } from "@/components/AiSettingsPanel";

type TabId = "workspace" | "studio" | "inspector" | "demo";

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [examples, setExamples] = React.useState<ExampleQuestion[]>([]);
  const [sources, setSources] = React.useState<SourceInfo[]>([]);
  const [inventory, setInventory] = React.useState<Inventory | null>(null);

  const [tab, setTab] = React.useState<TabId>("workspace");
  const [question, setQuestion] = React.useState("");
  const [role, setRole] = React.useState<string | null>(null);
  const [outputMode, setOutputMode] = React.useState("Standard Response");
  const [resp, setResp] = React.useState<AskResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [streamingText, setStreamingText] = React.useState("");   // live SSE partial answer
  const [error, setError] = React.useState<string | null>(null);
  const [connecting, setConnecting] = React.useState(true);

  // AI Settings (Section 2)
  const { settings: aiSettings, update: updateAiSettings } = useAiSettings();

  // Chat sessions (Section 5)
  const [sessions, setSessions] = React.useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = React.useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);

  // Dark mode (Section 12) — manual toggle over prefers-color-scheme, persisted.
  const [dark, setDark] = React.useState(false);
  React.useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("theme") : null;
    const prefers = typeof window !== "undefined"
      && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
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

  // Resilient bootstrap: retry until the engine answers (covers container warm-up).
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
        // Load sessions
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

  // Keyboard shortcuts (Section 12)
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+K: New chat
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        handleNewSession();
      }
      // Ctrl+E: toggle the explainability panel on the current answer
      if ((e.metaKey || e.ctrlKey) && e.key === "e") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("aba:toggle-explain"));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const run = async (q: string, scope: AskScope = "workspace") => {
    const query = q.trim();
    if (!query) return;
    setTab("workspace");
    setQuestion(query);
    setLoading(true);
    setError(null);
    setResp(null);
    setStreamingText("");
    const opts = {
      custom_system_prompt: aiSettings.customSystemPrompt || null,
      agent_role: aiSettings.agentRole || null,
      output_format: aiSettings.outputFormat,
      session_id: activeSessionId,
      multi_agent: aiSettings.multiAgent,
    };

    // Preferred path: stream the answer over SSE (Section 12.3).
    try {
      let acc = "";
      await askStream(query, scope, role, outputMode, opts, {
        onDelta: (t) => { acc += t; setStreamingText(acc); },
        onDone: (r) => {
          setResp(r);
          setStreamingText("");
          setLoading(false);
          fetchSessions().then(setSessions).catch(() => {});
        },
        onError: () => { throw new Error("stream error"); },
      });
      if (loading) setLoading(false);
      return;
    } catch {
      // fall through to the non-streaming path
      setStreamingText("");
    }

    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await ask(query, scope, role, outputMode, opts);
        setResp(r);
        setError(null);
        setLoading(false);
        fetchSessions().then(setSessions).catch(() => {});
        return;
      } catch {
        if (attempt === 0) setError("Reaching the engine… retrying.");
        await new Promise((res) => setTimeout(res, 1200));
      }
    }
    setLoading(false);
    setError("Could not reach the engine after several tries. Please confirm the API is running.");
    bootstrap();
  };

  const refreshSources = () => {
    fetchSources().then(setSources).catch(() => {});
  };

  const clearQuestion = () => {
    setQuestion("");
    setResp(null);
    setError(null);
  };

  // Session management
  const handleNewSession = async () => {
    try {
      const s = await createSession();
      setSessions((prev) => [s, ...prev]);
      setActiveSessionId(s.id);
      clearQuestion();
    } catch {
      /* ignore */
    }
  };

  const handleSelectSession = async (id: string) => {
    setActiveSessionId(id);
    // Load messages from session
    try {
      const msgs = await fetchMessages(id);
      if (msgs.length > 0) {
        const lastUserMsg = [...msgs].reverse().find((m) => m.role === "user");
        const lastAssistantMsg = [...msgs].reverse().find((m) => m.role === "assistant");
        if (lastUserMsg) setQuestion(lastUserMsg.content);
        // Note: we don't restore the full AskResponse from session — just the question
      }
    } catch {
      /* ignore */
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) {
        setActiveSessionId(null);
        clearQuestion();
      }
    } catch {
      /* ignore */
    }
  };

  const handleRenameSession = async (id: string, title: string) => {
    try {
      await renameSession(id, title);
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, title } : s))
      );
    } catch {
      /* ignore */
    }
  };

  const handlePdf = async (files: File[]) => {
    setPdfBusy(true); setPdfMsg(null); setPdfErr(null);
    try {
      const res = await ingestPdf(files);
      setInventory(res.inventory);
      const failed = res.documents.filter((d) => d.status === "error");
      if (failed.length) setPdfErr(failed.map((f) => `${f.name}: ${f.error || "failed"}`).join("; "));
      else setPdfMsg(res.message);
      refreshSources();
    } catch (e: any) {
      setPdfErr(e?.message || "Upload failed.");
    } finally {
      setPdfBusy(false);
    }
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
    } catch (e: any) {
      setDbErr(e?.message || "Upload failed.");
    } finally {
      setSqliteBusy(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      const inv = await resetWorkspace();
      setInventory(inv);
      setResp(null); setQuestion(""); setError(null);
      setPdfMsg(null); setPdfErr(null); setDbMsg(null); setDbErr(null);
      refreshSources();
    } catch {
      /* ignore */
    } finally {
      setResetting(false);
    }
  };

  const tabs: { id: TabId; label: string; icon?: React.ReactNode }[] = [
    { id: "workspace", label: "Workspace", icon: <Icons.grid className="h-3.5 w-3.5" /> },
    { id: "studio", label: "Studio", icon: <Icons.layers className="h-3.5 w-3.5" /> },
    { id: "inspector", label: "Inspector", icon: <Icons.inspect className="h-3.5 w-3.5" /> },
    { id: "demo", label: "Demo", icon: <Icons.play className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Chat Sidebar (Section 5) */}
      <ChatSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
      />

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* ---- top app bar ---- */}
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
              {/* Dark mode toggle (Section 12) */}
              <button
                onClick={() => setDark((d) => !d)}
                title={dark ? "Switch to light mode" : "Switch to dark mode"}
                aria-label="Toggle dark mode"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 ring-1 ring-inset ring-slate-200 transition hover:bg-slate-50"
              >
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
              {/* Active AI settings indicator */}
              {(aiSettings.agentRole || aiSettings.customSystemPrompt || aiSettings.outputFormat !== "auto") && (
                <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-1 text-[11px] font-medium text-indigo-600 ring-1 ring-inset ring-indigo-200">
                  <Icons.spark className="h-3 w-3" />
                  AI customized
                </span>
              )}
              {config && (
                <>
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
                    <span className={cn("h-1.5 w-1.5 rounded-full", config.mode === "live" ? "bg-emerald-500" : "bg-amber-500")} />
                    {config.mode === "live" ? `Live · ${config.provider}` : "Offline"}
                  </span>
                  <span className="hidden items-center rounded-md bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200 md:inline-flex">
                    {config.models.generation}
                  </span>
                </>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-5 py-6">
          <div className="mx-auto max-w-7xl">
            {connecting && (
              <div className="mb-4 flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[13px] text-slate-500 shadow-sm">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-500" />
                Connecting to the engine… (this can take a few seconds while it starts up)
              </div>
            )}

            {tab === "workspace" && (
              <Workspace
                inventory={inventory}
                question={question} setQuestion={setQuestion}
                role={role} setRole={setRole}
                outputMode={outputMode} setOutputMode={setOutputMode}
                aiSettings={aiSettings} onAiSettingsUpdate={updateAiSettings}
                onAsk={run} onClear={clearQuestion} resp={resp} loading={loading} error={error}
                streamingText={streamingText}
                onOpenInspector={() => setTab("inspector")}
                onUploadPdf={handlePdf} onUploadSqlite={handleSqlite} onReset={handleReset}
                pdfBusy={pdfBusy} sqliteBusy={sqliteBusy} resetting={resetting}
                pdfMsg={pdfMsg} pdfErr={pdfErr} dbMsg={dbMsg} dbErr={dbErr}
                examples={examples}
              />
            )}
            {tab === "studio" && <WorkspaceView />}
            {tab === "inspector" && <Inspector resp={resp} />}
            {tab === "demo" && (
              <Demo examples={examples} sources={sources} config={config} inventory={inventory}
                onRun={(q) => run(q, "demo")} />
            )}
          </div>
        </main>

        <footer className="px-5 pb-4 pt-2 text-center text-[11px] leading-relaxed text-slate-400">
          PDF + SQLite · query routing · hybrid retrieval (dense + BM25 + RRF + rerank) · grounded generation ·
          citation verification · Ctrl+K new chat
        </footer>
      </div>
    </div>
  );
}
