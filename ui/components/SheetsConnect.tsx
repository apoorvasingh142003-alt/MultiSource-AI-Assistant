"use client";
import { useState } from "react";
import { signIn, useSession } from "next-auth/react";
import { importSheet, type SheetImportResult } from "@/lib/api";
import ConnectTile, { ConnectButton, connectInput } from "@/components/ConnectTile";

const SHEETS_SCOPE =
  "openid email profile https://www.googleapis.com/auth/spreadsheets.readonly";

// Connect Google Sheets via incremental auth (asks for the Sheets scope only here), then
// import a spreadsheet as a queryable table in this tenant's engine.
export default function SheetsConnect({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { data: session } = useSession();
  const connected = Boolean((session as Record<string, unknown> | null)?.sheetsConnected);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SheetImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function connect() {
    signIn("google", { callbackUrl: typeof window !== "undefined" ? window.location.href : "/" },
      { scope: SHEETS_SCOPE, prompt: "consent", access_type: "offline" } as Record<string, string>);
  }

  async function doImport() {
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await importSheet(url.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConnectTile brand="sheets" connected={connected} open={open} onToggle={onToggle}>
      {!connected ? (
        <>
          <p className="mb-2.5 text-xs text-muted">
            Connect Google Sheets to query a spreadsheet as grounded data.
          </p>
          <ConnectButton onClick={connect} tone="emerald">Connect Google Sheets</ConnectButton>
        </>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">
            Paste a Google Sheets link. Its first tab becomes a queryable table.
          </p>
          <input
            value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://docs.google.com/spreadsheets/d/…"
            className={`${connectInput} mb-2`}
          />
          <ConnectButton onClick={doImport} disabled={busy || !url.trim()} tone="emerald">
            {busy ? "Importing…" : "Import sheet"}
          </ConnectButton>
          {result?.ok && (
            <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
              ✓ Imported “{result.title}” — {result.rows} rows. Ask about it in chat.
            </p>
          )}
          {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
        </>
      )}
    </ConnectTile>
  );
}
