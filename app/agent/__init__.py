"""LangGraph iterative agent — an additive layer over the existing pipeline.

The agent reuses the SAME retrieval / SQL / verification machinery the classic
orchestrator uses (wrapped as LangChain tools), so every Inspector / Explainability /
Verification panel keeps working. It is import-guarded and only engages when
``agent_mode`` is requested AND the dependencies + a live LLM are available; otherwise
the engine transparently falls back to the classic path.
"""
