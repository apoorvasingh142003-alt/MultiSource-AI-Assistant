"use client";
import React from "react";
import type { Inventory } from "@/lib/types";
import { Button, Card, Icons, Pill, cn } from "./ui";

const LANG_LABEL: Record<string, string> = { de: "German", en: "English" };

/* ---------------- upload control ---------------- */
function UploadCard({
  title, accept, hint, multiple, icon, busy, onFiles, lastMessage, lastError,
}: {
  title: string; accept: string; hint: string; multiple?: boolean;
  icon: React.ReactNode; busy: boolean; onFiles: (files: File[]) => void;
  lastMessage?: string | null; lastError?: string | null;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const pick = (list: FileList | null) => { if (list && list.length) onFiles(Array.from(list)); };

  return (
    <div>
      <div
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) pick(e.dataTransfer.files); }}
        className={cn("dropzone flex cursor-pointer flex-col items-center px-4 py-5 text-center",
          over && "is-over", busy && "cursor-wait opacity-80")}
        role="button" aria-disabled={busy}>
        <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-500 ring-1 ring-indigo-100">
          {icon}
        </div>
        <div className="text-[13px] font-semibold text-slate-700">{title}</div>
        <div className="mt-0.5 text-[11.5px] text-slate-400">{hint}</div>
        <input ref={inputRef} type="file" accept={accept} multiple={multiple} className="hidden"
          onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
      </div>
      {busy && <div className="progress-track progress-indeterminate mt-2 h-1.5 w-full" />}
      {!busy && lastError && (
        <p className="mt-2 flex items-start gap-1.5 text-[11.5px] text-rose-600">
          <Icons.alert className="mt-0.5 h-3.5 w-3.5 shrink-0" />{lastError}
        </p>
      )}
      {!busy && !lastError && lastMessage && (
        <p className="mt-2 flex items-start gap-1.5 text-[11.5px] text-emerald-600">
          <Icons.check className="mt-0.5 h-3.5 w-3.5 shrink-0" />{lastMessage}
        </p>
      )}
    </div>
  );
}

function timing(ms: number, origin: string) {
  if (origin === "sample") return "preloaded";
  if (ms >= 1000) return `indexed in ${(ms / 1000).toFixed(1)} s`;
  return `indexed in ${Math.round(ms)} ms`;
}

function DocRow({ d }: { d: Inventory["documents"][number] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-[12.5px] font-medium text-slate-700">
          <Icons.doc className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
          <span className="truncate" title={d.name}>{d.name}</span>
        </span>
        <Pill tone={d.origin === "uploaded" ? "indigo" : "slate"}>{d.origin}</Pill>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {d.status === "error" ? (
          <Pill tone="rose"><Icons.alert className="h-3 w-3" />error</Pill>
        ) : (
          <>
            <Pill tone="emerald"><Icons.check className="h-3 w-3" />indexed</Pill>
            <Pill>{d.chunks_indexed} chunks</Pill>
            {d.pages ? <Pill>{d.pages} pages</Pill> : null}
            {d.languages.map((l) => <Pill key={l}>{LANG_LABEL[l] ?? l}</Pill>)}
          </>
        )}
        <span className="ml-auto text-[10.5px] text-slate-400">{timing(d.ingestion_ms, d.origin)}</span>
      </div>
      {d.error && <p className="mt-1 text-[11px] text-rose-600">{d.error}</p>}
    </div>
  );
}

function DbRow({ d }: { d: Inventory["databases"][number] }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-[12.5px] font-medium text-slate-700">
          <Icons.db className="h-3.5 w-3.5 shrink-0 text-sky-500" />
          <span className="truncate" title={d.name}>{d.name}</span>
        </span>
        <Pill tone={d.origin === "uploaded" ? "indigo" : "slate"}>{d.origin}</Pill>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {d.status === "error" ? (
          <Pill tone="rose"><Icons.alert className="h-3 w-3" />error</Pill>
        ) : (
          <>
            <Pill tone="sky"><Icons.check className="h-3 w-3" />registered</Pill>
            <Pill>{d.tables.length} tables</Pill>
            <Pill>{d.total_rows} rows</Pill>
          </>
        )}
        <span className="ml-auto text-[10.5px] text-slate-400">{timing(d.ingestion_ms, d.origin)}</span>
      </div>
      {d.error && <p className="mt-1 text-[11px] text-rose-600">{d.error}</p>}
      {d.tables.length > 0 && (
        <>
          <button onClick={() => setOpen((o) => !o)}
            className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-700">
            <Icons.chevron className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
            {open ? "Hide" : "Show"} schema
          </button>
          {open && (
            <div className="mt-2 space-y-1.5">
              {d.tables.map((t) => (
                <div key={t.name} className="rounded-lg border border-slate-200 bg-slate-50/60 px-2.5 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 font-mono text-[11.5px] text-slate-700">
                      <Icons.table className="h-3 w-3 text-slate-400" />{t.name}
                    </span>
                    <span className="font-mono text-[10.5px] text-slate-400">{t.rows} rows</span>
                  </div>
                  {t.columns.length > 0 && (
                    <p className="mt-1 font-mono text-[10.5px] leading-relaxed text-slate-500">
                      {t.columns.join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ================= main — sources only ================= */
export default function Workspace({
  inventory, onUploadPdf, onUploadSqlite, onReset,
  pdfBusy, sqliteBusy, resetting, pdfMsg, pdfErr, dbMsg, dbErr,
}: {
  inventory: Inventory | null;
  onUploadPdf: (files: File[]) => void;
  onUploadSqlite: (files: File[]) => void;
  onReset: () => void;
  pdfBusy: boolean; sqliteBusy: boolean; resetting: boolean;
  pdfMsg: string | null; pdfErr: string | null; dbMsg: string | null; dbErr: string | null;
}) {
  const docs = inventory?.documents ?? [];
  const dbs = inventory?.databases ?? [];
  const uploadedDocs = docs.filter((d) => d.origin === "uploaded");
  const uploadedDbs = dbs.filter((d) => d.origin === "uploaded");
  const hasUploads = uploadedDocs.length > 0 || uploadedDbs.length > 0;
  const uploadedChunks = uploadedDocs.reduce((a, d) => a + (d.chunks_indexed || 0), 0);
  const uploadedTables = uploadedDbs.reduce((a, d) => a + d.tables.length, 0);

  const confirmReset = () => {
    if (window.confirm("Clear all uploaded sources and return to the sample data? This cannot be undone.")) onReset();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h2 className="text-[18px] font-bold text-slate-900">Workspace sources</h2>
        <p className="mt-0.5 text-[13px] text-slate-500">
          Upload PDFs and SQLite databases here. Then head to <span className="font-medium text-indigo-600">Chat</span> to
          ask questions grounded in your sources.
        </p>
      </div>

      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
            <Icons.upload className="h-3.5 w-3.5 text-indigo-500" /> Add sources
          </h3>
          {hasUploads && (
            <Button variant="ghost" size="sm" onClick={confirmReset} disabled={resetting}
              title="Remove all uploaded sources and return to the sample data">
              <Icons.refresh className={cn("h-3.5 w-3.5", resetting && "animate-spin")} />Reset workspace
            </Button>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <UploadCard title="Upload PDF documents" accept=".pdf" multiple
            hint="Drag & drop or click — contracts, briefs, reports"
            icon={<Icons.doc className="h-4 w-4" />}
            busy={pdfBusy} onFiles={onUploadPdf} lastMessage={pdfMsg} lastError={pdfErr} />
          <UploadCard title="Upload SQLite database" accept=".db,.sqlite,.sqlite3" multiple
            hint="Drag & drop or click — .db / .sqlite files"
            icon={<Icons.db className="h-4 w-4" />}
            busy={sqliteBusy} onFiles={onUploadSqlite} lastMessage={dbMsg} lastError={dbErr} />
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
            <Icons.layers className="h-3.5 w-3.5 text-indigo-500" /> Your workspace
          </h3>
          {hasUploads && <span className="text-[11px] text-slate-400">{uploadedChunks} chunks · {uploadedTables} tables</span>}
        </div>
        {hasUploads ? (
          <div className="space-y-2">
            {uploadedDocs.map((d) => <DocRow key={d.name} d={d} />)}
            {uploadedDbs.map((d) => <DbRow key={d.name} d={d} />)}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-3 py-5 text-center text-[12px] leading-relaxed text-slate-400">
            Your workspace is empty. Upload a PDF or SQLite database above to ask questions about your own data —
            answers come only from what you add here.
          </div>
        )}
      </Card>
    </div>
  );
}
