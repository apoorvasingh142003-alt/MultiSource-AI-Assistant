"""Process readiness signal for cold-start UX.

The engine builds + embeds the sample corpus on startup (``main._warm``); on a cold boot the
first request can arrive before that finishes. Rather than let the UI show an error, the
server reports an explicit ``warming`` state until the warm-up completes, and the UI shows a
calm "warming up" banner. This tiny module holds that one boolean so ``/health`` can answer
without forcing (or blocking on) an engine build.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_ready = False
_started_at = time.time()


def mark_ready() -> None:
    """Called once at the end of startup warm-up when the engine is built and serving."""
    global _ready
    with _lock:
        _ready = True


def is_ready() -> bool:
    with _lock:
        return _ready


def get_status() -> dict:
    """A cheap, never-failing snapshot for /health."""
    ready = is_ready()
    return {
        "ready": ready,
        "state": "ready" if ready else "warming",
        "uptime_seconds": round(time.time() - _started_at, 1),
    }
