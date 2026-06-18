"use client";
import React from "react";
import type { ParsedTable } from "@/lib/tableParser";
import { toCSV, toTSV } from "@/lib/tableParser";
import { Button, Icons, cn } from "./ui";

const ROWS_PER_PAGE = 10;

type SortDir = "asc" | "desc" | null;

export default function AnswerTable({ table }: { table: ParsedTable }) {
  const { headers, rows } = table;
  const [sortCol, setSortCol] = React.useState<number | null>(null);
  const [sortDir, setSortDir] = React.useState<SortDir>(null);
  const [page, setPage] = React.useState(0);
  const [copied, setCopied] = React.useState(false);

  // Sort
  const sorted = React.useMemo(() => {
    if (sortCol == null || sortDir == null) return rows;
    return [...rows].sort((a, b) => {
      const va = a[sortCol] ?? "";
      const vb = b[sortCol] ?? "";
      // Try numeric comparison
      const na = parseFloat(va);
      const nb = parseFloat(vb);
      if (!isNaN(na) && !isNaN(nb)) {
        return sortDir === "asc" ? na - nb : nb - na;
      }
      return sortDir === "asc"
        ? va.localeCompare(vb)
        : vb.localeCompare(va);
    });
  }, [rows, sortCol, sortDir]);

  // Paginate
  const totalPages = Math.ceil(sorted.length / ROWS_PER_PAGE);
  const pagedRows = sorted.slice(
    page * ROWS_PER_PAGE,
    (page + 1) * ROWS_PER_PAGE
  );

  const toggleSort = (col: number) => {
    if (sortCol === col) {
      if (sortDir === "asc") setSortDir("desc");
      else if (sortDir === "desc") {
        setSortCol(null);
        setSortDir(null);
      }
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
    setPage(0);
  };

  const exportCSV = () => {
    const csv = toCSV(headers, rows);
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "table-export.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyTable = async () => {
    const tsv = toTSV(headers, rows);
    await navigator.clipboard.writeText(tsv);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Determine if first column should have timeline accent
  const isTimeline =
    headers.length > 0 &&
    /date|time|period|year|month|when/i.test(headers[0]);

  return (
    <div className="my-3 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Controls */}
      <div className="flex items-center justify-end gap-2 border-b border-slate-100 px-3 py-2">
        <Button variant="ghost" size="sm" onClick={exportCSV}>
          <Icons.doc className="h-3.5 w-3.5" />Export CSV
        </Button>
        <Button variant="ghost" size="sm" onClick={copyTable}>
          <Icons.layers className="h-3.5 w-3.5" />
          {copied ? "Copied!" : "Copy Table"}
        </Button>
      </div>

      {/* Table */}
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full text-left text-[12.5px]">
          <thead>
            <tr className="bg-indigo-50/60">
              {headers.map((h, i) => (
                <th
                  key={i}
                  onClick={() => toggleSort(i)}
                  className="cursor-pointer select-none whitespace-nowrap px-3 py-2.5 font-semibold text-slate-700 transition hover:bg-indigo-100/50"
                >
                  <span className="inline-flex items-center gap-1">
                    {h}
                    {sortCol === i && sortDir === "asc" && (
                      <span className="text-indigo-500">↑</span>
                    )}
                    {sortCol === i && sortDir === "desc" && (
                      <span className="text-indigo-500">↓</span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map((row, ri) => (
              <tr
                key={ri}
                className={cn(
                  "border-t border-slate-100 transition hover:bg-slate-50",
                  ri % 2 === 1 && "bg-slate-50/40"
                )}
              >
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className={cn(
                      "px-3 py-2 text-slate-600",
                      isTimeline &&
                        ci === 0 &&
                        "border-l-[3px] border-l-indigo-400 font-semibold text-slate-800"
                    )}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2">
          <span className="text-[11px] text-slate-400">
            Page {page + 1} of {totalPages} · {rows.length} rows
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              ← Prev
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setPage((p) => Math.min(totalPages - 1, p + 1))
              }
              disabled={page >= totalPages - 1}
            >
              Next →
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
