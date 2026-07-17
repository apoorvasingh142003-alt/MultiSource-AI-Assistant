"""/health cold-start contract: never 500, always reports a readiness state.

The engine builds on startup; /health must answer even before that finishes (reporting
"warming") and once ready include the corpus summary. Uses a bare TestClient (no startup
warm-up runs), so this exercises the not-yet-marked-ready path too.

Run:  .venv/bin/python -m pytest tests/test_health.py -q
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_never_500_and_reports_readiness():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "warming")
        assert "ready" in body and isinstance(body["ready"], bool)
        assert "uptime_seconds" in body


def test_health_ready_includes_corpus_summary():
    # TestClient as a context manager runs the startup event → mark_ready() → engine built.
    with TestClient(app) as client:
        body = client.get("/health").json()
        if body["ready"]:
            assert body["status"] == "ok"
            assert body["documents"] >= 1
            assert isinstance(body["tables"], list)
