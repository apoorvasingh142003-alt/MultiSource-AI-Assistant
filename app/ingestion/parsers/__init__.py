"""Parser selection — pick the PDF parser at runtime, with graceful fallback.

``ABA_PDF_PARSER`` (settings.pdf_parser):
    auto     — Docling when it's importable, else the basic pypdf parser (default).
    docling  — force Docling (falls back to basic if unavailable / on per-file failure).
    basic    — force the deterministic pypdf parser (offline/CI default; hermetic tests).

Both parsers return the same ``IngestedDoc`` shape (see base.py), so the engine is
parser-agnostic. A Docling failure on a specific file transparently falls back to the basic
parser for that file — one bad PDF never breaks ingestion.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.config import get_settings
from app.ingestion.parsers import basic
from app.ingestion.parsers.base import Chunk, IngestedDoc, detect_language  # re-export
from app.ingestion.parsers.docling_parser import docling_available

log = logging.getLogger("aba.ingestion")

__all__ = ["Chunk", "IngestedDoc", "detect_language", "parse_pdf",
           "active_parser_name", "docling_available"]


def active_parser_name() -> str:
    """Which parser ``auto`` resolves to right now (for /config + inventory labelling)."""
    mode = (get_settings().pdf_parser or "auto").lower()
    if mode == "basic":
        return "basic"
    if mode == "docling":
        return "docling" if docling_available() else "basic"
    return "docling" if docling_available() else "basic"


def parse_pdf(path: Path) -> IngestedDoc:
    """Parse one PDF with the configured parser, falling back to basic on any failure."""
    parser = active_parser_name()
    if parser == "docling":
        try:
            from app.ingestion.parsers import docling_parser
            return docling_parser.parse(path)
        except Exception:  # torch/model/parse failure → never lose the document
            log.warning("Docling parse failed for %s — falling back to basic parser",
                        path.name, exc_info=True)
    return basic.parse(path)
