# AI Business Knowledge Assistant — Project Context

## Purpose

This repository implements a business knowledge assistant that answers free-form business questions by retrieving and combining evidence from multiple sources. It is designed as a retrieval orchestration engine rather than a simple PDF chatbot.

The system supports:
- PDF document retrieval with semantic and keyword search
- Structured SQL database querying with safe generated SQL
- Hybrid agentic workflows that combine database results with document search
- Bilingual support: English and Hebrew
- Traceable, citation-verified answers with a full audit trail

## Key Features

### 1. Source-aware question routing
- The system routes questions to one of four outcomes: `PDF`, `SQL`, `HYBRID`, or `NONE`
- Routing uses a hybrid combination of deterministic rules and language model classification
- The router is source-centric: it decides which stored source(s) can answer the question
- `NONE` is a valid safe outcome meaning "insufficient evidence"

### 2. Document retrieval
- Uses dense local multilingual embeddings and BM25 keyword search in parallel
- Combines retrieval ranks using Reciprocal Rank Fusion (RRF)
- Optionally reranks candidates with a cross-encoder
- Supports document filtering by metadata and entity linkage
- Returns detailed retrieval scores and provenance for each candidate

### 3. SQL generation and execution
- Generates SQL from natural language using a model prompt
- Validates generated SQL with `sqlglot`
- Enforces read-only, single `SELECT` queries and injects `LIMIT`
- Executes queries against a SQLite database in a safe, read-only session
- Supports `business_db` schema with tables such as `customers`, `contracts`, `invoices`, `payments`, and `projects`

### 4. Hybrid agentic orchestration
- The hybrid path runs SQL first and uses its results to restrict document retrieval
- Example: find overdue customers in the database, then retrieve only their contract documents
- This enables combined answers that reference both structured data and document evidence

### 5. Grounded answer generation
- The answer generator is instructed to use evidence-only reasoning
- Each claim in the answer is cited with `[eN]`
- Generates grounded prose and honors the evidence provenance
- A deterministic offline answer path exists when no external key is available

### 6. Citation verification
- Verifies that every citation in the final answer maps to retrieved evidence
- Ensures the answer is auditable and traceable
- Flags unverifiable citations in the trace output

### 7. Traceability and inspection
- The UI exposes a full trace showing:
  - routing decision and confidence
  - SQL generation, validation, and results
  - document retrieval candidates and ranking details
  - evidence items and citation labels
  - timing and cost metrics
- The trace is the single source of truth for answer provenance

## Architecture

The system is organized into four main stages:

1. **Routing**
   - `app/routing/classify.py`
   - `app/routing/orchestrator.py`

2. **Retrieval**
   - Document retrieval in `app/retrieval/`
   - SQL generation and validation in `app/sql/`

3. **Generation**
   - Grounded generation in `app/generation/generate.py`
   - Verification in `app/generation/verify.py`

4. **Sources**
   - Source interface in `app/sources/base.py`
   - Document source in `app/sources/document_source.py`
   - Relational source in `app/sources/relational_source.py`
   - CRM stub source in `app/sources/crm_source.py`

### Data flow

1. User submits a question.
2. Router decides whether to use PDF, SQL, hybrid, or answer none.
3. For PDF:
   - Document retrieval returns candidate passages.
   - Evidence items are aggregated.
4. For SQL:
   - SQL is generated, validated, executed, and rows are returned.
   - Rows become evidence items.
5. For hybrid:
   - SQL rows are used to identify document targets.
   - Document retrieval is filtered to those sources.
6. Evidence is combined and passed to grounded generation.
7. Generated answer is citation-verified before delivery.

## Components and files

### Application backend
- `app/main.py` — FastAPI application entrypoint
- `app/config.py` — configuration and environment handling
- `app/engine.py` — core orchestration and pipeline engine
- `app/models.py` — data models and Pydantic schemas
- `app/pricing.py` — per-answer cost accounting

### API routes
- `app/api/routes.py` — route definitions for the API endpoints

### Retrieval
- `app/retrieval/vector_store.py` — NumPy and Qdrant adapters
- `app/retrieval/bm25.py` — BM25 keyword search
- `app/retrieval/fusion.py` — RRF combining
- `app/retrieval/rerank.py` — optional cross-encoder reranking
- `app/retrieval/document_retriever.py` — document retrieval orchestration
- `app/retrieval/intent.py` — intent detection or retrieval-specific logic? (note: may be used for source-specific routing)

### SQL
- `app/sql/generate.py` — model prompt and SQL generation
- `app/sql/validate.py` — SQL AST validation and enforcement
- `app/sql/execute.py` — safe SQLite execution

### Sources
- `app/sources/base.py` — base `Source` interface
- `app/sources/document_source.py` — document/PDF retrieval implementation
- `app/sources/relational_source.py` — relational DB source implementation
- `app/sources/crm_source.py` — future-facing CRM source stub

### LLM and embeddings
- `app/llm/client.py` — provider-agnostic LLM client
- `app/llm/embeddings.py` — local multilingual embedding generation and fallback

### Ingestion
- `app/ingestion/pdf.py` — PDF text extraction and chunking, including RTL normalization
- `app/ingestion/sqlite_introspect.py` — DB schema introspection
- `app/ingestion/sqlite_register.py` — schema and row registration helpers

### UI
- `ui/app/page.tsx` — main frontend page
- `ui/components/` — front-end components for answer display and inspection
- `ui/lib/api.ts` — API client utilities
- `ui/lib/types.ts` — shared TypeScript types

### Scripts and data
- `scripts/seed_data.py` — generates sample SQLite database data
- `scripts/make_pdfs.py` — generates PDF corpus for document retrieval
- `scripts/eval.py` — end-to-end evaluation of routing and evidence quality
- `data/pdfs/` — sample PDF documents
- `data/business.db` — sample SQLite database

## Deployment and run modes

### Docker Compose
- Primary command: `docker compose up --build`
- API exposed on `http://localhost:8000`
- UI exposed on `http://localhost:3000`
- Optional Qdrant profile: `docker compose --profile qdrant up`
- Optional Cloudflare tunnel profile: `docker compose --profile tunnel up -d`

### Local development
- Backend: create a Python venv, install dependencies, run `uvicorn app.main:app --reload --port 8000`
- Frontend: `cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev`

### Environment configuration
- `.env.example` contains all relevant variables
- Core settings include:
  - `ABA_LLM_PROVIDER`
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `ABA_OPENAI_BASE_URL`
  - `ABA_OFFLINE_MODE`
  - `ABA_MODEL_GENERATION`
  - `ABA_MODEL_ROUTER`
  - `ABA_MODEL_SQL`
  - `ABA_VECTOR_BACKEND`
  - `ABA_QDRANT_URL`

### Offline mode
- If no API key is provided, the system runs in deterministic offline mode
- Offline mode is still fully traceable
- Embeddings are local and do not require a key

## Supported use cases

- Business questions requiring structured data only (`SQL` route)
- Contract and document questions requiring text retrieval (`PDF` route)
- Mixed questions requiring both database lookup and document evidence (`HYBRID` route)
- Questions outside the available corpus (`NONE` route)
- Hebrew and right-to-left document handling

## Example questions and expected routes

| Question | Route | Outcome |
|---|---|---|
| What is the total outstanding invoice amount per customer? | SQL | Structured data answer with row citations |
| What do our contracts say about service suspension? | PDF | Document retrieval answer with contract citations |
| Which customers have overdue invoices, and what do their agreements say about service suspension? | HYBRID | SQL-driven candidate selection plus contract evidence |
| What contracts expire in the next 90 days, and what penalties do they define? | HYBRID | Date-filtered DB results + contract clause retrieval |
| מה אומר ההסכם של תבור מערכות על השעיית שירות וקנסות? | PDF | Hebrew document retrieval and answer generation |
| What is our employee headcount in Berlin? | NONE | Insufficient evidence response |

## Extension points

### Adding a new source
- Implement the `Source` interface in `app/sources/`
- Add a new source instance to the source registry
- The router can classify it as relevant via its `describe()` metadata
- The orchestrator can route hybrid or multi-source queries without pipeline changes

### Swapping LLM providers
- Change `ABA_LLM_PROVIDER` to `openai` or `anthropic`
- Configure provider-specific key and base URL settings
- The provider-agnostic client layer supports OpenAI-compatible endpoints and Anthropic

### Using Qdrant
- Enable the Qdrant profile in Docker Compose
- Set `ABA_VECTOR_BACKEND=qdrant`
- This changes document vector storage while preserving the retrieval pipeline

### Production considerations
- Add authentication and authorization around API routes
- Add secrets management for API keys
- Add rate limiting and request logging
- Add monitoring and health checks beyond the built-in API health endpoint

## Notes for AI agents

- Treat the app as an orchestration engine, not a simple document chatbot
- Focus on the routing decision before retrieval
- Use the trace and evidence objects to explain answers
- Preserve the distinction between `PDF`, `SQL`, `HYBRID`, and `NONE` responses
- When recommending extensions, verify that new sources implement the `Source` interface
- Do not assume data outside the committed sample store

## Useful references
- `README.md` — project overview and quickstart
- `docs/overview.md` — system overview with screenshots and example flows
- `docs/architecture.md` — architecture deep dive and rationale
- `docker-compose.yml` — service topology, environment variables, and profiles
- `Dockerfile` — backend image build and runtime behavior
- `.env.example` — environment configuration templates

## Summary

This project is a demonstration of a business knowledge assistant built around:
- source-aware routing
- hybrid structured/document retrieval
- grounded answer generation
- citation verification and traceability

The architecture is intentionally modular and extensible, with a single `Source` interface enabling future additions such as CRM, email, or cloud storage without rewriting the core pipeline.
