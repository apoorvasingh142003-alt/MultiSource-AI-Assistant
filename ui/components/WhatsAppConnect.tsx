"use client";
import { useEffect, useState } from "react";
import {
  whatsappStatus, whatsappLink, whatsappUnlink, type WhatsAppLinkInfo,
} from "@/lib/api";
import ConnectTile, { ConnectButton } from "@/components/ConnectTile";

// Connect this account to the shared WhatsApp business number via a one-time code.
export default function WhatsAppConnect({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [linked, setLinked] = useState<boolean | null>(null);
  const [info, setInfo] = useState<WhatsAppLinkInfo | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open && linked === null) {
      whatsappStatus().then((s) => setLinked(s.linked)).catch(() => setLinked(false));
    }
  }, [open, linked]);

  async function generate() {
    setBusy(true);
    try { setInfo(await whatsappLink()); } catch { /* ignore */ } finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true);
    try { await whatsappUnlink(); setLinked(false); setInfo(null); } finally { setBusy(false); }
  }

  return (
    <ConnectTile brand="whatsapp" connected={linked} open={open} onToggle={onToggle}>
      {linked ? (
        <button onClick={disconnect} disabled={busy}
          className="w-full rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:opacity-50 dark:text-rose-400 dark:hover:bg-rose-500/10">
          Disconnect
        </button>
      ) : info ? (
        <>
          <p className="mb-2 text-xs text-muted">
            Open WhatsApp and send this message to the assistant, then ask your questions.
          </p>
          {info.deep_link && (
            <a href={info.deep_link} target="_blank" rel="noreferrer"
              className="mb-2 block w-full rounded-lg bg-green-600 px-3 py-2 text-center text-sm font-semibold text-white transition hover:bg-green-500">
              Open WhatsApp
            </a>
          )}
          <p className="text-[11px] text-faint">
            Or message {info.business_number || "the business number"}:{" "}
            <code className="rounded bg-surface px-1 font-mono text-fg">LINK {info.code}</code><br />
            Expires in {info.expires_in_minutes} min.
          </p>
        </>
      ) : (
        <>
          <p className="mb-2.5 text-xs text-muted">
            Chat with the assistant on WhatsApp — grounded in your own data.
          </p>
          <ConnectButton onClick={generate} disabled={busy} tone="green">
            {busy ? "Generating…" : "Generate link"}
          </ConnectButton>
        </>
      )}
    </ConnectTile>
  );
}
