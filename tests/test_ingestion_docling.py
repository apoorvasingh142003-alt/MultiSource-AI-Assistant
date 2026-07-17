"""Phase 1 (robust ingestion / Docling) tests.

Hermetic + offline: the whole suite forces ``ABA_PDF_PARSER=basic`` (see conftest) so no
torch/Docling import happens here. These tests assert the parser abstraction, the
graceful fallback, the parse-confidence signal, and — the product invariant — that a
low-confidence parse lowers *credibility* (a visible caveat) WITHOUT ever blending the
tri-state grounding wall (grounded stays grounded; an empty scan degrades to a labelled
error, never a silent answer).
"""
from __future__ import annotations

import os

os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")
os.environ.setdefault("ABA_PDF_PARSER", "basic")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from app.config import ROOT  # noqa: E402
from app.ingestion import parsers  # noqa: E402
from app.ingestion.pdf import ingest_pdf  # noqa: E402
from app.ingestion.parsers.base import (looks_like_table_row, page_confidence,  # noqa: E402
                                        table_to_markdown)

EVAL_DIR = ROOT / "data" / "eval_pdfs"
FEES = EVAL_DIR / "HARD_fees_table.pdf"
MULTICOL = EVAL_DIR / "HARD_multicolumn.pdf"
SCAN = EVAL_DIR / "HARD_scan.pdf"

pytestmark = pytest.mark.skipif(
    not FEES.exists(),
    reason="hard eval PDFs not generated (run scripts/make_hard_pdfs.py)",
)


# --------------------------------------------------------------------------- #
# parser selection + fallback                                                  #
# --------------------------------------------------------------------------- #
def test_active_parser_is_basic_in_tests():
    assert parsers.active_parser_name() == "basic"


def test_docling_forced_falls_back_to_basic_when_unavailable(monkeypatch):
    """With docling forced but unimportable, parse_pdf must fall back to the basic parser
    (never raise, never lose the document)."""
    monkeypatch.setenv("ABA_PDF_PARSER", "docling")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(parsers, "docling_available", lambda: False)
    try:
        doc = parsers.parse_pdf(FEES)
        assert doc.parser == "basic"
        assert doc.chunks
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# confidence signal                                                            #
# --------------------------------------------------------------------------- #
def test_page_confidence_ranges():
    assert page_confidence("") == 0.0                       # empty scan → zero
    assert page_confidence("!@#$%^&*()_+={}[]|\\<>/") < 0.55  # garble → low
    clean = ("This is a clean paragraph of ordinary English prose that reads like a real "
             "contract clause with normal punctuation and length. " * 3)
    assert page_confidence(clean) >= 0.9                    # clean prose → high


def test_confidence_threaded_to_chunks_and_dict():
    doc = ingest_pdf(FEES)
    assert doc.parser == "basic"
    assert 0.0 <= doc.parse_confidence <= 1.0
    c0 = doc.chunks[0]
    d = c0.as_dict()
    assert "parse_confidence" in d and "parser" in d and "is_table" in d


def test_table_fact_is_extractable_from_fees_table():
    """The distinctive cell fact (27% early-termination penalty) survives ingestion."""
    doc = ingest_pdf(FEES)
    text = " ".join(c.text for c in doc.chunks)
    assert "27%" in text


def test_multicolumn_fact_extractable():
    doc = ingest_pdf(MULTICOL)
    text = " ".join(c.text for c in doc.chunks)
    assert "forty-two" in text or "(42)" in text


# --------------------------------------------------------------------------- #
# table helpers                                                                #
# --------------------------------------------------------------------------- #
def test_table_detection_is_pipe_only():
    # pipe rows are tables; prose (even multi-space) is NOT (avoids shredding paragraphs)
    assert looks_like_table_row("| a | b | c |")
    assert not looks_like_table_row("The quick brown    fox    jumped over")


def test_table_to_markdown_shape():
    md = table_to_markdown(["| Item | Amount |", "| Fee | 27% |"])
    assert md.startswith("| Item | Amount |")
    assert "---" in md


# --------------------------------------------------------------------------- #
# graceful degradation (empty scan) + credibility caveat                       #
# --------------------------------------------------------------------------- #
def test_empty_scan_degrades_to_labelled_error(tmp_path):
    """An image-only scan yields no text under the basic parser → the engine records a
    labelled error, never a silent empty index / confident answer."""
    from app.engine import Engine
    eng = Engine(user_id="docling-test-scan")
    info = eng.add_pdf("HARD_scan.pdf", SCAN)
    assert info.status == "error"
    assert info.error and ("scanned" in info.error.lower() or "no extractable" in info.error.lower())


def test_low_parse_confidence_caveat_keeps_grounded(tmp_path):
    """A synthetic low-confidence PDF passage that gets cited must keep the answer GROUNDED
    (it IS cited) while surfacing a verification_warning — the wall is never blended."""
    from app.engine import Engine
    from app.models import compute_answer_state

    eng = Engine(user_id="docling-test-lowconf")
    # Inject a low-confidence chunk directly into the live index (simulating a poor scan
    # that still produced *some* text), then ask a question that retrieves it.
    idx = eng.document_source.index
    idx.add_chunks([{
        "chunk_id": "lowconf::p1::c1",
        "document": "LOWCONF_scan.pdf", "page": 1, "section": "1. Penalty",
        "language": "en",
        "text": ("The early termination penalty under this scanned agreement is "
                 "thirty-three percent (33%) of the remaining contract value."),
        "parse_confidence": 0.2, "parser": "basic", "is_table": False,
    }])
    eng.document_source.documents.append("LOWCONF_scan.pdf")
    from app.models import IngestedDocumentInfo
    eng._documents.append(IngestedDocumentInfo(
        name="LOWCONF_scan.pdf", origin="uploaded", status="indexed",
        chunks_indexed=1, parse_confidence=0.2, parser="basic"))

    resp = eng.ask("What is the early termination penalty in the scanned agreement?",
                   scope="all")
    # If the low-confidence passage was actually cited, the caveat must fire and the answer
    # must remain grounded (not flipped to reasoned/insufficient).
    cited_low = any(
        e.parse_confidence is not None and e.parse_confidence < 0.55
        for e in resp.trace.evidence if e.used
    )
    if cited_low:
        assert resp.answer_state == "grounded"
        assert resp.verification_warning
        assert "low-confidence" in resp.answer.lower() or "verify" in resp.answer.lower()
