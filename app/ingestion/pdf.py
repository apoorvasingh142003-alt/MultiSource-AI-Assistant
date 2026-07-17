"""PDF ingestion — the public interface. Extracts text with real page numbers, detects
language, and chunks in a structure-aware, sentence-respecting, table-aware way so every
chunk carries document/page/section metadata (for citations) plus a parse-confidence
signal (so a poor scan never becomes a silent confident citation).

The actual parsing is delegated to a pluggable parser (``app/ingestion/parsers/``):
``basic`` (pypdf, always available, the offline/CI default) or ``docling`` (robust tables /
multi-column / OCR, optional heavy dependency). ``ingest_pdf`` / ``ingest_pdf_dir`` keep the
same signature they always had, so ``app/engine.py`` and the tests are unchanged.
"""
from __future__ import annotations

from pathlib import Path

# Re-exported so existing imports (``from app.ingestion.pdf import Chunk``/``detect_language``)
# keep working after the parser refactor.
from app.ingestion.parsers import parse_pdf
from app.ingestion.parsers.base import Chunk, IngestedDoc, detect_language  # noqa: F401

__all__ = ["Chunk", "IngestedDoc", "detect_language", "ingest_pdf", "ingest_pdf_dir"]


def ingest_pdf(path: Path) -> IngestedDoc:
    return parse_pdf(path)


def ingest_pdf_dir(pdf_dir: Path) -> list[IngestedDoc]:
    return [ingest_pdf(p) for p in sorted(pdf_dir.glob("*.pdf"))]
