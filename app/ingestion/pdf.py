"""PDF ingestion: extract text with real page numbers, detect language, and chunk in a
structure-aware, sentence-respecting way so every chunk carries document/page/section
metadata for citations.

Multilingual: documents are labelled with a detected language (e.g. German ``de`` vs
English ``en``). Retrieval is cross-lingual (the multilingual embedding model + Unicode
BM25 handle German natively), so no per-language text repair is needed — the text is used
as extracted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

_HEADING = re.compile(r"^\s*(\d+)\.\s+\S")

# German signals: umlauts/eszett, or a few high-frequency German function words. Used to
# label documents and to detect the language of a query (so German Q&A is showcased).
_GERMAN_CHARS = re.compile(r"[äöüßÄÖÜ]")
_GERMAN_WORDS = re.compile(
    r"\b(der|die|das|und|oder|für|von|mit|nicht|auf|dem|den|eine|einen|ist|sind|wird|"
    r"werden|vertrag|kunde|kunden|rechnung|zahlung|kündigung|vereinbarung|dienst|"
    r"über|gemäß|sowie)\b",
    re.I,
)


def detect_language(text: str) -> str:
    """Best-effort language label: ``de`` for German, else ``en``. Deliberately light —
    a couple of German function words or any umlaut is enough to tag German content."""
    if not text:
        return "en"
    if _GERMAN_CHARS.search(text):
        return "de"
    if len(_GERMAN_WORDS.findall(text)) >= 2:
        return "de"
    return "en"


@dataclass
class Chunk:
    chunk_id: str
    document: str
    page: int
    section: str
    language: str
    text: str

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "document": self.document, "page": self.page,
            "section": self.section, "language": self.language, "text": self.text,
        }


@dataclass
class IngestedDoc:
    document: str
    language: str
    chunks: list[Chunk] = field(default_factory=list)


# Sentence boundary: end punctuation (Latin or after a clause number) followed by space
# and a capital letter or quote. Keeps clauses and sentences intact across chunk edges.
_SENT_SPLIT = re.compile(r'(?<=[.!?;:])\s+(?=[A-ZÄÖÜ0-9"“(])')

# Enterprise-grade chunking target: large enough for coherent context, with meaningful
# overlap so a fact split across a boundary is still recoverable. Sentence-respecting.
_TARGET_CHARS = 900
_OVERLAP_CHARS = 180


def _hard_window(text: str, size: int, overlap: int) -> list[str]:
    """Character window — only used to break a single pathologically long sentence."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return [c for c in out if c]


def _semantic_chunks(text: str, target: int = _TARGET_CHARS,
                     overlap: int = _OVERLAP_CHARS) -> list[str]:
    """Structure-aware chunking: group whole sentences up to ``target`` chars, carrying a
    trailing ~``overlap`` chars of sentences into the next chunk. Never splits mid-sentence
    (except for a single over-long sentence, which is hard-windowed)."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    units: list[str] = []
    for sentence in _SENT_SPLIT.split(text):
        s = sentence.strip()
        if not s:
            continue
        if len(s) <= int(target * 1.5):
            units.append(s)
        else:
            units.extend(_hard_window(s, target, overlap))

    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for u in units:
        if cur and cur_len + len(u) + 1 > target:
            chunks.append(" ".join(cur).strip())
            # carry trailing sentences (~overlap chars) into the next chunk for continuity
            carry: list[str] = []
            clen = 0
            for prev in reversed(cur):
                if clen + len(prev) > overlap:
                    break
                carry.insert(0, prev)
                clen += len(prev) + 1
            cur = carry
            cur_len = sum(len(x) + 1 for x in cur)
        cur.append(u)
        cur_len += len(u) + 1
    if cur:
        chunks.append(" ".join(cur).strip())
    return [c for c in chunks if c]


def _page_texts(path: Path) -> list[str]:
    """Return the extracted text per page. Prefers a clean ``<name>.txt`` sidecar (a
    pre-extracted text layer) when present, otherwise extracts from the PDF directly."""
    sidecar = path.with_suffix(".txt")
    if sidecar.exists():
        return sidecar.read_text("utf-8").split("\f")
    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def ingest_pdf(path: Path) -> IngestedDoc:
    document = path.name
    chunks: list[Chunk] = []
    current_section = "Preamble"
    seq = 0
    doc_lang = "en"

    for page_index, text in enumerate(_page_texts(path), start=1):
        if detect_language(text) == "de":
            doc_lang = "de"

        # split the page into (section, body) blocks using heading lines
        blocks: list[tuple[str, list[str]]] = [(current_section, [])]
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if _HEADING.match(stripped):
                current_section = re.sub(r"\s+", " ", stripped)
                blocks.append((current_section, []))
            else:
                blocks[-1][1].append(stripped)

        for section, lines in blocks:
            body = " ".join(lines).strip()
            if not body:
                continue
            for piece in _semantic_chunks(body):
                seq += 1
                chunks.append(
                    Chunk(
                        chunk_id=f"{document}::p{page_index}::c{seq}",
                        document=document,
                        page=page_index,
                        section=section,
                        language=detect_language(piece),
                        text=piece,
                    )
                )

    return IngestedDoc(document=document, language=doc_lang, chunks=chunks)


def ingest_pdf_dir(pdf_dir: Path) -> list[IngestedDoc]:
    docs = []
    for p in sorted(pdf_dir.glob("*.pdf")):
        docs.append(ingest_pdf(p))
    return docs
