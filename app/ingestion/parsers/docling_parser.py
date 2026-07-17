"""Docling PDF parser — robust extraction for messy real-world PDFs (merged/nested tables,
multi-column layout, scans via OCR). Docling emits clean markdown with true table
structure, which we chunk the same way as the basic parser so retrieval/citation are
unchanged.

Docling pulls in torch and layout/OCR models, so it is an OPTIONAL dependency (installed
only when ``INSTALL_ML=true`` / ``pip install -r requirements-ml.txt``). Everything here is
import-guarded: ``docling_available()`` is False when the package isn't installed, and
``get_parser`` falls back to the basic parser. The module never imports torch at app import
time — the heavy import happens lazily inside ``parse``.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.ingestion.parsers.base import (Chunk, IngestedDoc, detect_language,
                                        semantic_chunks)

PARSER_NAME = "docling"

# Markdown heading (Docling emits atx headings) and a markdown table row.
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)")
_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_MD_TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def docling_available() -> bool:
    """True only when the Docling package can be imported (no heavy import performed)."""
    try:
        return importlib.util.find_spec("docling") is not None
    except Exception:
        return False


def _convert(path: Path):
    """Run Docling's converter. Heavy imports are local so importing this module is cheap."""
    from docling.document_converter import DocumentConverter  # noqa: WPS433 (lazy)

    converter = DocumentConverter()
    return converter.convert(str(path))


def _doc_confidence(result) -> float:
    """Best-effort document-level confidence from Docling's confidence report, if present.
    Docling exposes a ``confidence`` grade/score on newer versions; fall back to a high
    default when the extraction succeeded but no score is exposed."""
    try:
        conf = getattr(result, "confidence", None)
        if conf is None:
            return 0.9
        # Newer Docling: a ConfidenceReport with a mean_grade / overall score in [0,1].
        score = getattr(conf, "mean_grade", None)
        if score is None:
            score = getattr(conf, "overall", None) or getattr(conf, "score", None)
        if isinstance(score, (int, float)):
            return round(max(0.0, min(1.0, float(score))), 3)
    except Exception:
        pass
    return 0.9


def _blocks_from_markdown(md: str):
    """Turn Docling markdown into (section, kind, body) blocks. Consecutive table rows are
    kept together as one 'table' block (markdown preserved); headings open sections."""
    blocks: list[tuple[str, str, str]] = []
    section = "Document"
    prose: list[str] = []
    table: list[str] = []

    def flush_prose():
        if prose:
            blocks.append((section, "prose", " ".join(prose).strip()))
            prose.clear()

    def flush_table():
        if table:
            blocks.append((section, "table", "\n".join(table).strip()))
            table.clear()

    for line in md.split("\n"):
        s = line.rstrip()
        if not s.strip():
            flush_table()
            continue
        h = _MD_HEADING.match(s)
        if h:
            flush_prose()
            flush_table()
            section = h.group(1).strip()
            continue
        if _MD_TABLE_ROW.match(s):
            if _MD_TABLE_SEP.match(s):
                table.append(s)  # keep the header separator inside the table block
                continue
            flush_prose()
            table.append(s)
        else:
            flush_table()
            prose.append(s)
    flush_prose()
    flush_table()
    return blocks


def parse(path: Path) -> IngestedDoc:
    result = _convert(path)
    doc = result.document
    md = doc.export_to_markdown()
    conf = _doc_confidence(result)

    document = path.name
    chunks: list[Chunk] = []
    seq = 0
    doc_lang = "en"
    for section, kind, body in _blocks_from_markdown(md):
        if not body:
            continue
        if detect_language(body) == "de":
            doc_lang = "de"
        pieces = [body] if kind == "table" else semantic_chunks(body)
        for piece in pieces:
            seq += 1
            chunks.append(Chunk(
                chunk_id=f"{document}::c{seq}",
                document=document, page=1, section=section,
                language=detect_language(piece), text=piece,
                parse_confidence=conf, parser=PARSER_NAME,
                is_table=(kind == "table"),
            ))
    return IngestedDoc(document=document, language=doc_lang, chunks=chunks,
                       parse_confidence=conf, parser=PARSER_NAME)
