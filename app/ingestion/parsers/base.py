"""Shared ingestion toolkit: the chunk/document data model, language detection, the
structure-aware chunker, table detection, and the parse-confidence signal.

Both concrete parsers (``basic`` = pypdf, ``docling`` = Docling) produce the SAME
``IngestedDoc`` shape from here, so the rest of the engine (index, evidence, trace) is
parser-agnostic. Adding a parser is a new ``parse(path) -> IngestedDoc`` — not a pipeline
change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

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
    # Phase 1 (Docling): per-chunk parse quality (0..1) + which parser produced it, and
    # whether this chunk is a (markdown) table. These flow through as_dict() → the index →
    # Evidence, so a low-confidence scan can never masquerade as a confident citation.
    parse_confidence: float = 1.0
    parser: str = "basic"
    is_table: bool = False

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "document": self.document, "page": self.page,
            "section": self.section, "language": self.language, "text": self.text,
            "parse_confidence": self.parse_confidence, "parser": self.parser,
            "is_table": self.is_table,
        }


@dataclass
class IngestedDoc:
    document: str
    language: str
    chunks: list[Chunk] = field(default_factory=list)
    # Document-level parse confidence (min across pages / Docling doc score) + parser used.
    parse_confidence: float = 1.0
    parser: str = "basic"


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


def semantic_chunks(text: str, target: int = _TARGET_CHARS,
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


# --------------------------------------------------------------------------- #
# Parse-confidence signal (deterministic, no ML)                              #
# --------------------------------------------------------------------------- #
# A page whose extracted text is empty, tiny, or dominated by non-word "garble"
# characters (typical of a failed extraction over a scan / complex layout) scores low.
# This is intentionally conservative and offline: it degrades a bad parse into a visible
# caveat rather than a silent confident citation. Docling supplies its own, better signal.

_WORDISH = re.compile(r"[0-9A-Za-zÀ-ÿ]")


def page_confidence(text: str) -> float:
    """0..1 confidence that ``text`` is a clean extraction of a real page.

    Signals combined (min-ish): amount of text, and the fraction of characters that are
    word-like vs punctuation/symbol noise. Empty text → 0.0 (a scan with no text layer)."""
    t = (text or "").strip()
    if not t:
        return 0.0
    n = len(t)
    wordish = len(_WORDISH.findall(t))
    word_ratio = wordish / n if n else 0.0
    # Very short pages are inherently less certain; ramp up to full weight by ~200 chars.
    length_factor = min(1.0, n / 200.0)
    # word_ratio ~0.75+ is clean prose; <0.5 looks like garble/symbols.
    ratio_factor = max(0.0, min(1.0, (word_ratio - 0.35) / 0.4))
    conf = 0.35 + 0.65 * min(length_factor, 0.5 + 0.5 * ratio_factor) * ratio_factor
    # Clean, long prose should land near 1.0; clamp.
    if word_ratio >= 0.7 and n >= 200:
        conf = max(conf, 0.95)
    return round(max(0.0, min(1.0, conf)), 3)


# --------------------------------------------------------------------------- #
# Table awareness (basic parser)                                               #
# --------------------------------------------------------------------------- #
# A table row is detected ONLY by explicit pipe delimiters. Whitespace-column heuristics
# are deliberately avoided here: pypdf-extracted prose is riddled with multi-space gaps
# (from PDF layout), so a whitespace heuristic shreds ordinary paragraphs into fake tables
# and degrades retrieval. Real table structure for messy PDFs comes from the Docling parser
# (which emits proper ``| … |`` markdown); the basic parser only keeps an already-pipe-
# delimited table together. This keeps basic-parser chunks identical to plain prose
# extraction for every non-pipe document (no retrieval regression).
_MULTISPACE = re.compile(r"\s{2,}")


def looks_like_table_row(line: str) -> bool:
    return "|" in line and line.count("|") >= 2


def table_to_markdown(rows: list[str]) -> str:
    """Normalise a run of detected table rows into a simple markdown table so the row
    structure survives chunking and retrieval (a cell fact stays with its header)."""
    parsed: list[list[str]] = []
    for r in rows:
        if "|" in r:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
        else:
            cells = [c.strip() for c in _MULTISPACE.split(r.strip()) if c.strip()]
        if cells:
            parsed.append(cells)
    if not parsed:
        return "\n".join(rows)
    width = max(len(c) for c in parsed)
    parsed = [c + [""] * (width - len(c)) for c in parsed]
    header = parsed[0]
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join(["---"] * width) + " |"]
    for row in parsed[1:]:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)
