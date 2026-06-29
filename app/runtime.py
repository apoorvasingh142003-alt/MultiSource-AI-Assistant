"""Runtime, switchable model configuration.

Lets the UI flip the live LLM between the server-configured **API** provider (e.g. OpenAI)
and a **local** model (Ollama / any OpenAI-compatible local server) WITHOUT a restart and
without entering a key — local endpoints need none.

Implementation: the process-wide ``Settings`` singleton is mutable, so we overwrite its
provider/base_url/model fields in place and reset the cached LLM clients. Embeddings already
built at startup are left untouched (the switch targets generation/routing/SQL/agent).
"""
from __future__ import annotations

from typing import Optional

from app.config import get_settings

_original: Optional[dict] = None     # snapshot of the API-mode settings
_mode: str = "api"


def _snapshot(s) -> dict:
    return {
        "llm_provider": s.llm_provider,
        "openai_base_url": s.openai_base_url,
        "model_generation": s.model_generation,
        "model_router": s.model_router,
        "model_sql": s.model_sql,
    }


def get_mode() -> str:
    return _mode


def _reset_llm_clients() -> None:
    from app.llm.client import get_llm
    llm = get_llm()
    llm._openai = None
    llm._anthropic = None


def set_model_mode(mode: str) -> str:
    """Switch the live model to ``api`` or ``local``. Returns the active mode."""
    global _original, _mode
    s = get_settings()
    if _original is None:
        _original = _snapshot(s)

    if mode == "local":
        s.llm_provider = "openai"                 # Ollama speaks the OpenAI API
        s.openai_base_url = s.local_base_url
        s.model_generation = s.local_model
        s.model_router = s.local_model
        s.model_sql = s.local_model
        _mode = "local"
    else:
        for k, v in _original.items():
            setattr(s, k, v)
        _mode = "api"

    _reset_llm_clients()
    return _mode


def status() -> dict:
    s = get_settings()
    return {
        "mode": _mode,
        "provider": s.llm_provider,
        "model": s.model_generation,
        "base_url": s.openai_base_url if s.llm_provider == "openai" else "anthropic",
        "local_model": s.local_model,
        "live": s.use_live_llm,
    }
