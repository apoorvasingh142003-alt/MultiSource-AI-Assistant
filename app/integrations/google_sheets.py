"""Google Sheets as a grounded data source.

A user connects Google Sheets (incremental OAuth for spreadsheets.readonly, handled by the
Next.js layer), then points the assistant at a spreadsheet. We read the values with their
token, materialise them as a SQLite table, and merge that into the tenant's working DB via
the existing engine.add_database path — so the sheet is immediately queryable through the
same SQL/hybrid routing (and isolated per user like every other upload).

Outbound HTTP uses the stdlib so the backend gains no dependency.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import urllib.parse
import urllib.request

log = logging.getLogger("aba.sheets")

_SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(Exception):
    pass


def parse_spreadsheet_id(url_or_id: str) -> str:
    """Accept a full Sheets URL or a bare id and return the spreadsheet id."""
    s = (url_or_id or "").strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", s):
        return s
    raise SheetsError("That doesn't look like a Google Sheets link or id.")


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        body = exc.read().decode(errors="ignore") if hasattr(exc, "read") else ""
        if exc.code in (401, 403):
            raise SheetsError(
                "Google denied access to that sheet. Reconnect Google Sheets, and make sure "
                "you have access to the spreadsheet."
            )
        if exc.code == 404:
            raise SheetsError("Spreadsheet not found — check the link.")
        log.warning("sheets HTTP %s: %s", exc.code, body[:200])
        raise SheetsError("Could not read the spreadsheet from Google.")
    except Exception as exc:  # noqa: BLE001
        raise SheetsError(f"Could not reach Google Sheets: {exc}")


def read_sheet(token: str, spreadsheet_id: str) -> tuple[str, list[str], list[list[str]]]:
    """Return (title, header_row, data_rows) for the first tab of a spreadsheet."""
    meta = _get(f"{_SHEETS_API}/{spreadsheet_id}?fields=properties.title,sheets.properties.title", token)
    title = (meta.get("properties") or {}).get("title") or "sheet"
    sheets = meta.get("sheets") or []
    if not sheets:
        raise SheetsError("That spreadsheet has no tabs.")
    first = (sheets[0].get("properties") or {}).get("title") or "Sheet1"
    rng = urllib.parse.quote(first)
    values = _get(f"{_SHEETS_API}/{spreadsheet_id}/values/{rng}", token).get("values", [])
    if not values:
        raise SheetsError("That sheet is empty.")
    header = [str(c) for c in values[0]]
    data = [[str(c) for c in row] for row in values[1:]]
    return title, header, data


# --- materialise into SQLite --------------------------------------------------
def _safe_ident(name: str, fallback: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", (name or "").strip()) or fallback
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident[:63]


def build_sqlite(path, table_name: str, header: list[str], data: list[list[str]]) -> str:
    """Write the rows into a fresh SQLite file with one all-TEXT table. Returns the table name."""
    table = _safe_ident(table_name, "sheet")
    seen: dict[str, int] = {}
    cols: list[str] = []
    for i, h in enumerate(header):
        c = _safe_ident(h, f"col{i+1}")
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        else:
            seen[c] = 0
        cols.append(c)

    conn = sqlite3.connect(str(path))
    try:
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        conn.execute(f'CREATE TABLE "{table}" ({col_defs})')
        placeholders = ", ".join("?" for _ in cols)
        for row in data:
            padded = (row + [""] * len(cols))[:len(cols)]
            conn.execute(f'INSERT INTO "{table}" VALUES ({placeholders})', padded)
        conn.commit()
    finally:
        conn.close()
    return table


def import_sheet_for_user(user_id: str, token: str, url_or_id: str) -> dict:
    """Read a sheet with the user's token and register it in their isolated engine."""
    from app.engine import get_engine

    spreadsheet_id = parse_spreadsheet_id(url_or_id)
    title, header, data = read_sheet(token, spreadsheet_id)

    eng = get_engine(user_id)
    eng.uploads_dir.mkdir(parents=True, exist_ok=True)
    db_name = _safe_ident(f"gsheet_{title}", "gsheet")
    db_path = eng.uploads_dir / f"{db_name}.db"
    table = build_sqlite(db_path, title, header, data)

    info = eng.add_database(f"{title} (Google Sheet)", db_path)
    return {
        "ok": info.status == "indexed",
        "title": title,
        "table": table,
        "rows": len(data),
        "columns": header,
        "status": info.status,
        "error": getattr(info, "error", None),
    }
