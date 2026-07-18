"""Engine assembly — build the index and wire the sources + orchestrator once at startup,
then allow runtime ingestion of customer-uploaded PDFs and SQLite databases.

The engine is a process-wide singleton. Startup ingests only the deterministic sample
corpus (so it always boots clean). Uploads mutate the live engine under a lock:
PDF chunks are appended to the existing hybrid index, and uploaded SQLite tables are
merged into a working database the relational source is rebound to. The retrieval,
routing, SQL, and generation logic are untouched — only registration is added.
"""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.multi_agent import is_multipart
from app.ingestion.pdf import ingest_pdf, ingest_pdf_dir
from app.ingestion.sqlite_introspect import SchemaInfo, introspect
from app.ingestion.sqlite_register import copy_seed, merge_sqlite
from app.models import (ExampleQuestion, IngestedDatabaseInfo, IngestedDocumentInfo,
                        Inventory, SourceInfo, TableInfo, compute_answer_state)
from app.generation.components import build_components
from app.retrieval.document_retriever import DocumentIndex
from app.routing.orchestrator import Orchestrator
from app.sources.crm_source import CrmSource
from app.sources.document_source import DocumentSource
from app.sources.relational_source import RelationalSource

EXAMPLES = [
    ExampleQuestion(
        label="Pure SQL", route="SQL", language="en",
        question="What is the total outstanding invoice amount per customer?",
        why="Aggregation over the database; clean generated SQL with table/row citations."),
    ExampleQuestion(
        label="Pure document", route="PDF", language="en",
        question="What do our contracts say about service suspension?",
        why="Hybrid retrieval (dense + BM25) over the PDFs with page-level citations."),
    ExampleQuestion(
        label="Keyword beats vector", route="PDF", language="en",
        question="Which contract clauses mention SLA-2025?",
        why="BM25 finds the exact identifier 'SLA-2025' that pure embeddings miss."),
    ExampleQuestion(
        label="Hybrid (agentic)", route="HYBRID", language="en",
        question="Which customers have overdue invoices, and what do their agreements say about service suspension?",
        why="SQL finds overdue customers → those customers' contracts are retrieved → grounded combined answer. The flagship."),
    ExampleQuestion(
        label="Hybrid (date + clause)", route="HYBRID", language="en",
        question="What contracts expire in the next 90 days, and what penalties do they define?",
        why="Date filter in SQL + penalty clauses from the documents — impossible with vector search alone."),
    ExampleQuestion(
        label="Hybrid (projects + risks)", route="HYBRID", language="en",
        question="Show all active projects and summarize the risks in their documentation.",
        why="SQL lists active projects; project briefs supply the risk narrative, grouped per project."),
    ExampleQuestion(
        label="German", route="PDF", language="de",
        question="Was sagt der Vertrag über die Aussetzung des Dienstes und Vertragsstrafen?",
        why="Multilingual retrieval over a German contract — cross-lingual embeddings + Unicode BM25."),
    ExampleQuestion(
        label="Honest grounding", route="NONE", language="en",
        question="What is our employee headcount in Berlin?",
        why="No source can answer → the system says 'insufficient evidence' instead of guessing."),
]


class Engine:
    def __init__(self, user_id: str | None = None) -> None:
        self.settings = get_settings()
        # Each tenant gets its own Engine (see get_engine): the shared sample corpus is
        # rebuilt identically for everyone, but uploads + the merged upload DB live in a
        # per-user directory and a per-user in-memory index, so one tenant's documents can
        # never surface in another tenant's retrieval.
        self.user_id = user_id or self.settings.default_user_id
        self._uploads_dir = self.settings.data_path / "uploads" / self.user_id
        self.examples = EXAMPLES
        self._lock = threading.RLock()
        self._build_from_seed()

    @property
    def uploads_dir(self) -> Path:
        return self._uploads_dir

    # -- assembly ----------------------------------------------------------
    def _build_from_seed(self) -> None:
        s = self.settings
        # documents (sample corpus)
        docs = ingest_pdf_dir(s.pdf_dir)
        chunks = [c.as_dict() for d in docs for c in d.chunks]
        index = DocumentIndex()
        index.build(chunks)
        doc_names = [d.document for d in docs]
        languages = sorted({d.language for d in docs})
        self.document_source = DocumentSource(index, doc_names, languages)

        # relational (sample database) — the relational source starts bound to the seed DB.
        self._seed_db_path: Path = s.db_path
        self._working_db_path: Path | None = None
        schema = introspect(s.db_path)
        self._seed_table_names: set[str] = set(schema.table_names())
        self.relational_source = RelationalSource(s.db_path, schema)

        # per-source inventory (sample data is pre-loaded)
        self._documents: list[IngestedDocumentInfo] = [
            _doc_info_from_ingested(ingest_pdf(p), origin="sample")
            for p in sorted(s.pdf_dir.glob("*.pdf"))
        ]
        self._databases: list[IngestedDatabaseInfo] = [
            _db_info_from_schema("business.db (sample)", schema, origin="sample")
        ]

        self._rebuild_orchestrator()

    def _rebuild_orchestrator(self) -> None:
        self.orchestrator = Orchestrator(self.document_source, self.relational_source)

    # -- runtime ingestion -------------------------------------------------
    def add_pdf(self, filename: str, path: Path) -> IngestedDocumentInfo:
        """Ingest, embed, and index an uploaded PDF, then make it queryable."""
        with self._lock:
            t0 = time.perf_counter()
            try:
                try:
                    doc = ingest_pdf(path)
                except Exception:
                    raise ValueError(
                        "Unable to process PDF — the file may be corrupt, encrypted, "
                        "or not a valid PDF."
                    )
                if not doc.chunks:
                    raise ValueError(
                        "No extractable text found in this PDF. It may be a scanned "
                        "image (OCR is not enabled in this environment)."
                    )
                chunk_dicts = [c.as_dict() for c in doc.chunks]
                added = self.document_source.index.add_chunks(chunk_dicts)
                if doc.document not in self.document_source.documents:
                    self.document_source.documents.append(doc.document)
                langs = sorted({c.language for c in doc.chunks}) or [doc.language]
                for lg in langs:
                    if lg not in self.document_source.languages:
                        self.document_source.languages.append(lg)
                self._rebuild_orchestrator()
                info = IngestedDocumentInfo(
                    name=doc.document, origin="uploaded", status="indexed",
                    chunks_indexed=added, languages=langs,
                    pages=max((c.page for c in doc.chunks), default=0),
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                    parse_confidence=getattr(doc, "parse_confidence", None),
                    parser=getattr(doc, "parser", None),
                )
            except Exception as exc:  # never let a bad upload take down the engine
                info = IngestedDocumentInfo(
                    name=filename, origin="uploaded", status="error",
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                    error=str(exc),
                )
            self._documents = [d for d in self._documents if d.name != info.name] + [info]
            return info

    def add_database(self, filename: str, path: Path) -> IngestedDatabaseInfo:
        """Register an uploaded SQLite database with the router by merging its tables
        into a working database and rebinding the relational source."""
        with self._lock:
            t0 = time.perf_counter()
            try:
                if self._working_db_path is None:
                    self._uploads_dir.mkdir(parents=True, exist_ok=True)
                    self._working_db_path = self._uploads_dir / "working.db"
                    copy_seed(self._seed_db_path, self._working_db_path)
                try:
                    merged = merge_sqlite(path, self._working_db_path, source_label=filename)
                except Exception:
                    raise ValueError(
                        "Unable to read this SQLite database — the file may be corrupt or "
                        "use an unsupported format."
                    )
                if not merged:
                    raise ValueError(
                        "No tables found in this SQLite database — nothing to register."
                    )
                schema = introspect(self._working_db_path)
                self.relational_source = RelationalSource(self._working_db_path, schema)
                self._rebuild_orchestrator()

                cols_by_table = {t.name: [c.name for c in t.columns] for t in schema.tables}
                tables = [
                    TableInfo(
                        name=m.effective,
                        original_name=(m.original if m.original != m.effective else None),
                        rows=m.rows, columns=cols_by_table.get(m.effective, []),
                    )
                    for m in merged
                ]
                info = IngestedDatabaseInfo(
                    name=filename, origin="uploaded", status="indexed",
                    tables=tables, total_rows=sum(t.rows for t in tables),
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
            except Exception as exc:
                info = IngestedDatabaseInfo(
                    name=filename, origin="uploaded", status="error",
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                    error=str(exc),
                )
            self._databases = [d for d in self._databases if d.name != info.name] + [info]
            return info

    def reset(self) -> None:
        """Return THIS tenant's workspace to a clean sample state (drops only their uploads)."""
        with self._lock:
            # best-effort cleanup of this user's uploaded artifacts on disk
            try:
                import shutil
                if self._uploads_dir.exists():
                    shutil.rmtree(self._uploads_dir)
            except Exception:
                pass
            self._build_from_seed()

    # -- views -------------------------------------------------------------
    def inventory(self) -> Inventory:
        docs = list(self._documents)
        dbs = list(self._databases)
        return Inventory(
            documents=docs, databases=dbs,
            total_chunks=self.document_source.index.n_chunks,
            total_tables=sum(len(d.tables) for d in dbs),
        )

    @property
    def sources(self) -> list[SourceInfo]:
        return [
            self.document_source.describe(),
            self.relational_source.describe(),
            CrmSource().describe(),
        ]

    def ask(
        self,
        question: str,
        scope: str = "all",
        role: Optional[str] = None,
        output_mode: str = "Standard Response",
        custom_system_prompt: Optional[str] = None,
        agent_role: Optional[str] = None,
        output_format: Optional[str] = "auto",
        session_id: Optional[str] = None,
        multi_agent: bool = False,
        agent_mode: bool = False,
        deep_research: bool = False,
        temperature: Optional[float] = None,
        conversation_history: Optional[list[dict]] = None,
        on_token=None,
        on_event=None,
    ):
        with self._lock:
            # Action command (Phase 6): an explicit "create a lead for … / escalate this /
            # raise an invoice …" message is a WRITE request, not a question — no retrieval
            # runs, and nothing is dispatched. The response carries a ProposedAction the
            # user must confirm (POST /actions/execute) before anything leaves the system.
            from app.actions.detect import detect_action_command
            cmd = detect_action_command(question)
            if cmd is not None:
                return self._action_command_response(question, cmd)

            allowed_docs, allowed_tables = self._scope_sources(scope)
            if scope == "workspace" and not allowed_docs and not allowed_tables:
                return self._empty_workspace_response(question)

            # Conversation memory: load prior turns for the session so follow-up
            # questions resolve references. Caller may pass history explicitly.
            if conversation_history is None and session_id:
                from app.conversation import load_history
                conversation_history = load_history(session_id)

            # Deep research (Phase 4): bounded retrieve → sufficiency-check →
            # reformulate loop. Provider-agnostic and offline-deterministic, so it
            # takes precedence over agent mode when both are toggled.
            if deep_research:
                from app.agent.research import run_deep_research
                resp = run_deep_research(
                    self.orchestrator, question,
                    allowed_docs=allowed_docs, allowed_tables=allowed_tables,
                    role=role, output_mode=output_mode,
                    custom_system_prompt=custom_system_prompt, agent_role=agent_role,
                    output_format=output_format, temperature=temperature,
                    conversation_history=conversation_history, on_token=on_token,
                    on_event=on_event,
                )
                return self._finalize(resp)

            # Agent mode (Section: LangGraph iterative agent): the model loops over
            # tools (SQL / document retrieval), then we rebuild the standard Trace so
            # every inspector/explainability panel still lights up. Falls back to the
            # classic path when unavailable (offline / no key / import missing).
            if agent_mode:
                try:
                    from app.agent.runner import run_agent, agent_available
                    available = agent_available()
                except Exception:
                    available = False
                if available:
                    resp = run_agent(
                        self.orchestrator, question,
                        allowed_docs=allowed_docs, allowed_tables=allowed_tables,
                        role=role, output_mode=output_mode,
                        custom_system_prompt=custom_system_prompt, agent_role=agent_role,
                        output_format=output_format, temperature=temperature,
                        conversation_history=conversation_history, on_token=on_token,
                        on_event=on_event, user_id=self.user_id,
                    )
                    return self._finalize(resp)

            # Multi-agent decomposition (Section 10): triggered explicitly or by a
            # multi-part heuristic. Runs the full pipeline per sub-question, then synthesizes.
            if multi_agent or is_multipart(question):
                from app.multi_agent import run_multi_agent
                resp = run_multi_agent(
                    self.orchestrator, question, allowed_docs, allowed_tables,
                    role, output_mode, custom_system_prompt, agent_role, output_format,
                    temperature, conversation_history,
                )
            else:
                resp = self.orchestrator.ask(
                    question,
                    allowed_docs=allowed_docs,
                    allowed_tables=allowed_tables,
                    role=role,
                    output_mode=output_mode,
                    custom_system_prompt=custom_system_prompt,
                    agent_role=agent_role,
                    output_format=output_format,
                    temperature=temperature,
                    conversation_history=conversation_history,
                    on_token=on_token,
                )
            return self._finalize(resp)

    def _finalize(self, resp):
        """Common tail for every answer path: stamp evidence provenance, compute the
        tri-state grounding label once, then build the inline generative components — all
        at this single chokepoint so no path can forget them or disagree on the label."""
        self._stamp_origin(resp.trace.evidence)
        resp.answer_state = compute_answer_state(
            resp.answer, resp.trace.route, resp.trace.evidence, resp.insufficient
        )
        # Generative components (cited table / chart / timeline / artifact) — deterministic,
        # built from the same evidence the wall verified, and gated on `grounded` inside
        # build_components so an ungrounded answer never renders a confident-looking chart.
        resp.components = build_components(
            resp.question, resp.answer_state, resp.trace, resp.trace.evidence
        )
        # Sandboxed computation (Phase 6): gated inside maybe_compute to grounded answers
        # with SQL rows AND an explicit statistical ask. The appended block is labeled
        # "computed from the cited rows"; a failed run surfaces in the trace only.
        try:
            from app.code_exec import maybe_compute
            code_exec, block = maybe_compute(resp.question, resp.answer_state, resp.trace)
            if code_exec is not None:
                resp.trace.code_execution = code_exec
                if block:
                    resp.answer = resp.answer.rstrip() + block
                    resp.trace.notes.append(
                        "Sandboxed computation ran over the retrieved SQL rows "
                        f"({code_exec.get('source_rows', 0)} row(s)); code + output are in the trace."
                    )
        except Exception:  # analysis must never take down an answer
            pass
        # Escalate when unsure (Phase 6): an insufficient answer additionally offers a
        # one-click human handoff. The honest decline stays the honest decline — the
        # label/chip are untouched; the suggestion is a separate, clearly-labeled card.
        try:
            if resp.answer_state == "insufficient":
                from app.actions.service import build_proposal, get_config
                if get_config(self.user_id, "escalate")["enabled"]:
                    proposal = build_proposal(
                        self.user_id, "escalate",
                        {"reason": f"The assistant could not answer: {resp.question}",
                         "context": (resp.answer or "")[:400]},
                        origin="suggested",
                    )
                    resp.actions.append(proposal)
                    resp.trace.actions.append(proposal.model_dump())
                    resp.trace.notes.append(
                        "Insufficient evidence — offered a human-handoff escalation "
                        "(confirm-to-send; the answer label is unchanged)."
                    )
        except Exception:
            pass
        return resp

    def _action_command_response(self, question: str, cmd):
        """A pure action command's turn: a deterministic procedural acknowledgment plus
        the ProposedAction. No retrieval, no knowledge claims, nothing dispatched."""
        from app.actions.service import build_proposal
        from app.models import AskResponse, RouteDecision, Trace
        proposal = build_proposal(self.user_id, cmd.action, cmd.params, origin="command")
        needs = (
            f" Fill in {', '.join(proposal.missing)} before confirming."
            if proposal.missing else ""
        )
        dest = (
            "your n8n workflow" if proposal.configured
            else "the local audit log (no n8n webhook is configured yet — add one under "
                 "Sources → Actions & automations to go live)"
        )
        answer = (
            f"I've prepared a **{proposal.title}** action from your message — review the "
            f"details below and confirm to send it to {dest}.{needs} Nothing is sent "
            "until you confirm."
        )
        trace = Trace(
            question=question,
            route=RouteDecision(route="NONE", confidence=1.0,
                                reasoning="Action command — no retrieval performed."),
            notes=[cmd.reason,
                   "Proposal only: execution requires an explicit user confirmation."],
            mode="deterministic",
            actions=[proposal.model_dump()],
        )
        return AskResponse(
            question=question, answer=answer, insufficient=False,
            answer_state="grounded",  # procedural ack; the UI hides the chip (action_only)
            citations=[], actions=[proposal], action_only=True, trace=trace,
        )

    def _scope_sources(self, scope: str):
        """Resolve a scope to the document names + table names it may use.
        Returns (allowed_docs, allowed_tables); None means 'no restriction'."""
        if scope == "all":
            return None, None
        want_uploaded = scope == "workspace"
        docs = [d.name for d in self._documents
                if d.status == "indexed" and (d.origin == "uploaded") == want_uploaded]
        tables = [t for t in self.relational_source.schema.table_names()
                  if (t not in self._seed_table_names) == want_uploaded]
        return docs, tables

    def _empty_workspace_response(self, question: str):
        from app.models import AskResponse, RouteDecision, Trace
        msg = ("Your workspace is empty. Upload a PDF or SQLite database on the left to ask "
               "questions about your own data. (Open the Demo tab to see the assistant working "
               "on sample contracts and a business database.)")
        return AskResponse(
            question=question, answer=msg, insufficient=True, answer_state="insufficient",
            citations=[],
            trace=Trace(
                question=question,
                route=RouteDecision(route="NONE", reasoning="Empty workspace — no uploaded sources yet.",
                                    confidence=0.0),
                notes=["No sources in the workspace. Upload a PDF or database to begin."],
                mode="deterministic",
            ),
        )

    # -- provenance --------------------------------------------------------
    def _table_origin(self) -> dict[str, str]:
        return {
            t.name: ("sample" if t.name in self._seed_table_names else "uploaded")
            for t in self.relational_source.schema.tables
        }

    def _stamp_origin(self, evidence) -> None:
        """Tag every evidence item with its provenance (sample vs uploaded) so the client
        is never left wondering whether an answer came from their upload or our demo data.
        (trace.evidence and citations reference the same objects, so this covers both.)"""
        doc_origin = {d.name: d.origin for d in self._documents}
        tbl_origin = self._table_origin()
        for e in evidence:
            if e.source_kind == "documents" and e.document:
                e.origin = doc_origin.get(e.document)
            elif e.source_kind == "relational" and e.table:
                e.origin = tbl_origin.get(e.table)


# -- inventory helpers -------------------------------------------------------

def _doc_info_from_ingested(doc, origin: str) -> IngestedDocumentInfo:
    langs = sorted({c.language for c in doc.chunks}) or [doc.language]
    return IngestedDocumentInfo(
        name=doc.document, origin=origin, status="indexed",
        chunks_indexed=len(doc.chunks), languages=langs,
        pages=max((c.page for c in doc.chunks), default=0),
        parse_confidence=getattr(doc, "parse_confidence", None),
        parser=getattr(doc, "parser", None),
    )


def _db_info_from_schema(name: str, schema: SchemaInfo, origin: str) -> IngestedDatabaseInfo:
    tables = [
        TableInfo(name=t.name, rows=t.row_count, columns=[c.name for c in t.columns])
        for t in schema.tables
    ]
    return IngestedDatabaseInfo(
        name=name, origin=origin, status="indexed",
        tables=tables, total_rows=sum(t.rows for t in tables),
    )


@lru_cache(maxsize=64)
def _engine_for(user_id: str) -> Engine:
    return Engine(user_id)


def get_engine(user_id: str | None = None) -> Engine:
    """Return the per-tenant Engine (built + cached on first use for each user).

    ``user_id=None`` resolves to the default user — used by non-tenant surfaces
    (startup warm-up, /health, /config) and by the whole offline test suite, so their
    behaviour is unchanged. Cached per user so repeated requests reuse the warm index;
    the LRU cap bounds memory (an evicted tenant simply rebuilds on next request).
    """
    uid = user_id or get_settings().default_user_id
    return _engine_for(uid)
