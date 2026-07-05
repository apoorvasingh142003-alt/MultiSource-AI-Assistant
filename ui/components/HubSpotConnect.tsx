"use client";
import { useEffect, useState } from "react";
import {
  hubspotStatus, hubspotConnect, hubspotSync, hubspotDisconnect,
  type HubSpotImport,
} from "@/lib/api";

// Connect HubSpot with a Private App token; imports contacts/companies/deals into this
// tenant's engine as queryable tables. Isolated so it needs no page.tsx changes.
export default function HubSpotConnect() {
  const [open, setOpen] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<HubSpotImport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && connected === null) {
      hubspotStatus().then((s) => setConnected(s.connected)).catch(() => setConnected(false));
    }
  }, [open, connected]);

  async function run(fn: () => Promise<HubSpotImport>) {
    setBusy(true); setError(null); setResult(null);
    try { setResult(await fn()); setConnected(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true);
    try { await hubspotDisconnect(); setConnected(false); setResult(null); } finally { setBusy(false); }
  }

  const imported = (r: HubSpotImport) =>
    Object.entries(r.imported).map(([k, v]) => `${v} ${k}`).join(", ");

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium text-orange-600 hover:text-orange-700 px-1"
        title="HubSpot CRM"
      >
        HubSpot
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl p-4 text-left">
          <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-1">
            HubSpot CRM
          </div>
          {connected ? (
            <>
              <p className="text-xs text-emerald-600 mb-2">✓ Connected.</p>
              <div className="flex gap-2">
                <button onClick={() => run(hubspotSync)} disabled={busy}
                  className="flex-1 rounded-lg bg-orange-600 hover:bg-orange-700 text-white px-3 py-1.5 text-xs disabled:opacity-50">
                  {busy ? "Syncing…" : "Re-sync"}
                </button>
                <button onClick={disconnect} disabled={busy}
                  className="rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 disabled:opacity-50">
                  Disconnect
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                Paste a HubSpot <span className="font-medium">Private App</span> token
                (pat-…) with CRM read scopes.
              </p>
              <input
                value={token} onChange={(e) => setToken(e.target.value)}
                placeholder="pat-na2-…" type="password"
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1.5 text-xs mb-2"
              />
              <button onClick={() => run(() => hubspotConnect(token.trim()))} disabled={busy || !token.trim()}
                className="w-full rounded-lg bg-orange-600 hover:bg-orange-700 text-white px-3 py-2 text-sm font-medium disabled:opacity-50">
                {busy ? "Connecting…" : "Connect HubSpot"}
              </button>
            </>
          )}
          {result?.ok && (
            <p className="mt-2 text-xs text-emerald-600">✓ Imported {imported(result)}. Ask about it in chat.</p>
          )}
          {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
        </div>
      )}
    </div>
  );
}
