"""Sandboxed code execution (Phase 6) — gated, validated, isolated, wall-safe.

The compute step runs ONLY for a grounded answer whose trace holds SQL rows AND whose
question carries an explicit statistical cue; the script is AST-validated (imports,
dunders, dangerous builtins) and executed in an rlimit-capped subprocess. These tests pin
the gate, the validator's rejections, the sandbox behaviour (incl. the wall-clock kill),
and the end-to-end engine wiring. Offline and deterministic.

Run:  .venv/bin/python -m pytest tests/test_code_exec.py -q
"""
from __future__ import annotations

from app.code_exec import (build_analysis_code, detect_compute_intent, maybe_compute,
                           run_sandboxed, validate_code)
from app.engine import EXAMPLES, get_engine
from app.models import RouteDecision, SqlExecutionTrace, Trace

ROWS = [
    {"customer": "Acme", "amount": 100.5},
    {"customer": "Globex", "amount": 200.0},
    {"customer": "Initech", "amount": 340.25},
]


def _trace_with_rows(rows=ROWS) -> Trace:
    return Trace(
        question="q",
        route=RouteDecision(route="SQL", reasoning="", confidence=1.0),
        sql_executions=[SqlExecutionTrace(
            purpose="sql_main", natural_language="q", generated_sql="SELECT …",
            validated_sql="SELECT …", valid=True,
            columns=list(rows[0].keys()) if rows else [], rows=rows,
            row_count=len(rows), tables=["invoices"],
        )],
    )


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #
def test_compute_intent_cues():
    assert detect_compute_intent("What is the median invoice amount?")
    assert detect_compute_intent("average revenue and the standard deviation")
    assert detect_compute_intent("What's the growth rate quarter over quarter?")
    assert not detect_compute_intent("What is the total outstanding invoice amount per customer?")
    for ex in EXAMPLES:  # the demo suite never triggers the sandbox
        assert not detect_compute_intent(ex.question), ex.question


def test_gate_requires_grounded_state_and_rows():
    t = _trace_with_rows()
    assert maybe_compute("median amount?", "insufficient", t) == (None, "")
    assert maybe_compute("median amount?", "reasoned", t) == (None, "")
    assert maybe_compute("what happened?", "grounded", t) == (None, "")   # no cue
    empty = Trace(question="q", route=RouteDecision(route="PDF", reasoning="", confidence=1.0))
    assert maybe_compute("median amount?", "grounded", empty) == (None, "")


def test_gate_opens_for_grounded_sql_with_cue():
    result, block = maybe_compute("What is the median amount?", "grounded", _trace_with_rows())
    assert result is not None and result["ok"] is True
    assert result["source_rows"] == 3
    assert "Computed from the cited rows" in block
    assert "median 200" in block


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #
def test_validator_rejects_escapes():
    assert validate_code("import os") is not None
    assert validate_code("from subprocess import run") is not None
    assert validate_code("open('/etc/passwd')") is not None
    assert validate_code("().__class__.__mro__") is not None
    assert validate_code("eval('1')") is not None
    assert validate_code("__import__('os')") is not None
    assert validate_code("class A: pass") is not None
    assert validate_code("x = lambda: 1") is not None
    assert validate_code("x = (") is not None                    # syntax error
    # the allowed surface stays allowed
    assert validate_code("import math, statistics, json\nprint(1)") is None
    assert validate_code(build_analysis_code(["customer", "amount"], ROWS)) is None


# --------------------------------------------------------------------------- #
# Sandbox
# --------------------------------------------------------------------------- #
def test_sandbox_computes_stats():
    res = run_sandboxed(build_analysis_code(["customer", "amount"], ROWS), ROWS)
    assert res["ok"] is True and res["error"] == ""
    assert '"median": 200.0' in res["output"]
    assert '"count": 3' in res["output"]


def test_sandbox_rejects_invalid_code_before_spawning():
    res = run_sandboxed("import os\nprint(os.getcwd())", ROWS)
    assert res["ok"] is False and "not allowed" in res["error"]
    assert res["duration_ms"] == 0.0                              # never spawned


def test_sandbox_kills_runaway_code():
    res = run_sandboxed("while True:\n    pass", [])
    assert res["ok"] is False
    assert "Timed out" in res["error"] or res["error"]            # rlimit may kill first


def test_sandbox_runtime_error_is_captured():
    res = run_sandboxed("print(1 / 0)", [])
    assert res["ok"] is False and "ZeroDivision" in res["error"]


def test_non_numeric_rows_produce_no_code():
    rows = [{"name": "a", "status": "open"}]
    assert build_analysis_code(["name", "status"], rows) is None


# --------------------------------------------------------------------------- #
# Engine end-to-end
# --------------------------------------------------------------------------- #
def test_engine_appends_labeled_compute_block():
    resp = get_engine().ask("What is the average and median invoice amount across all invoices?")
    assert resp.answer_state == "grounded" and not resp.insufficient
    ce = resp.trace.code_execution
    assert ce is not None and ce["ok"] is True
    assert "Computed from the cited rows" in resp.answer
    assert "sandboxed" in resp.answer


def test_engine_skips_compute_for_plain_questions():
    resp = get_engine().ask("What is the total outstanding invoice amount per customer?")
    assert resp.trace.code_execution is None
    assert "Computed from the cited rows" not in resp.answer
