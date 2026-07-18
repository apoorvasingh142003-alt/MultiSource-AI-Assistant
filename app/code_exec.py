"""Sandboxed code execution for analysis intents (Phase 6).

Scope is deliberately tight: when a GROUNDED answer's trace holds SQL rows and the
question asks for statistics SQL didn't compute (median, average, spread, growth…), a
small deterministic Python script is generated over those rows and run in a locked-down
subprocess. The code + output are shown in the inspector ("Sandboxed computation") and the
answer gains a clearly-labeled "Computed from the cited rows" block.

Why this shape:
- **Deterministic codegen** — no LLM required, so offline/CI behave identically and the
  script can never exfiltrate or invent anything (it is derived from the question's cues
  and the rows' numeric columns only).
- **Defense in depth** — the script is AST-validated (imports limited to math/statistics/
  json, no dunder access, whitelisted builtins) and then executed in ``python -I -S`` with
  rlimits (CPU, memory, file size) and a hard wall-clock kill. Rows go in via stdin JSON;
  results come out as stdout JSON. Nothing runs on the app's interpreter state.
- **The wall holds** — computed values derive from grounded, cited rows; the block is
  additive and labeled, never a new unlabeled answer stream. Reasoned / insufficient
  answers never run code.
"""
from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import sys
import time

log = logging.getLogger("aba.codeexec")

_TIMEOUT_S = 5.0

# Statistical asks that plain SELECTs typically don't answer (SQLite has no MEDIAN/STDEV).
_COMPUTE_CUE = re.compile(
    r"\b(median|mean|average|avg|std|standard\s+deviation|variance|percentile|"
    r"quartile|correlat\w*|spread|growth\s+rate|cagr|percent(?:age)?\s+(?:change|difference))\b",
    re.I,
)


def detect_compute_intent(question: str) -> bool:
    """True when the question asks for a statistic worth computing over retrieved rows."""
    return bool(_COMPUTE_CUE.search(question or ""))


# --------------------------------------------------------------------------- #
# Deterministic codegen
# --------------------------------------------------------------------------- #
def build_analysis_code(columns: list[str], rows: list[dict]) -> str | None:
    """A summary-statistics script over the numeric columns of the retrieved rows.
    Returns None when there is nothing numeric to compute."""
    numeric = [c for c in columns if _is_numeric_column(c, rows)]
    if not rows or not numeric:
        return None
    return f'''import json, statistics

numeric_columns = {numeric!r}
summary = {{}}
for col in numeric_columns:
    values = [float(r[col]) for r in rows
              if r.get(col) is not None and str(r[col]).replace(".", "", 1).replace("-", "", 1).isdigit()]
    if not values:
        continue
    summary[col] = {{
        "count": len(values),
        "sum": round(sum(values), 2),
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }}
print(json.dumps(summary))
'''


def _is_numeric_column(col: str, rows: list[dict]) -> bool:
    vals = [r.get(col) for r in rows if r.get(col) is not None]
    if not vals:
        return False
    ok = 0
    for v in vals:
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            ok += 1
        else:
            try:
                float(str(v))
                ok += 1
            except ValueError:
                return False
    return ok > 0


# --------------------------------------------------------------------------- #
# AST validation (first line of defense — before a subprocess ever starts)
# --------------------------------------------------------------------------- #
_ALLOWED_IMPORTS = {"math", "statistics", "json"}
_FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "memoryview",
    "exit", "quit", "help", "dir", "type", "super", "object", "classmethod",
    "staticmethod", "property",
}


def validate_code(code: str) -> str | None:
    """Return an error string if the code is not sandbox-safe, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Syntax error: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in node.names]
            if isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            bad = [n for n in names if n not in _ALLOWED_IMPORTS]
            if bad:
                return f"Import of {', '.join(bad)} is not allowed."
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return f"Use of '{node.id}' is not allowed."
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return "Dunder attribute access is not allowed."
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.ClassDef,
                               ast.AsyncFunctionDef, ast.Await, ast.Lambda)):
            return f"'{type(node).__name__}' is not allowed."
    return None


# --------------------------------------------------------------------------- #
# Subprocess sandbox (second line of defense)
# --------------------------------------------------------------------------- #
# The harness runs inside `python -I -S` (isolated: no site-packages, no cwd on sys.path,
# env ignored), applies rlimits, restricts builtins, then execs the validated code with
# only `rows` + math/statistics/json in scope.
_HARNESS = r'''
import json, math, statistics, sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
except Exception:
    pass
payload = json.loads(sys.stdin.read())
safe_builtins = {n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n)
                 for n in ("len", "sum", "min", "max", "sorted", "round", "abs", "range",
                           "enumerate", "zip", "map", "filter", "float", "int", "str",
                           "bool", "list", "dict", "set", "tuple", "print", "isinstance",
                           "any", "all", "reversed", "ValueError", "ZeroDivisionError",
                           "Exception", "KeyError", "IndexError", "TypeError")}
_allowed_modules = {"math": math, "statistics": statistics, "json": json}
def _restricted_import(name, *args, **kwargs):
    if name in _allowed_modules:
        return _allowed_modules[name]
    raise ImportError("import of " + repr(name) + " is not allowed in the sandbox")
safe_builtins["__import__"] = _restricted_import
scope = {"__builtins__": safe_builtins, "math": math, "statistics": statistics,
         "json": json, "rows": payload["rows"]}
exec(compile(payload["code"], "<analysis>", "exec"), scope)
'''


def run_sandboxed(code: str, rows: list[dict]) -> dict:
    """Validate + execute the analysis script. Returns
    {ok, code, output, error, duration_ms} and never raises."""
    err = validate_code(code)
    if err:
        return {"ok": False, "code": code, "output": "", "error": err, "duration_ms": 0.0}
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _HARNESS],
            input=json.dumps({"code": code, "rows": rows}),
            capture_output=True, text=True, timeout=_TIMEOUT_S,
        )
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if proc.returncode != 0:
            return {"ok": False, "code": code, "output": proc.stdout.strip()[:2000],
                    "error": (proc.stderr.strip() or "sandbox exited non-zero")[:500],
                    "duration_ms": ms}
        return {"ok": True, "code": code, "output": proc.stdout.strip()[:4000],
                "error": "", "duration_ms": ms}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": code, "output": "",
                "error": f"Timed out after {_TIMEOUT_S:.0f}s (killed).",
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001 — analysis must never take down an answer
        log.warning("sandbox failed: %s", exc)
        return {"ok": False, "code": code, "output": "", "error": str(exc)[:500],
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1)}


# --------------------------------------------------------------------------- #
# The one entry point the engine calls
# --------------------------------------------------------------------------- #
def maybe_compute(question: str, answer_state: str, trace) -> tuple[dict | None, str]:
    """Run the gated analysis step. Returns (code_execution dict for the trace, an
    answer-append block) — (None, "") when the gate doesn't open."""
    if answer_state != "grounded" or not detect_compute_intent(question):
        return None, ""
    best = None
    for s in trace.sql_executions:
        if s.valid and s.rows and (best is None or s.row_count > best.row_count):
            best = s
    if best is None:
        return None, ""
    code = build_analysis_code(best.columns, best.rows)
    if not code:
        return None, ""
    result = run_sandboxed(code, best.rows)
    result["source_rows"] = best.row_count
    result["source_sql"] = best.validated_sql or best.generated_sql
    if not result["ok"]:
        # A failed computation is surfaced in the trace but never mangles the answer.
        return result, ""
    try:
        summary = json.loads(result["output"])
    except Exception:
        return result, ""
    if not summary:
        return result, ""
    lines = [
        "\n\n---\n**Computed from the cited rows** (sandboxed Python over the "
        f"{best.row_count} retrieved row(s) — code and output in the Trace panel):",
    ]
    for col, s in summary.items():
        lines.append(
            f"- `{col}`: mean {s['mean']:,} · median {s['median']:,} · "
            f"σ {s['stdev']:,} · min {s['min']:,} · max {s['max']:,} "
            f"(n={s['count']}, sum {s['sum']:,})"
        )
    return result, "\n".join(lines)
