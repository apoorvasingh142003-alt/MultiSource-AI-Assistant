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

    # Phase 4 (deep research) — agentic iterative retrieval. Offline-deterministic:
    # an evidence-spread question must ITERATE (round 1 alone can't satisfy the corpus
    # spread), end grounded + citation-verified across several documents, and the whole
    # search must be recorded in research_trace. The wall check: deep research must
    # never ground an out-of-scope question in off-topic top-k passages.
    dq = "Summarize the payment terms across every customer contract."
    dresp = eng.ask(dq, deep_research=True)
    drt = dresp.research_trace or {}
    spread_ok = (
        dresp.answer_state == "grounded" and not dresp.insufficient
        and bool(dresp.trace.citation_check and dresp.trace.citation_check.verified)
        and len(drt.get("documents_covered", [])) >= eng.settings.research_spread_min_docs
        and 2 <= drt.get("total_rounds", 0) <= eng.settings.research_max_rounds
    )
    passed += spread_ok
    total += 1
    print(f"{'PDF':>7} {'deep':>7}  {'✓' if spread_ok else '✗':>2}  "
          f"{len(dresp.trace.evidence):>3}  "
          f"{('r%d/%dd' % (drt.get('total_rounds', 0), len(drt.get('documents_covered', [])))):>5}  "
          f"{('[deep research] ' + dq)[:64]}")

    wq = "What is our employee headcount in Berlin?"
    wresp = eng.ask(wq, deep_research=True)
    wall_ok = wresp.insufficient and wresp.answer_state == "insufficient"
    passed += wall_ok
    total += 1
    print(f"{'NONE':>7} {'deep':>7}  {'✓' if wall_ok else '✗':>2}  "
          f"{len(wresp.trace.evidence):>3}  {'wall':>5}  "
          f"{('[deep research] ' + wq)[:64]}")

    # Phase 5 (reasoning/design mode) — the exit criterion: a design/strategy question
    # produces a structured, clearly-LABELLED answer grounded in the actual contracts:
    # Part 1 cites retrieved evidence (verified), Part 2 carries the exact guidance
    # disclaimer, and the whole answer lands on the REASONED side of the wall. An
    # analysis question (document intelligence) stays GROUNDED. An advice question with
    # no relevant corpus stays disclaimed — never fabricated, never a bare decline.
    from app.generation.generate import ADVICE_GUIDANCE_DISCLAIMER

    q5 = "Design a renewal strategy for our customer contracts."
    r5 = eng.ask(q5)
    design_ok = (
        r5.answer_state == "reasoned" and not r5.insufficient
        and r5.trace.reasoning_mode == "design"
        and len(r5.trace.evidence) > 0
        and ADVICE_GUIDANCE_DISCLAIMER in r5.answer
        and bool(r5.trace.citation_check and r5.trace.citation_check.verified
                 and r5.trace.citation_check.cited_ids)
    )
    passed += design_ok
    total += 1
    print(f"{'PDF':>7} {'design':>7}  {'✓' if design_ok else '✗':>2}  "
          f"{len(r5.trace.evidence):>3}  {'rsnd':>5}  {('[design mode] ' + q5)[:64]}")

    q6 = "Analyze the termination clauses in our contracts."
    r6 = eng.ask(q6)
    analysis_ok = (
        r6.answer_state == "grounded" and not r6.insufficient
        and r6.trace.reasoning_mode == "analysis"
        and len(r6.trace.evidence) > 0
        and bool(r6.trace.citation_check and r6.trace.citation_check.verified)
    )
    passed += analysis_ok
    total += 1
    print(f"{'PDF':>7} {'analyz':>7}  {'✓' if analysis_ok else '✗':>2}  "
          f"{len(r6.trace.evidence):>3}  {'grnd':>5}  {('[analysis mode] ' + q6)[:64]}")

    q7 = "Would you recommend we expand the Berlin office?"
    r7 = eng.ask(q7)
    advice_ok = (
        r7.answer_state == "reasoned" and not r7.insufficient
        and ADVICE_GUIDANCE_DISCLAIMER in r7.answer
    )
    passed += advice_ok
    total += 1
    print(f"{'—':>7} {'advice':>7}  {'✓' if advice_ok else '✗':>2}  "
          f"{len(r7.trace.evidence):>3}  {'rsnd':>5}  {('[advice wall] ' + q7)[:64]}")

    print("-" * 100)
    print(f"{passed}/{total} passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
