"use client";
import { useEffect, useState } from "react";
import {
  whatsappStatus, whatsappLink, whatsappUnlink, type WhatsAppLinkInfo,
} from "@/lib/api";

// Connect this account to the shared WhatsApp business number via a one-time code.
export default function WhatsAppConnect() {
  const [open, setOpen] = useState(false);
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
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium text-green-600 hover:text-green-700 px-1"
        title="WhatsApp"
      >
        WhatsApp
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl p-4 text-left">
          <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-1">
            WhatsApp
          </div>
          {linked ? (
            <>
              <p className="text-xs text-emerald-600 mb-3">✓ This account is connected.</p>
              <button onClick={disconnect} disabled={busy}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 disabled:opacity-50">
                Disconnect
              </button>
            </>
          ) : info ? (
            <>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                Open WhatsApp and send this message to the assistant, then ask your questions.
              </p>
              {info.deep_link && (
                <a href={info.deep_link} target="_blank" rel="noreferrer"
                  className="block w-full text-center rounded-lg bg-green-600 hover:bg-green-700 text-white px-3 py-2 text-sm font-medium mb-2">
                  Open WhatsApp
                </a>
              )}
              <p className="text-[11px] text-slate-400">
                Or message {info.business_number || "the business number"}:{" "}
                <code className="font-mono">LINK {info.code}</code><br />
                Expires in {info.expires_in_minutes} min.
              </p>
            </>
          ) : (
            <>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                Chat with the assistant on WhatsApp — grounded in your own data.
              </p>
              <button onClick={generate} disabled={busy}
                className="w-full rounded-lg bg-green-600 hover:bg-green-700 text-white px-3 py-2 text-sm font-medium disabled:opacity-50">
                {busy ? "Generating…" : "Generate link"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
