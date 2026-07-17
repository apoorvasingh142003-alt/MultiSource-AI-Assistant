"""Basic PDF parser: pypdf text extraction with real page numbers, structure-aware
sentence-respecting chunking, table-run detection, and a deterministic parse-confidence
signal. Always available (no torch), so it is the offline/CI default and the fallback for
any file Docling can't handle.

Multilingual: documents are labelled with a detected language (German ``de`` vs English
``en``). Retrieval is cross-lingual, so no per-language text repair is needed.
"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from app.ingestion.parsers.base import (Chunk, IngestedDoc, _HEADING, detect_language,
                                        looks_like_table_row, page_confidence,
                                        semantic_chunks, table_to_markdown)

PARSER_NAME = "basic"


def _page_texts(path: Path) -> list[str]:
    """Return the extracted text per page. Prefers a clean ``<name>.txt`` sidecar (a
    pre-extracted text layer) when present, otherwise extracts from the PDF directly."""
    sidecar = path.with_suffix(".txt")
    if sidecar.exists():
        return sidecar.read_text("utf-8").split("\f")
    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def _split_blocks(text: str, current_section: str):
    """Split a page into (section, kind, body) blocks. ``kind`` is 'table' for a detected
    table run (rendered to markdown) and 'prose' otherwise. Headings open a new section."""
    blocks: list[tuple[str, str, str]] = []
    prose: list[str] = []
    table: list[str] = []

    def flush_prose():
        if prose:
            blocks.append((current_section, "prose", " ".join(prose).strip()))
            prose.clear()

    def flush_table():
        if table:
            blocks.append((current_section, "table", table_to_markdown(list(table))))
            table.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            # a blank line closes a table run (paragraph break)
            flush_table()
            continue
        if _HEADING.match(stripped):
            flush_prose()
            flush_table()
            current_section = re.sub(r"\s+", " ", stripped)
            continue
        if looks_like_table_row(stripped):
            flush_prose()
            table.append(stripped)
        else:
            flush_table()
            prose.append(stripped)
    flush_prose()
    flush_table()
    return current_section, blocks


def parse(path: Path) -> IngestedDoc:
    document = path.name
    chunks: list[Chunk] = []
    current_section = "Preamble"
    seq = 0
    doc_lang = "en"
    page_confs: list[float] = []

    for page_index, text in enumerate(_page_texts(path), start=1):
        page_confs.append(page_confidence(text))
        if detect_language(text) == "de":
            doc_lang = "de"

        current_section, blocks = _split_blocks(text, current_section)
        for section, kind, body in blocks:
            if not body:
                continue
            pieces = [body] if kind == "table" else semantic_chunks(body)
            for piece in pieces:
                seq += 1
                chunks.append(Chunk(
                    chunk_id=f"{document}::p{page_index}::c{seq}",
                    document=document, page=page_index, section=section,
                    language=detect_language(piece), text=piece,
                    parse_confidence=page_confs[-1], parser=PARSER_NAME,
                    is_table=(kind == "table"),
                ))

    doc_conf = round(min(page_confs), 3) if page_confs else 1.0
    return IngestedDoc(document=document, language=doc_lang, chunks=chunks,
                       parse_confidence=doc_conf, parser=PARSER_NAME)
