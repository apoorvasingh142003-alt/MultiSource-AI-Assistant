"use client";
import React from "react";
import type { ActionConfig, McpInfo, McpServer } from "@/lib/types";
import {
  addMcpServer, fetchActions, fetchMcpInfo, fetchMcpServers, fetchMcpServerTools,
  removeMcpServer, updateActionConfig,
} from "@/lib/api";
import { Button, Card, Icons, Pill, cn } from "./ui";

/* ============================================================================
 * Actions & MCP configuration (Phase 6) — lives in the Sources tab.
 *
 * - Actions: per-action n8n webhook URL + optional signing secret + enable
 *   toggle. Unconfigured actions still work in "simulated" mode (audit-log
 *   only), so the propose→confirm flow is demo-able with zero setup.
 * - MCP server: the address other AI tools (Claude Desktop, agents, n8n MCP
 *   nodes) paste to consume this workspace's knowledge base, read-only.
 * - External MCP servers: endpoints this assistant consumes as extra agent
 *   tools (client side).
 * ========================================================================== */
export default function AutomationPanel() {
  const [actions, setActions] = React.useState<ActionConfig[]>([]);
  const [mcpInfo, setMcpInfo] = React.useState<McpInfo | null>(null);
  const [servers, setServers] = React.useState<McpServer[]>([]);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    fetchActions().then(setActions).catch(() => {});
    fetchMcpInfo().then(setMcpInfo).catch(() => {});
    fetchMcpServers().then(setServers).catch(() => {});
    setLoaded(true);
  }, []);

  if (!loaded) return null;

  return (
    <>
      <Card className="p-4">
        <h3 className="mb-1 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-muted">
          <Icons.bolt className="h-3.5 w-3.5 text-violet-500" /> Actions &amp; automations (n8n)
        </h3>
        <p className="mb-3 text-[11.5px] leading-relaxed text-faint">
          The assistant proposes actions in chat (create a lead, escalate, create an invoice);
          you confirm before anything is sent. Paste each action&apos;s n8n webhook URL to go live —
          without one, confirmed actions are recorded locally as <span className="font-medium">simulated</span>.
        </p>
        <div className="space-y-2">
          {actions.map((a) => (
            <ActionConfigRow key={a.action} config={a}
              onSaved={(patch) => setActions((prev) =>
                prev.map((x) => (x.action === a.action ? { ...x, ...patch } : x)))} />
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <h3 className="mb-1 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-muted">
          <Icons.link className="h-3.5 w-3.5 text-violet-500" /> MCP
        </h3>
        {mcpInfo && (
          <div className="rounded-xl border border-line bg-surface-2/60 p-3">
            <div className="text-[12px] font-semibold text-fg">This workspace as an MCP server</div>
            <p className="mt-0.5 text-[11.5px] leading-relaxed text-faint">
              Point Claude Desktop or any MCP client (streamable HTTP) at this endpoint to query
              your knowledge base — read-only tools: {mcpInfo.tools.map((t) => t.name).join(", ")}.
            </p>
            <div className="mt-2 flex items-center gap-1.5">
              <code className="min-w-0 flex-1 truncate rounded-lg bg-surface px-2.5 py-1.5 font-mono text-[11px] text-fg ring-1 ring-inset ring-line">
                {mcpInfo.url}
              </code>
              <Button variant="ghost" size="sm" title="Copy MCP endpoint"
                onClick={() => navigator.clipboard.writeText(mcpInfo.url)}>
                <Icons.copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
        <ExternalServers servers={servers} setServers={setServers} />
      </Card>
    </>
  );
}

function ActionConfigRow({
  config, onSaved,
}: {
  config: ActionConfig;
  onSaved: (patch: Partial<ActionConfig>) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const [secret, setSecret] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [msg, setMsg] = React.useState<string | null>(null);

  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      const res = await updateActionConfig(config.action, {
        ...(url.trim() || url === "" ? { webhook_url: url.trim() } : {}),
        ...(secret.trim() ? { secret: secret.trim() } : {}),
      });
      onSaved({ configured: res.configured, has_secret: config.has_secret || !!secret.trim() });
      setMsg(res.configured ? "Saved — this action now dispatches to n8n." : "Saved — webhook cleared (simulated mode).");
      setSecret("");
    } catch { setMsg("Could not save the webhook."); }
    setSaving(false);
  };

  const toggle = async () => {
    try {
      const res = await updateActionConfig(config.action, { enabled: !config.enabled });
      onSaved({ enabled: res.enabled });
    } catch { /* ignore */ }
  };

  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[12.5px] font-medium text-fg">
            <Icons.bolt className="h-3.5 w-3.5 shrink-0 text-violet-500" />{config.title}
            <Pill tone={config.configured ? "emerald" : "slate"}>
              {config.configured ? "live" : "simulated"}
            </Pill>
            {!config.enabled && <Pill tone="rose">disabled</Pill>}
          </div>
          <p className="mt-0.5 text-[11.5px] text-faint">{config.description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button onClick={toggle}
            title={config.enabled ? "Disable this action" : "Enable this action"}
            className={cn("rounded-lg px-2 py-1 text-[11px] font-medium transition",
              config.enabled ? "text-muted hover:bg-surface-2" : "text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10")}>
            {config.enabled ? "Disable" : "Enable"}
          </button>
          <button onClick={() => setOpen((o) => !o)}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-violet-600 transition hover:bg-violet-50 dark:text-violet-300 dark:hover:bg-violet-500/10">
            <Icons.chevron className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
            Webhook
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-2 space-y-1.5">
          <input value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder={config.configured ? "Webhook URL is set — paste a new one to replace it" : "https://your-n8n.example.com/webhook/…"}
            className="focus-ring w-full rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 font-mono text-[11.5px] text-fg placeholder:text-faint" />
          <div className="flex items-center gap-1.5">
            <input value={secret} onChange={(e) => setSecret(e.target.value)} type="password"
              placeholder={config.has_secret ? "Signing secret is set — paste to replace" : "Optional signing secret (X-ABA-Signature)"}
              className="focus-ring min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 font-mono text-[11.5px] text-fg placeholder:text-faint" />
            <Button size="sm" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
          {msg && <p className="text-[11px] text-muted">{msg}</p>}
        </div>
      )}
    </div>
  );
}

function ExternalServers({
  servers, setServers,
}: {
  servers: McpServer[];
  setServers: React.Dispatch<React.SetStateAction<McpServer[]>>;
}) {
  const [name, setName] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [auth, setAuth] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [toolsFor, setToolsFor] = React.useState<Record<string, string>>({});

  const add = async () => {
    if (!url.trim() || busy) return;
    setBusy(true); setErr(null);
    try {
      const s = await addMcpServer(name.trim() || "MCP server", url.trim(), auth.trim() || undefined);
      setServers((prev) => [...prev, s]);
      setName(""); setUrl(""); setAuth("");
    } catch { setErr("Could not add the server — check the URL."); }
    setBusy(false);
  };

  const testTools = async (id: string) => {
    setToolsFor((p) => ({ ...p, [id]: "…" }));
    try {
      const tools = await fetchMcpServerTools(id);
      setToolsFor((p) => ({ ...p, [id]: tools.map((t) => t.name).join(", ") || "no tools" }));
    } catch {
      setToolsFor((p) => ({ ...p, [id]: "unreachable" }));
    }
  };

  const remove = async (id: string) => {
    try {
      await removeMcpServer(id);
      setServers((prev) => prev.filter((s) => s.id !== id));
    } catch { /* ignore */ }
  };

  return (
    <div className="mt-3">
      <div className="text-[12px] font-semibold text-fg">External MCP servers (consumed as tools)</div>
      <p className="mt-0.5 text-[11.5px] leading-relaxed text-faint">
        Register an MCP endpoint (e.g. a QuickBooks MCP server) and the agent can call its
        tools. Results are third-party observations — never cited as grounded evidence.
      </p>
      {servers.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {servers.map((s) => (
            <div key={s.id} className="rounded-lg border border-line bg-surface-2/60 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate text-[12px] font-medium text-fg" title={s.url}>
                  {s.name} <span className="font-mono text-[10.5px] text-faint">{s.url}</span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  <button onClick={() => testTools(s.id)}
                    className="rounded-md px-1.5 py-0.5 text-[11px] font-medium text-violet-600 transition hover:bg-violet-50 dark:text-violet-300 dark:hover:bg-violet-500/10">
                    Test
                  </button>
                  <button onClick={() => remove(s.id)} title="Remove"
                    className="rounded-md p-1 text-faint transition hover:text-rose-500">
                    <Icons.x className="h-3 w-3" />
                  </button>
                </span>
              </div>
              {toolsFor[s.id] && (
                <p className="mt-1 font-mono text-[10.5px] text-muted">tools: {toolsFor[s.id]}</p>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 grid gap-1.5 sm:grid-cols-[1fr_2fr]">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name"
          className="focus-ring rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-[11.5px] text-fg placeholder:text-faint" />
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/mcp"
          className="focus-ring rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 font-mono text-[11.5px] text-fg placeholder:text-faint" />
      </div>
      <div className="mt-1.5 flex items-center gap-1.5">
        <input value={auth} onChange={(e) => setAuth(e.target.value)} type="password"
          placeholder="Optional Authorization header (e.g. Bearer …)"
          className="focus-ring min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 font-mono text-[11.5px] text-fg placeholder:text-faint" />
        <Button size="sm" onClick={add} disabled={busy || !url.trim()}>
          <Icons.plus className="h-3.5 w-3.5" />Add
        </Button>
      </div>
      {err && <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-400">{err}</p>}
    </div>
  );
}
