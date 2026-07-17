"""Tiny retrieval/routing eval + smoke test.

Runs every scripted demo question through the full engine and checks:
- the route matches the expected route,
- answerable questions retrieve evidence and pass citation verification,
- the out-of-scope question is correctly flagged 'insufficient'.

Works fully offline (deterministic fallbacks). With ANTHROPIC_API_KEY set, it
exercises the live Claude path instead.
"""
from __future__ import annotations

import sys

from app.engine import get_engine


def main() -> int:
    eng = get_engine()
    cfg_mode = "live" if eng.settings.use_live_llm else "offline"
    print(f"\nMode: {cfg_mode} | embeddings: {eng.document_source.index.embedder.backend} | "
          f"vector: {eng.document_source.index.store.backend}\n")
    print(f"{'expect':>7} {'got':>7}  ok   ev  cite  question")
    print("-" * 100)

    passed = 0
    for ex in eng.examples:
        resp = eng.ask(ex.question)
        route = resp.trace.route.route if resp.trace.route else "?"
        route_ok = route == ex.route
        ev = len(resp.trace.evidence)
        cited = resp.trace.citation_check.verified if resp.trace.citation_check else False

        if ex.route == "NONE":
            # The tri-state wall: an unanswerable question must land on the honest decline.
            ok = route_ok and resp.insufficient and resp.answer_state == "insufficient"
        else:
            # An answerable question must be grounded+cited — never silently "reasoned".
            ok = (route_ok and ev > 0 and cited and not resp.insufficient
                  and resp.answer_state == "grounded")
        passed += ok
        flag = "✓" if ok else "✗"
        print(f"{ex.route:>7} {route:>7}  {flag:>2}  {ev:>3}  {str(cited):>5}  {ex.question[:64]}")

    total = len(eng.examples)

    # Keyword-precision regression: a "which document mentions <exact id>" lookup must
    # return ONLY passages from the document that literally contains the id — never
    # semantically-similar-but-irrelevant chunks from other documents.
    probe = "Which document mentions INI-MSA-2024?"
    resp = eng.ask(probe)
    docs = {e.document for e in resp.trace.evidence}
    intent = resp.trace.document_retrieval.intent if resp.trace.document_retrieval else "?"
    precise = bool(resp.trace.evidence) and docs == {"INITECH_Agreement.pdf"}
    passed += precise
    total += 1
    print(f"{'PDF':>7} {resp.trace.route.route:>7}  {'✓' if precise else '✗':>2}  "
          f"{len(resp.trace.evidence):>3}  {intent:>5}  {probe[:64]}")

    # Grounding-first regression: even if the router is forced to GENERAL_KNOWLEDGE for a
    # document-answerable question, the engine must still ground in the document (the safety
    # net recovers it) and never emit an ungrounded parametric answer. Reproduces the
    # nursing-home incident in miniature against the seeded contract corpus.
    import app.routing.orchestrator as _orch
    from app.models import LLMCall, RouteDecision

    _real_classify = _orch.classify
    _orch.classify = lambda *a, **k: (
        RouteDecision(route="GENERAL_KNOWLEDGE", reasoning="forced GK (eval probe)",
                      confidence=0.4, languages=["en"], document_subquery="",
                      sql_subquery="", entity_hint="", agentic=False, strategy_note=""),
        LLMCall(purpose="routing", model="probe", mode="stub"),
    )
    try:
        gprobe = "What do our contracts say about suspension?"
        gresp = eng.ask(gprobe)
        # The safety net must recover a GROUNDED, cited answer — the tri-state label must
        # NOT flip to "reasoned" just because the router was (wrongly) forced to GK.
        grounded = (bool(gresp.trace.evidence) and not gresp.insufficient
                    and "not grounded" not in gresp.answer.lower()
                    and gresp.answer_state == "grounded")
    finally:
        _orch.classify = _real_classify
    passed += grounded
    total += 1
    print(f"{'PDF':>7} {'GK→doc':>7}  {'✓' if grounded else '✗':>2}  "
          f"{len(gresp.trace.evidence):>3}  {'grnd':>5}  {('[grounding-first] ' + gprobe)[:64]}")

    # Phase 1 (Docling) — robust ingestion regression. Uploads a table-heavy PDF and a
    # multi-column PDF (basic parser, offline) and asserts the distinctive fact that lives
    # in a TABLE CELL / a two-column flow is still retrieved + citable. Skipped when the
    # hard eval corpus hasn't been generated (scripts/make_hard_pdfs.py).
    from pathlib import Path as _Path
    eval_dir = eng.settings.data_path / "eval_pdfs"
    hard_cases = [
        ("HARD_fees_table.pdf", "What is the early termination penalty?", "27%"),
        ("HARD_multicolumn.pdf", "What is the cure period for a material breach?", "42"),
    ]
    for fname, q, needle in hard_cases:
        fpath = eval_dir / fname
        if not fpath.exists():
            continue
        from app.engine import Engine as _Engine
        probe_eng = _Engine(user_id=f"eval-hard-{fname}")
        info = probe_eng.add_pdf(fname, fpath)
        # Scope to the workspace (the uploaded doc only) — the realistic client flow, and it
        # isolates the hard PDF from the seed corpus under weak offline hashing embeddings.
        hresp = probe_eng.ask(q, scope="workspace")
        text = " ".join(e.content for e in hresp.trace.evidence)
        ok = (info.status == "indexed" and needle in text
              and not hresp.insufficient and hresp.answer_state == "grounded")
        passed += ok
        total += 1
        print(f"{'PDF':>7} {'hard':>7}  {'✓' if ok else '✗':>2}  "
              f"{len(hresp.trace.evidence):>3}  {('conf%.0f%%' % ((info.parse_confidence or 0)*100)):>5}  "
              f"{(fname + ': ' + q)[:64]}")

    print("-" * 100)
    print(f"{passed}/{total} passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
