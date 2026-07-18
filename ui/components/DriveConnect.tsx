"use client";
import { useState } from "react";
import { signIn, useSession } from "next-auth/react";
import { driveFiles, driveImport, type DriveFile, type DriveImportResult } from "@/lib/api";
import ConnectTile, { ConnectButton, connectInput } from "@/components/ConnectTile";

const DRIVE_SCOPE =
  "openid email profile https://www.googleapis.com/auth/drive.readonly";

// Connect Google Drive via incremental auth (asks for the drive.readonly scope only
// here; include_granted_scopes keeps any earlier Sheets grant), then import PDFs or
// Google Docs (exported as PDF) into this tenant's engine — chunked, embedded, citable.
export default function DriveConnect({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { data: session } = useSession();
  const connected = Boolean((session as Record<string, unknown> | null)?.driveConnected);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [listBusy, setListBusy] = useState(false);
  const [files, setFiles] = useState<DriveFile[] | null>(null);
  const [result, setResult] = useState<DriveImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function connect() {
    signIn("google", { callbackUrl: typeof window !== "undefined" ? window.location.href : "/" },
      { scope: DRIVE_SCOPE, prompt: "consent", access_type: "offline",
        include_granted_scopes: "true" } as Record<string, string>);
  }

  async function doImport(fileUrlOrId: string) {
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await driveImport(fileUrlOrId.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  async function browse() {
    setListBusy(true); setError(null);
    try {
      setFiles(await driveFiles());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not list Drive files");
    } finally {
      setListBusy(false);
    }
  }

  return (
    <ConnectTile brand="drive" connected={connected} open={open} onToggle={onToggle}>
      {!connected ? (
        <>
          <p className="mb-2.5 text-xs text-muted">
            Connect Google Drive to import PDFs and Google Docs as grounded, citable sources.
          </p>
          <ConnectButton onClick={connect} tone="emerald">Connect Google Drive</ConnectButton>
        </>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">
            Paste a Drive file link (PDF or Google Doc), or browse your recent documents.
          </p>
          <input
            value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://drive.google.com/file/d/… or https://docs.google.com/document/d/…"
            className={`${connectInput} mb-2`}
          />
          <div className="flex gap-1.5">
            <ConnectButton onClick={() => doImport(url)} disabled={busy || !url.trim()} tone="emerald">
              {busy ? "Importing…" : "Import file"}
            </ConnectButton>
            <ConnectButton onClick={browse} disabled={listBusy} tone="sky">
              {listBusy ? "Loading…" : "Browse recent"}
            </ConnectButton>
          </div>
          {files && (
            <div className="mt-2 max-h-44 space-y-1 overflow-y-auto">
              {files.length === 0 && (
                <p className="text-xs text-faint">No PDFs or Google Docs found in your Drive.</p>
              )}
              {files.map((f) => (
                <button key={f.id} onClick={() => doImport(f.id)} disabled={busy}
                  className="flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-surface-2/60 px-2 py-1.5 text-left text-xs text-fg transition hover:border-blue-300 hover:bg-blue-50 disabled:opacity-50 dark:hover:bg-blue-500/10"
                  title={`Import “${f.name}”`}>
                  <span className="min-w-0 truncate">{f.name}</span>
                  <span className="shrink-0 rounded bg-surface px-1 py-0.5 font-mono text-[9.5px] uppercase text-faint ring-1 ring-inset ring-line">
                    {f.kind}
                  </span>
                </button>
              ))}
            </div>
          )}
          {result?.ok && (
            <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
              ✓ Imported “{result.name}” — {result.chunks_indexed} chunk(s)
              {result.pages ? `, ${result.pages} page(s)` : ""}. Ask about it in chat.
            </p>
          )}
          {result && !result.ok && (
            <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">
              {result.error || "Import failed."}
            </p>
          )}
          {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
        </>
      )}
    </ConnectTile>
  );
}
