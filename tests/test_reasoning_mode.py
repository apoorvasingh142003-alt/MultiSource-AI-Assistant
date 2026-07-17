"""Phase 5 — reasoning / design mode ("it thinks").

Pins the deterministic reasoning-mode detector and its end-to-end wiring:

- "advice"/"design" questions get the two-part treatment — PART 1 cited facts from the
  record (verified like any grounded answer), PART 2 clearly-labelled guidance / a
  structured design deliverable — and land on the *reasoned* side of the tri-state wall.
- "analysis" questions (clause/risk analysis) stay *grounded*: document intelligence
  strictly over the retrieved evidence.
- The detector never fires on the factual demo suite, and off-topic retrieval is never
  used to ground guidance (the wall holds).

Hermetic/offline (conftest forces auth off + hashing embeddings + offline LLM), so every
assertion runs the deterministic fallbacks.

Run:  .venv/bin/python -m pytest tests/test_reasoning_mode.py -q
"""
from __future__ import annotations

import re

import pytest

from app.generation.generate import ADVICE_GUIDANCE_DISCLAIMER
from app.retrieval.intent import detect_reasoning_mode


# -- the detector ------------------------------------------------------------

DESIGN_QUESTIONS = [
    "Design a renewal strategy for our customer contracts.",
    "Propose a plan to reduce overdue invoices.",
    "Draft a negotiation strategy for the GLOBEX agreement.",
    "Run a gap analysis on our agreements.",
    "What's missing from our supplier contracts?",
    "How can we improve our payment terms?",
]

ADVICE_QUESTIONS = [
    "Would you recommend smokeless tobacco for Mohammad Ben?",
    "Should he be prescribed ibuprofen for his pain?",
    "Is it advisable for him to switch to a high-sugar diet?",
    "How should we approach contract renewals next quarter?",
]

ANALYSIS_QUESTIONS = [
    "Analyze the termination clauses in our contracts.",
    "Assess the liability caps across the agreements.",
    "Identify the risks in our project documentation.",
    "Review the payment obligations in each contract.",
    "Give me a risk assessment of the INITECH agreement.",
]

# The factual demo suite (scripts/eval.py + flagship examples) must stay plain Q&A —
# a false-positive here would reroute a grounded demo answer through the advice path.
FACTUAL_QUESTIONS = [
    "What is the total outstanding invoice amount per customer?",
    "What do our contracts say about service suspension?",
    "Which contract clauses mention SLA-2025?",
    "Which customers have overdue invoices, and what do their agreements say about service suspension?",
    "What contracts expire in the next 90 days, and what penalties do they define?",
    "Show all active projects and summarize the risks in their documentation.",
    "Was sagt der Vertrag über die Aussetzung des Dienstes und Vertragsstrafen?",
    "What is our employee headcount in Berlin?",
    "Summarize the payment terms across every customer contract.",
    "Which document mentions INI-MSA-2024?",
    "What is the early termination penalty?",
    "What is his diet?",
]


@pytest.mark.parametrize("q", DESIGN_QUESTIONS)
def test_detects_design(q):
    assert detect_reasoning_mode(q) == "design"


@pytest.mark.parametrize("q", ADVICE_QUESTIONS)
def test_detects_advice(q):
    assert detect_reasoning_mode(q) == "advice"


@pytest.mark.parametrize("q", ANALYSIS_QUESTIONS)
def test_detects_analysis(q):
    assert detect_reasoning_mode(q) == "analysis"


@pytest.mark.parametrize("q", FACTUAL_QUESTIONS)
def test_factual_suite_stays_plain(q):
    assert detect_reasoning_mode(q) == ""


# -- end to end: design over the seeded contracts (the exit criterion) --------

def _engine():
    from app.engine import get_engine
    return get_engine()


def test_design_question_is_grounded_structured_and_labelled():
    """'Design a renewal strategy for these contracts' → structured, useful, clearly
    labelled, grounded in the actual contracts (Phase 5 exit criterion)."""
    resp = _engine().ask("Design a renewal strategy for our customer contracts.")
    assert resp.trace.reasoning_mode == "design"
    # labelled: reasoned side of the wall, with the exact disclaimer sentence
    assert resp.answer_state == "reasoned"
    assert not resp.insufficient
    assert ADVICE_GUIDANCE_DISCLAIMER in resp.answer
    # grounded: PART 1 cites real retrieved contract passages, and they verify
    assert resp.trace.evidence
    cited = re.findall(r"\[(e\d+)\]", resp.answer)
    assert cited, "design answer grounded no Part-1 citations"
    assert resp.trace.citation_check and resp.trace.citation_check.verified
    # structured: the two parts are present and Part 2 follows the disclaimer
    assert "PART 1" in resp.answer and "PART 2" in resp.answer
    assert resp.answer.index("PART 1") < resp.answer.index(ADVICE_GUIDANCE_DISCLAIMER)


def test_design_answer_streams():
    chunks: list[str] = []
    resp = _engine().ask("Design a renewal strategy for our customer contracts.",
                         on_token=chunks.append)
    streamed = "".join(chunks)
    assert streamed, "advice/design answer did not stream"
    assert ADVICE_GUIDANCE_DISCLAIMER in streamed


def test_analysis_question_stays_grounded():
    resp = _engine().ask("Analyze the termination clauses in our contracts.")
    assert resp.trace.reasoning_mode == "analysis"
    assert resp.answer_state == "grounded"
    assert not resp.insufficient
    assert resp.trace.evidence
    assert resp.trace.citation_check and resp.trace.citation_check.verified
    # analysis is grounded reasoning — never the advice disclaimer
    assert ADVICE_GUIDANCE_DISCLAIMER not in resp.answer


def test_offtopic_advice_never_grounds_in_junk():
    """An advice question whose subject is absent from the corpus must not quote
    off-topic passages as 'the record' — honest Part 1 + labelled guidance only."""
    resp = _engine().ask("Would you recommend we expand the Berlin office?")
    assert resp.answer_state == "reasoned"
    assert not resp.insufficient
    assert ADVICE_GUIDANCE_DISCLAIMER in resp.answer
    assert not resp.trace.evidence          # gate refused off-topic grounding
    assert not re.findall(r"\[(e\d+)\]", resp.answer)


def test_deep_research_design_gets_two_part_treatment():
    resp = _engine().ask("Design a renewal strategy for our customer contracts.",
                         deep_research=True)
    assert resp.trace.reasoning_mode == "design"
    assert resp.answer_state == "reasoned"
    assert ADVICE_GUIDANCE_DISCLAIMER in resp.answer
    assert resp.research_trace is not None


def test_grouped_citation_markers_are_normalized():
    """Live models sometimes emit "[e1, e2, e3]" — every downstream [eN] consumer
    (verification, contributions, clickable citations) must still see each id."""
    from app.generation.generate import _normalize_citation_groups
    assert _normalize_citation_groups("terms renew [e1, e2, e3].") == "terms renew [e1][e2][e3]."
    assert _normalize_citation_groups("cap [e2; e5]") == "cap [e2][e5]"
    assert _normalize_citation_groups("plain [e4].") == "plain [e4]."
    assert _normalize_citation_groups("no cites [see note]") == "no cites [see note]"


def test_paraphrased_disclaimer_is_reinserted_under_part2_header():
    """If the model paraphrases the disclaimer instead of emitting the exact sentence,
    the safety net must place the exact sentence directly under the Part 2 header — in
    front of the guidance it disclaims — not orphaned at the end of the answer."""
    from unittest.mock import patch
    from app.generation import generate as g
    from app.models import Evidence

    ev = [Evidence(id="e1", source_name="s", source_kind="documents",
                   content="renews for 12 months", citation_label="[doc p.1]")]
    fake = ("PART 1 — From the record:\nThe contract renews [e1].\n\n"
            "PART 2 — General guidance (not from your sources, may be inaccurate):\n"
            "### Strategy\nDo the thing.")
    with patch.object(g.get_llm(), "text", return_value=(fake, None)):
        answer, cited, insufficient, _ = g.generate_grounded_advice(
            "Design a strategy.", ev, mode="design")
    lines = answer.splitlines()
    part2_line = next(i for i, l in enumerate(lines) if l.startswith("PART 2"))
    assert lines[part2_line + 1] == g.ADVICE_GUIDANCE_DISCLAIMER
    assert answer.index(g.ADVICE_GUIDANCE_DISCLAIMER) < answer.index("### Strategy")
    assert cited == ["e1"]


def test_factual_pipeline_unchanged():
    """A flagship factual question is untouched by Phase 5: grounded, no mode, no
    disclaimer."""
    resp = _engine().ask("What do our contracts say about service suspension?")
    assert resp.trace.reasoning_mode is None
    assert resp.answer_state == "grounded"
    assert ADVICE_GUIDANCE_DISCLAIMER not in resp.answer
