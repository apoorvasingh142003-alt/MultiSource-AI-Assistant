"use client";
import { useEffect, useState } from "react";
import {
  telegramStatus, telegramLink, telegramUnlink, type TelegramLinkInfo,
} from "@/lib/api";
import ConnectTile, { ConnectButton } from "@/components/ConnectTile";

// Connect this account to the shared Telegram bot via a one-time deep link, or disconnect.
export default function TelegramConnect({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [linked, setLinked] = useState<boolean | null>(null);
  const [info, setInfo] = useState<TelegramLinkInfo | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open && linked === null) {
      telegramStatus().then((s) => setLinked(s.linked)).catch(() => setLinked(false));
    }
  }, [open, linked]);

  async function generate() {
    setBusy(true);
    try { setInfo(await telegramLink()); } catch { /* ignore */ } finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true);
    try { await telegramUnlink(); setLinked(false); setInfo(null); } finally { setBusy(false); }
  }

  return (
    <ConnectTile brand="telegram" connected={linked} open={open} onToggle={onToggle}>
      {linked ? (
        <button onClick={disconnect} disabled={busy}
          className="w-full rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:opacity-50 dark:text-rose-400 dark:hover:bg-rose-500/10">
          Disconnect
        </button>
      ) : info ? (
        <>
          <p className="mb-2 text-xs text-muted">
            Open this link in Telegram and press Start — then message the bot your questions.
          </p>
          {info.deep_link && (
            <a href={info.deep_link} target="_blank" rel="noreferrer"
              className="mb-2 block w-full rounded-lg bg-sky-600 px-3 py-2 text-center text-sm font-semibold text-white transition hover:bg-sky-500">
              Open @{info.bot_username} in Telegram
            </a>
          )}
          <p className="text-[11px] text-faint">
            Or DM the bot: <code className="rounded bg-surface px-1 font-mono text-fg">/start {info.code}</code>
            <br />Expires in {info.expires_in_minutes} min.
          </p>
        </>
      ) : (
        <>
          <p className="mb-2.5 text-xs text-muted">
            Chat with the assistant on Telegram — answers stay grounded in your own data.
          </p>
          <ConnectButton onClick={generate} disabled={busy} tone="sky">
            {busy ? "Generating…" : "Generate link"}
          </ConnectButton>
        </>
      )}
    </ConnectTile>
  );
}
