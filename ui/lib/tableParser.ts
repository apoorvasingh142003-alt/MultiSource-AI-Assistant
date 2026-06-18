/**
 * Parse markdown tables from answer text into structured data.
 * Used by AnswerTable.tsx to render sortable, exportable tables.
 */

export interface ParsedTable {
  headers: string[];
  rows: string[][];
  /** Character offset in source text where the table starts */
  startIndex: number;
  /** Character offset in source text where the table ends */
  endIndex: number;
}

const TABLE_ROW = /^\|(.+)\|$/;
const SEPARATOR = /^\|[\s:|-]+\|$/;

/**
 * Extract all markdown tables from a text block.
 * A table is 2+ rows where each starts/ends with `|` and has a separator row.
 */
export function parseTables(text: string): ParsedTable[] {
  const lines = text.split("\n");
  const tables: ParsedTable[] = [];
  let i = 0;
  let offset = 0;

  while (i < lines.length) {
    const lineStart = offset;
    // Detect a header row
    if (TABLE_ROW.test(lines[i].trim())) {
      const headerLine = lines[i].trim();
      const nextIdx = i + 1;
      // Must have a separator on the next line
      if (nextIdx < lines.length && SEPARATOR.test(lines[nextIdx].trim())) {
        const headers = headerLine
          .slice(1, -1)
          .split("|")
          .map((h) => h.trim());

        // Collect data rows
        const rows: string[][] = [];
        let j = nextIdx + 1;
        while (j < lines.length && TABLE_ROW.test(lines[j].trim())) {
          const cells = lines[j]
            .trim()
            .slice(1, -1)
            .split("|")
            .map((c) => c.trim());
          rows.push(cells);
          j++;
        }

        if (rows.length > 0) {
          // Calculate end offset
          let endOffset = lineStart;
          for (let k = i; k < j; k++) {
            endOffset += lines[k].length + 1; // +1 for newline
          }
          tables.push({
            headers,
            rows,
            startIndex: lineStart,
            endIndex: endOffset,
          });
        }

        // Advance past the table
        for (let k = i; k < j; k++) {
          offset += lines[k].length + 1;
        }
        i = j;
        continue;
      }
    }

    offset += lines[i].length + 1;
    i++;
  }

  return tables;
}

/**
 * Split answer text into segments: text chunks and parsed tables.
 */
export type AnswerSegment =
  | { type: "text"; content: string }
  | { type: "table"; table: ParsedTable };

export function segmentAnswer(text: string): AnswerSegment[] {
  const tables = parseTables(text);
  if (tables.length === 0) return [{ type: "text", content: text }];

  const segments: AnswerSegment[] = [];
  let cursor = 0;

  for (const t of tables) {
    if (t.startIndex > cursor) {
      const before = text.slice(cursor, t.startIndex).trim();
      if (before) segments.push({ type: "text", content: before });
    }
    segments.push({ type: "table", table: t });
    cursor = t.endIndex;
  }

  if (cursor < text.length) {
    const after = text.slice(cursor).trim();
    if (after) segments.push({ type: "text", content: after });
  }

  return segments;
}

/**
 * Export table data as CSV.
 */
export function toCSV(headers: string[], rows: string[][]): string {
  const escape = (s: string) => {
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const lines = [headers.map(escape).join(",")];
  for (const row of rows) {
    lines.push(row.map(escape).join(","));
  }
  return lines.join("\n");
}

/**
 * Export table data as tab-separated text (for clipboard).
 */
export function toTSV(headers: string[], rows: string[][]): string {
  const lines = [headers.join("\t")];
  for (const row of rows) {
    lines.push(row.join("\t"));
  }
  return lines.join("\n");
}
