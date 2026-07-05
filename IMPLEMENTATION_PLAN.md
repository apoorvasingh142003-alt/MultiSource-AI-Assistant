# Implementation Plan — Grounding-First Robustness + UI Trust Upgrade

**Branch:** `enterprise-upgrade` · **Status:** implemented & verified (see `task.md`).

**Goal of this round:** make the assistant **safe and dependable on a weak local model**.
A local Ollama run (`qwen2.5:7b-instruct`) routed a document-answerable question to
`GENERAL_KNOWLEDGE` and **fabricated** medications/staff that contradicted the uploaded
nursing-home PDF. This round makes grounding unconditional, hardens routing for small models,
makes the UI tell the truth loudly, and adds an adversarial test + red-team suite — without
regressing the API path, the 56-test baseline, or the flagship HYBRID demo (evidence = 9).

Full incident write-up + side-by-side fabrication table: `docs/grounding-first-fix.md`.

---

## 1. Root cause

A **routing-trust** problem, not a transport problem. Ollama already runs through the
unified OpenAI-compatible client (`app/llm/client.py`); the weakness is the *model*. The weak
7B router returned `GENERAL_KNOWLEDGE` (confidence 0.4), and the orchestrator had a parametric
escape hatch reachable whenever the only guard — a single-token `_on_topic()` lexical check —
dropped the recovered evidence. So a weak router could bypass retrieval and answer from
training data. **LangChain/ChatOllama would not fix this** (it does not improve structured-output
quality); the fix is architectural.

## 2. Backend — grounding-first guarantee

| ID | Area | Key files |
|----|------|-----------|
| G1 | `_on_topic()` widened (single passage → any of top-3 share a content word); honest decline preserved | `routing/orchestrator.py` |
| G2 | `GENERAL_KNOWLEDGE` parametric branch gated behind a real in-scope document search; never overrides on-topic evidence; loud disclaimer prepended; `hallucination_risk_score` 0.3 → 0.5 | `routing/orchestrator.py` |
| G3 | `_coerce_route()` — tolerant of malformed/partial 7B JSON (clamp confidence, validate enum, fill from rule layer) | `routing/classify.py` |
| G4 | One retry on malformed/low-confidence routing; rule-vs-LLM reconciliation (low-conf `GENERAL_KNOWLEDGE`/`NONE` → grounded route, never the reverse); `NONE→GK` upgrade moved after reconciliation | `routing/classify.py` |
| G5 | `router_low_confidence_threshold` (0.6), `router_rule_override` (True); `local_model` default aligned to `qwen2.5:7b-instruct` | `config.py` |
| G6 | Advice/recommendation questions → two-part **grounded context + disclaimed general guidance** (never fabricate, never bare-decline); subject resolved from conversation history | `retrieval/intent.py`, `generation/generate.py`, `routing/orchestrator.py` |

**Determinism preserved.** All new router logic is gated behind `use_live_llm` + `call.mode ==
"live"`, so offline/cached paths (the entire deterministic test suite) are byte-identical.
Reconciliation only ever *downgrades toward grounding*; it cannot push a question to the
parametric path.

## 3. Frontend — trust correctness + visual polish (`ui/`)

| ID | Area | Key files |
|----|------|-----------|
| U1 | `GENERAL_KNOWLEDGE` → prominent amber/rose "not grounded" warning banner (was a subtle blue info line); surface risk % | `components/AnswerPanel.tsx`, `components/VerificationBadge.tsx` |
| U2 | Confidence relabelled as **router** confidence (+ tooltip): it is not answer correctness | `components/AnswerPanel.tsx` |
| U3 | Historical turns show a "not re-verified" indicator (never indistinguishable from a verified answer) | `components/ChatThread.tsx` |
| U4 | Truncation indicators for capped SQL rows / compact evidence | `components/trace.tsx` |
| U5 | Visual polish: spacing/typography, cohesive light+dark palette, refined bubbles/composer/pills, clearer states, header, explainability legibility | `app/globals.css`, `components/ui.tsx`, panels |

The backend prepends the parametric disclaimer to the answer text; the UI renders it
prominently. Constraint: only fields already in `ui/lib/types.ts`; `tsc --noEmit` + `next
build` stay clean.

## 4. Local-model robustness (no LangChain migration)

Transport unchanged (`runtime.set_model_mode` keeps the OpenAI-compatible Ollama path). The
robustness layer (§2) is what makes a 7B route dependably. `langchain`/`langgraph` stay only
for the optional iterative agent. Bump the model via `ABA_LOCAL_MODEL` (e.g.
`qwen2.5:14b-instruct`) for stronger routing on more RAM.

## 5. Tests & verification

- `tests/test_grounding_first.py` (new) — forced-`GENERAL_KNOWLEDGE` still grounds in the PDF;
  no fabricated values; out-of-scope is declined or loudly disclaimed.
- `tests/test_router_robustness.py` (new) — `_coerce_route` survives garbage; low-conf GK
  reconciles to grounded; confident GK respected.
- `tests/test_nursing_home_red_team.py` (new) — adversarial Q&A over the real PDF: correct
  grounded facts, never-fabricate invariant, out-of-scope declines.
- `scripts/eval.py` — grounding-first regression line added; flagship HYBRID stays at ev = 9.
- **Suite: 108 passed, 10 skipped** (was 56/10). `scripts/eval.py` 10/10. UI `tsc` + `next
  build` clean. Live local-mode E2E: meds question grounds (Donepezil 10 mg, Metformin,
  Lisinopril, Acetaminophen, Vitamin D); "capital of France" answers with the loud disclaimer.

---

# Next Round (PLANNED — not yet built) — Enterprise Multi-Tenant Platform + Channels & CRM

**Status:** design locked with user 2026-07-05; implementation not started. Scoped via a
requirements discussion; all decisions below are confirmed. Target: **full enterprise-grade
wherever possible**, portable to cloud but runnable today on the local Docker stack.

## N0. Objectives

Turn the single-workspace assistant into a **multi-tenant, authenticated product** reachable at
a **permanent public URL**, with **two-way messaging channels** and **CRM + Sheets as grounded
data sources** — one isolated workspace per signed-in user.

## N1. Public access — permanent URL (no impact on the quiz site)

| ID | Decision | Notes |
|----|----------|-------|
| P1 | Serve at **`assistant.lazysnail.xyz`** (subdomain, not a path) | DNS is on **Cloudflare**; add one CNAME/route for a **Named Tunnel** — fully isolated from the client's quiz site at the apex. Zero changes to existing config. |
| P2 | Replace the ephemeral `trycloudflare.com` quick tunnel with a **Cloudflare Named Tunnel** (credentialed, stable hostname) | Permanent URL that fronts the **local Docker stack**; live whenever the scripts are run, down when the machine/tunnel is off (accepted). Cloud/always-on is a later, drop-in step. |
| P3 | Wire the named tunnel into `docker-compose.yml` + a `scripts/tunnel.sh`/`local-model.sh` update | Tunnel token via env/secret, not committed. |

## N2. Authentication & multi-tenancy

| ID | Decision | Notes |
|----|----------|-------|
| A1 | **Google (Gmail) sign-in**, **open signup** — any Google account auto-provisions its **own isolated workspace** | NextAuth (Auth.js) Google provider on the `ui/` side; backend verifies the session/JWT. |
| A2 | Request **Google Sheets read-only scope at sign-in** (reuse the login) | Single consent screen → token stored per user; used by the Sheets data source (N4). |
| A3 | **Per-tenant isolation** on every data path: `user_id` on sessions, messages, uploads, connections; **per-user vector namespaces**; per-user document scopes | No cross-tenant leakage — enforced in retrieval, SQL, and cache keys. |
| A4 | **Encrypted per-user secret storage** for all OAuth/channel tokens (Google, HubSpot, WhatsApp/Telegram links) | App-level encryption (e.g. Fernet/KMS-ready); tokens never logged. |

## N3. Data store — enterprise-grade

| ID | Decision | Notes |
|----|----------|-------|
| D1 | **Migrate to PostgreSQL** (new `db` service in `docker-compose.yml`) for tenants, sessions, messages, connections, audit | Replaces the SQLite `sessions.db` for multi-user concurrency; demo `business.db` can stay as a per-tenant sample source. |
| D2 | **Background worker + queue** (e.g. Redis + RQ/Celery, or FastAPI background tasks to start) | For async webhook processing and outbound message sends with retry/backoff. |
| D3 | **Audit log** of auth events, connections, and channel messages | Enterprise traceability; per-tenant. |

## N4. Integrations (all API-based)

| ID | Integration | Direction / Auth | Notes |
|----|-------------|------------------|-------|
| I1 | **WhatsApp** — Meta **WhatsApp Cloud API** | **Two-way**. One shared business number; inbound webhook → resolve tenant via **link code**; outbound via **approved message templates** | Provider kept behind an interface for portability. |
| I2 | **Telegram** — single **BotFather** bot | **Two-way**. `/start <code>` deep-link maps a chat to a workspace; inbound webhook, outbound via Bot API | Simplest channel; good first channel to ship. |
| I3 | **Channel linking** — **shared bot + one-time link code** | Signed-in user generates a code in-app, sends it from their WhatsApp/Telegram → chat bound to their tenant | Scales to open signup; no per-user number/bot setup. |
| I4 | **HubSpot CRM** — HubSpot **REST API**, its **own OAuth** ("Connect HubSpot" in settings) | **Read-only data source** (contacts, deals, companies) merged into retrieval + grounding | Separate from Google — cannot ride the Gmail login. |
| I5 | **Google Sheets** — Google **Sheets API**, scope from the **Gmail sign-in** (N-A2) | **Read-only data source** (user points at a sheet/range) merged into retrieval | Grounded + cited like PDFs/SQL. |

All four surface as **new grounded sources** in the existing retrieval pipeline, so the
grounding-first guarantee (this round's §2) and citations apply to CRM/Sheets answers too.
Inbound channel messages run the **same** orchestrator, so WhatsApp/Telegram replies are
grounded and cited exactly like the web UI.

## N5. Sequencing (proposed)

1. **Auth + multi-tenancy + Postgres** (foundation; everything else depends on `user_id`).
2. **Named tunnel → `assistant.lazysnail.xyz`** (get the permanent URL live early for OAuth redirects).
3. **Telegram** (fastest two-way channel) → validate the shared-bot + link-code model.
4. **Google Sheets** (read source; reuses the login scope) → **HubSpot** (own OAuth).
5. **WhatsApp Cloud API** (heaviest onboarding: Meta verification + templates).
6. Harden: worker/queue, encryption, audit, rate-limit/retry, per-tenant eval.

**Open items to confirm before build:** encryption/secret backend choice, worker/queue choice
(Redis vs in-process to start), and whether outbound WhatsApp templates are needed at launch or
inbound-reply-only first.

---

## Appendix — previous round (enterprise agentic-chat upgrade)

The prior round turned the single-shot RAG engine into a ChatGPT-like **agentic, multi-turn,
streaming** assistant: per-request temperature, multi-turn conversation context, message
edit/delete/regenerate, real token streaming, an optional LangGraph iterative agent (wrapping
the existing sources as tools), structure-aware semantic chunking, German multilingual
showcase, a single settings store, and a merged Output control. That work remains intact and
unregressed; this round is additive on top of it.
