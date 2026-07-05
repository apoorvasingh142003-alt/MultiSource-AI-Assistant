"use client";
import { useState } from "react";
import { signIn, useSession } from "next-auth/react";
import { importSheet, type SheetImportResult } from "@/lib/api";

const SHEETS_SCOPE =
  "openid email profile https://www.googleapis.com/auth/spreadsheets.readonly";

// Connect Google Sheets via incremental auth (asks for the Sheets scope only here), then
// import a spreadsheet as a queryable table in this tenant's engine.
export default function SheetsConnect() {
  const { data: session } = useSession();
  const connected = Boolean((session as Record<string, unknown> | null)?.sheetsConnected);
  const [open, setOpen] = useState(false);
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
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium text-emerald-600 hover:text-emerald-700 px-1"
        title="Google Sheets"
      >
        Sheets
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl p-4 text-left">
          <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 mb-1">
            Google Sheets
          </div>
          {!connected ? (
            <>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                Connect Google Sheets to query a spreadsheet as grounded data.
              </p>
              <button onClick={connect}
                className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-2 text-sm font-medium">
                Connect Google Sheets
              </button>
            </>
          ) : (
            <>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                Paste a Google Sheets link. Its first tab becomes a queryable table.
              </p>
              <input
                value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder="https://docs.google.com/spreadsheets/d/…"
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1.5 text-xs mb-2"
              />
              <button onClick={doImport} disabled={busy || !url.trim()}
                className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-2 text-sm font-medium disabled:opacity-50">
                {busy ? "Importing…" : "Import sheet"}
              </button>
              {result?.ok && (
                <p className="mt-2 text-xs text-emerald-600">
                  ✓ Imported “{result.title}” — {result.rows} rows. Ask about it in chat.
                </p>
              )}
              {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
