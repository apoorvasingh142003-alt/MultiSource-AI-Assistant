"""Google Drive as a document source (Phase 6 — the last connector on the roadmap).

A user connects Google Drive (incremental OAuth for ``drive.readonly``, handled by the
Next.js layer exactly like Sheets), then either browses their Drive PDFs/Docs or pastes a
file link. We fetch the file with THEIR token — a native PDF is downloaded as-is; a Google
Doc is exported as PDF via the Drive export endpoint — and ingest it through the existing
``engine.add_pdf`` path, so it is chunked, embedded, and citable like any upload, isolated
per tenant.

Outbound HTTP uses the stdlib (no new dependency), mirroring google_sheets.py.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger("aba.drive")

_DRIVE_API = "https://www.googleapis.com/drive/v3/files"
_MAX_BYTES = 30 * 1024 * 1024          # same ceiling as the direct PDF upload endpoint
_LIST_PAGE = 25

_PDF_MIME = "application/pdf"
_GDOC_MIME = "application/vnd.google-apps.document"
_SAFE_NAME = re.compile(r"[^0-9A-Za-z._ -]+")


class DriveError(Exception):
    pass


def parse_file_id(url_or_id: str) -> str:
    """Accept a Drive/Docs URL or a bare file id and return the file id."""
    s = (url_or_id or "").strip()
    m = re.search(r"/(?:file|document)/d/([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", s):
        return s
    raise DriveError("That doesn't look like a Google Drive file link or id.")


def _request(url: str, token: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})


def _get_json(url: str, token: str) -> dict:
    try:
        with urllib.request.urlopen(_request(url, token), timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        _raise_http(exc)
    except DriveError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DriveError(f"Could not reach Google Drive: {exc}")


def _get_bytes(url: str, token: str) -> bytes:
    try:
        with urllib.request.urlopen(_request(url, token), timeout=60) as resp:
            data = resp.read(_MAX_BYTES + 1)
            if len(data) > _MAX_BYTES:
                raise DriveError(f"The file exceeds the {_MAX_BYTES // (1024*1024)} MB limit.")
            return data
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        _raise_http(exc)
    except DriveError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DriveError(f"Could not download the file from Google Drive: {exc}")


def _raise_http(exc) -> None:
    if exc.code in (401, 403):
        raise DriveError(
            "Google denied access. Reconnect Google Drive, and make sure you have "
            "access to the file."
        )
    if exc.code == 404:
        raise DriveError("File not found in Google Drive — check the link.")
    body = exc.read().decode(errors="ignore") if hasattr(exc, "read") else ""
    log.warning("drive HTTP %s: %s", exc.code, body[:200])
    raise DriveError(f"Google Drive API error ({exc.code}).")


# --------------------------------------------------------------------------- #
# Listing (for the picker) + import
# --------------------------------------------------------------------------- #
def list_documents(token: str, query: str = "") -> list[dict]:
    """The user's most recent PDFs and Google Docs (optionally name-filtered)."""
    q = f"(mimeType='{_PDF_MIME}' or mimeType='{_GDOC_MIME}') and trashed=false"
    needle = (query or "").strip().replace("'", "\\'")
    if needle:
        q += f" and name contains '{needle}'"
    params = urllib.parse.urlencode({
        "q": q,
        "orderBy": "modifiedTime desc",
        "pageSize": str(_LIST_PAGE),
        "fields": "files(id,name,mimeType,modifiedTime,size)",
    })
    files = _get_json(f"{_DRIVE_API}?{params}", token).get("files", [])
    return [
        {
            "id": f.get("id", ""),
            "name": f.get("name", ""),
            "kind": "gdoc" if f.get("mimeType") == _GDOC_MIME else "pdf",
            "modified": f.get("modifiedTime", ""),
            "size": int(f["size"]) if str(f.get("size", "")).isdigit() else None,
        }
        for f in files
    ]


def import_file_for_user(user_id: str, token: str, url_or_id: str) -> dict:
    """Fetch a Drive file with the user's token and ingest it into their engine."""
    from app.engine import get_engine

    file_id = parse_file_id(url_or_id)
    meta = _get_json(
        f"{_DRIVE_API}/{file_id}?fields=id,name,mimeType,size", token
    )
    name = meta.get("name") or file_id
    mime = meta.get("mimeType") or ""
    size = int(meta["size"]) if str(meta.get("size", "")).isdigit() else 0
    if size > _MAX_BYTES:
        raise DriveError(f"“{name}” exceeds the {_MAX_BYTES // (1024*1024)} MB limit.")

    if mime == _PDF_MIME:
        data = _get_bytes(f"{_DRIVE_API}/{file_id}?alt=media", token)
    elif mime == _GDOC_MIME:
        # Native Google Doc → export as PDF, then it flows through the same parser.
        data = _get_bytes(
            f"{_DRIVE_API}/{file_id}/export?mimeType={urllib.parse.quote(_PDF_MIME, safe='')}",
            token,
        )
    else:
        raise DriveError(
            "Only PDFs and Google Docs can be imported (got "
            f"'{mime or 'unknown type'}')."
        )
    if not data.startswith(b"%PDF-"):
        raise DriveError(f"“{name}” did not download as a valid PDF.")

    safe = _SAFE_NAME.sub("_", name).strip("._ ") or file_id
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    eng = get_engine(user_id)
    dest_dir = eng.uploads_dir / "pdfs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)
    info = eng.add_pdf(safe, dest)
    return {
        "ok": info.status == "indexed",
        "name": info.name,
        "source": "gdoc" if mime == _GDOC_MIME else "pdf",
        "chunks_indexed": info.chunks_indexed,
        "pages": info.pages,
        "status": info.status,
        "error": info.error,
    }
