# Phase 1 — Robust ingestion (Docling) — implementation plan

Status: **shipped** (2026-07-17)
Owner: engineer
Roadmap: [../03-ROADMAP.md](../03-ROADMAP.md) Phase 1 · Backlog: [../04-BACKLOG.md](../04-BACKLOG.md)

## Exit criteria (from the roadmap — what "done" means)

- [x] Docling integrated into `app/ingestion/` **behind the existing ingestion interface**;
      the old pypdf parser stays as a fallback. (Pluggable `app/ingestion/parsers/`.)
- [x] Table-aware chunking; table structure preserved (as markdown) for retrieval.
- [x] Per-document / per-chunk **parse confidence** emitted and threaded into evidence +
      the credibility label.
- [x] Low parse confidence **lowers the answer credibility** — never a silent confident citation.
- [x] A table-heavy / scanned contract yields correct, cited answers; parsing failures
      **degrade gracefully (labelled), never silently**. (Docling verified locally on the
      merged-table PDF: real markdown table, "27%" cell fact retrieved, conf 0.9.)
- [x] Eval set extended with hard PDFs; `scripts/eval.py` Phase-1 block green (offline).
- [x] Offline determinism preserved (tests/eval run with no key and `ABA_PDF_PARSER=basic`).
- [x] The tri-state wall is untouched: parse confidence is a *caveat within* the grounded
      state, it does **not** blend grounded ↔ reasoned (verified: low-conf cited passage →
      answer stays `grounded` + `verification_warning` + visible caveat).

## Design decisions (respecting the locked roadmap)

### 1. Parser abstraction with graceful fallback (the "existing ingestion interface")

`app/ingestion/pdf.py` currently *is* the interface (`ingest_pdf(path) -> IngestedDoc`,
`ingest_pdf_dir`). Rather than break that contract (consumed by `app/engine.py` in three
places), I keep `ingest_pdf` / `ingest_pdf_dir` as the public entrypoints and make them
**dispatch** to a parser chosen at runtime:

- `app/ingestion/parsers/basic.py` — the current pypdf/sidecar logic, refactored out
  verbatim. Always available; the deterministic offline/CI default. Now also **computes a
  parse-confidence signal** (extractable-text ratio, per-page text density, garble ratio)
  and does **table-aware chunk keeping** (pipe/whitespace-column runs are kept together and
  normalised to markdown so a table row isn't shredded across chunks).
- `app/ingestion/parsers/docling_parser.py` — wraps Docling's `DocumentConverter`. Emits
  clean markdown with real tables, and uses Docling's OCR/layout signal for confidence.
  **Import-guarded** exactly like the LangGraph agent path (`docling_available()`), so the
  module never imports torch at app import time.
- `app/ingestion/parsers/__init__.py` — `get_parser()` picks the parser from
  `settings.pdf_parser` (`auto` | `docling` | `basic`). `auto` = Docling when importable,
  else basic. Any Docling failure on a specific file falls back to basic for that file (and
  is recorded), so one bad PDF never takes down ingestion.

New setting: `ABA_PDF_PARSER` (default `auto`). Tests/eval force `basic` (conftest) so the
suite stays hermetic and fast with no torch.

### 2. Confidence data model (additive, backward-compatible)

- `Chunk` gains `parse_confidence: float` (0..1) and `parser: str` (`"basic"|"docling"`),
  plus `is_table: bool`. `IngestedDoc` gains `parse_confidence: float` (min across pages /
  Docling doc score) and `parser`.
- `chunk.as_dict()` carries these through into the `DocumentIndex` chunk store.
- `Evidence` gains `parse_confidence: Optional[float]` and `parser: Optional[str]`; the
  document retriever stamps them from the chunk when building evidence.
- `IngestedDocumentInfo` gains `parse_confidence: Optional[float]` and `parser` for the
  Workspace inventory.

### 3. Threading confidence into credibility — WITHOUT breaking the wall

The tri-state (`grounded|reasoned|insufficient`) is **not** a confidence axis and must not
become one. Parse confidence is a **caveat inside the grounded state**:

- `attach_trust_factors` (app/generation/analysis.py) folds `parse_confidence` into each
  document evidence item's `trust_factors` (new `parse_confidence` field + wording in
  `trust_summary` when low).
- When the *cited* evidence includes a low-confidence parse (below
  `ABA_PARSE_CONFIDENCE_WARN`, default 0.55), the orchestrator sets a
  `verification_warning` ("Some cited passages came from a low-confidence parse (scanned or
  complex layout) — verify against the original.") and nudges `hallucination_risk_score`.
  The answer stays **grounded** (it *is* cited), but the caveat is explicit and visible.
- Total parse failure (no extractable text, Docling+basic both empty) is already handled:
  `add_pdf` returns `status="error"` with a clear message → labelled, never silent.

### 4. UI surface (tokens only, minimal)

- Workspace document row: a parse-confidence pill (emerald ≥0.8 / amber 0.55–0.8 / rose
  <0.55) next to the chunks/pages pills; `parser` shown as a subtle tag.
- Evidence/trust rendering already reads `trust_factors`; add the parse-confidence line.
- `verification_warning` already renders on the answer — no new component needed.

### 5. Hard eval PDFs

`scripts/make_hard_pdfs.py` generates a small `data/eval_pdfs/` set (kept OUT of the seeded
demo corpus so demo counts/routes don't drift):
- `HARD_merged_table.pdf` — a fees/penalties **table** with merged-ish cells + a distinctive
  fact only present in a cell (tests table-aware retrieval + citation).
- `HARD_multicolumn.pdf` — a two-column layout contract clause.
- `HARD_scan.pdf` — a rasterised (image-only) page → no text layer (tests graceful
  degradation / low-confidence labelling; with Docling+OCR it should still parse).

`tests/test_ingestion_docling.py`:
- parser dispatch + fallback (monkeypatch `docling_available`),
- confidence computed and threaded to evidence & inventory,
- table fact retrievable + citable from the merged-table PDF (basic parser),
- scanned/empty PDF degrades to a labelled error (not a silent empty answer),
- low parse confidence propagates a `verification_warning` while staying `grounded`.

`scripts/eval.py`: add a Phase-1 block asserting the hard merged-table PDF yields a cited,
grounded answer for its table-only fact — offline-safe.

## Files touched

- `app/ingestion/pdf.py` — becomes a thin dispatcher (keeps `Chunk`/`IngestedDoc`/
  `detect_language`/`ingest_pdf`/`ingest_pdf_dir` public API).
- `app/ingestion/parsers/{__init__,basic,docling_parser}.py` — new.
- `app/models.py` — `Evidence`, `IngestedDocumentInfo` gain parse-confidence fields.
- `app/retrieval/document_retriever.py` — stamp `parse_confidence`/`parser` onto evidence.
- `app/generation/analysis.py` — parse-confidence in `trust_factors`.
- `app/routing/orchestrator.py` — low-confidence caveat → `verification_warning`/risk.
- `app/engine.py` — inventory rows carry parse confidence; docstrings.
- `app/config.py` — `ABA_PDF_PARSER`, `ABA_PARSE_CONFIDENCE_WARN`.
- `requirements-ml.txt` — add `docling`; `Dockerfile` note (opt-in via INSTALL_ML).
- `ui/lib/types.ts`, `ui/components/Workspace.tsx`, evidence/trust rendering — pills/lines.
- `scripts/make_hard_pdfs.py` (new), `scripts/eval.py`, `tests/test_ingestion_docling.py`,
  `tests/conftest.py` (force `ABA_PDF_PARSER=basic`).

## Verification

- `pytest -q` green (hermetic, basic parser).
- `scripts.eval` green (offline).
- Docling path proven locally: install docling in the /home venv, run the Docling parser
  against a messy PDF, confirm markdown tables + confidence.
- `tsc --noEmit` + `next build` clean (via the /home clone sync per CLAUDE.md).
- Live: bring stack up fresh; /health green; upload a table-heavy PDF at
  https://assistant.lazysnail.xyz/ and confirm a cited answer + the confidence pill.

## Notes / left for next phase

- Docling is heavy (torch). Default Docker image stays lean (`INSTALL_ML=false` → basic
  parser + deterministic confidence). Docling is opt-in for a client box that needs it.
- Full OCR-of-scans is only exercised when Docling is installed; the lean deploy labels a
  no-text scan as a low-confidence/failed parse (graceful, honest).
