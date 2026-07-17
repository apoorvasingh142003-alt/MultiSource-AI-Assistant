"use client";
import { useEffect, useState } from "react";
import {
  hubspotStatus, hubspotConnect, hubspotSync, hubspotDisconnect,
  type HubSpotImport,
} from "@/lib/api";
import ConnectTile, { ConnectButton, connectInput } from "@/components/ConnectTile";

// Connect HubSpot with a Private App token; imports contacts/companies/deals into this
// tenant's engine as queryable tables.
export default function HubSpotConnect({ open, onToggle }: { open: boolean; onToggle: () => void }) {
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
    <ConnectTile brand="hubspot" connected={connected} open={open} onToggle={onToggle}>
      {connected ? (
        <div className="flex gap-2">
          <button onClick={() => run(hubspotSync)} disabled={busy}
            className="flex-1 rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-orange-400 disabled:opacity-50">
            {busy ? "Syncing…" : "Re-sync"}
          </button>
          <button onClick={disconnect} disabled={busy}
            className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:opacity-50 dark:text-rose-400 dark:hover:bg-rose-500/10">
            Disconnect
          </button>
        </div>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">
            Paste a HubSpot <span className="font-medium text-body">Private App</span> token
            (pat-…) with CRM read scopes.
          </p>
          <input
            value={token} onChange={(e) => setToken(e.target.value)}
            placeholder="pat-na2-…" type="password"
            className={`${connectInput} mb-2`}
          />
          <ConnectButton onClick={() => run(() => hubspotConnect(token.trim()))} disabled={busy || !token.trim()} tone="orange">
            {busy ? "Connecting…" : "Connect HubSpot"}
          </ConnectButton>
        </>
      )}
      {result?.ok && (
        <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">✓ Imported {imported(result)}. Ask about it in chat.</p>
      )}
      {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
    </ConnectTile>
  );
}
