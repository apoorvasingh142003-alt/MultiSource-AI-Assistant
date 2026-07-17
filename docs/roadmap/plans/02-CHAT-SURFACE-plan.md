# Phase 2 — The ChatGPT-class chat surface (plan)

Status: **shipped** — 2026-07-17.

## Goal (from roadmap)

The "sexy, modern, ChatGPT-like" UI: a clean chat + a separate inspector/artifacts
side panel. Streaming answers, threads, in-chat attachments, user-defined instructions
in place of the 13-persona picker. Exit criteria: *it feels like ChatGPT; chat is clean,
the inspector is one panel away, streaming is smooth.*

## Locked decisions honored

- **Tri-state grounding wall stays sacred.** The backend-computed `answer_state`
  (`grounded` / `reasoned` / `insufficient`) is still the *only* source of the label.
  In the clean chat we render a compact, unmistakably-colored state chip on every
  assistant message (never a neutral/positive look for ungrounded), and the full
  `AnswerStateBanner` lives in the inspector's Answer tab. The three states never blend.
- **Keep backend + design tokens.** No backend contract change. Style only with the
  semantic token classes (`text-fg`, `bg-surface`, `border-line`, …).
- **Offline determinism** — no new runtime deps that break the keyless path; `scripts/eval.py`
  and the test suite must stay green (this phase is UI-only on the Python side).

## Stack decision (deviation, approved)

The backlog names *assistant-ui + Vercel AI SDK*. After reading the code, the backend
`/ask/stream` uses a **custom SSE protocol** whose final `done` event carries the entire
rich `Trace` (routing, evidence, SQL, citations, verification, `answer_state`) — that
payload *is* the product. Adopting the AI SDK's data-stream protocol would mean rewriting
proven, tested streaming for no user-visible gain. The exit criteria are a UX outcome, and
the library is **not** in the README's locked decisions.

**Approved approach (user: "choose what is best, looks super sexy"):** rebuild the *shell*
into a polished ChatGPT layout on the existing, proven custom SSE transport and the existing
rich rendering. Deliver the ChatGPT feel; skip the library churn.

## The new layout

```
┌ ChatSidebar ┐┌──────────── main (clean chat) ────────────┐┌ InspectorPanel ┐
│ threads     ││ slim header (brand · model · customize ·  ││ slide-in drawer │
│ history     ││   inspect · settings · account)           ││ tabs:           │
│ new chat    ││ ─────────────────────────────────────────  ││  Answer         │
│             ││ chat thread (bubbles, streaming, state chip)││  Trace          │
│             ││ ─────────────────────────────────────────  ││  Evidence       │
│             ││ composer (attach 📎 · customize · send)    ││  Sources        │
└─────────────┘└───────────────────────────────────────────┘└─────────────────┘
```

- **Chat stays clean**: each assistant turn shows the answer text (with clickable `[eN]`
  citations), a compact tri-state chip, source chips, and light actions
  (Inspect · Copy · Regenerate). The heavy detail moves off the message.
- **Inspector = one panel away**: a right-side drawer (toggle in header, or "Inspect" on a
  message, or clicking a citation). Tabs:
  - **Answer** — the full `AnswerStateBanner` + answer + citations + supporting evidence
    (reuses `AnswerPanel` content).
  - **Trace** — routing, SQL, hybrid retrieval, cost/timings (reuses `Inspector` content).
  - **Evidence** — every retrieved passage/row (reuses `EvidenceItem`).
  - **Sources** — uploaded PDFs/DBs + upload dropzones (reuses `Workspace` rows). Replaces
    the old top-level "Workspace" tab.
- The top nav tabs (Chat/Workspace/Studio/Inspector) are **removed**. Studio (`WorkspaceView`)
  is off the demo path → dropped from the surface (files kept in repo, per "cut, don't delete").

## In-chat attachments

- A 📎 attach button in the composer opens the PDF file picker → `POST /ingest/pdf` (existing
  `ingestPdf`). Selected files show as chips with an ingesting/indexed/error state; on success
  the inventory refreshes and a system note confirms in the thread. SQLite upload stays in the
  Sources tab (drag-drop), keeping the composer focused on documents like ChatGPT.

## Custom instructions (replaces the persona picker)

- Remove the 13-entry `PRESET_ROLES` dropdown from the UI. Add a ChatGPT-style **Customize**
  popover (from the composer + header) with two free-text fields:
  - *Role* — "Respond as a … " (maps to existing `agent_role`).
  - *Instructions* — "How should the assistant respond?" (maps to existing
    `custom_system_prompt`).
  - Plus the output-format select + temperature (kept, already backend-wired).
- Backend already accepts free-text `agent_role` + `custom_system_prompt`; **no backend
  change**. `app/roles.py` stays (still used as a default label), just no longer surfaced as a
  13-persona chooser.

## Files

New:
- `ui/components/InspectorPanel.tsx` — the slide-in drawer with the four tabs.
- `ui/components/CustomizePanel.tsx` — ChatGPT-style instructions/role/output popover.
- `ui/components/Composer.tsx` — composer with attach + customize + send (extracted from page).

Changed:
- `ui/app/page.tsx` — new shell: sidebar + clean chat + inspector drawer; remove top tabs;
  wire attach, customize, inspector open/close + active tab + selected turn.
- `ui/components/ChatThread.tsx` — slim assistant messages: answer text + state chip + source
  chips + Inspect/Copy/Regenerate; streaming stays smooth; clicking a citation or Inspect opens
  the drawer. Add `onInspect(turn, tab)` + `onCite` callbacks.
- `ui/components/AiSettingsPanel.tsx` — drop `PRESET_ROLES` picker; keep the settings store and
  `resolveOutput`; role/instructions become free-text (consumed by CustomizePanel + SettingsPanel).
- `ui/components/SettingsPanel.tsx` — replace the role dropdown with a free-text default role.
- `CLAUDE.md` — note the Phase-2 shell (clean chat + inspector drawer) once shipped.

Reused as-is: `AnswerPanel`, `AnswerStateBanner`, `trace.tsx`, `Inspector`, `Workspace` rows,
`ui.tsx` primitives, `lib/api.ts` (`askStream`, `ingestPdf`, sessions).

## Exit criteria checklist

- [x] Clean ChatGPT-style chat surface; streaming smooth; state chip on every message.
- [x] Inspector is a single slide-in panel with Answer · Trace · Evidence · Sources tabs.
- [x] In-chat PDF upload → `/ingest/pdf`, with visible ingest state + system note in the thread.
- [x] 13-persona picker replaced by user-defined role + instructions (ChatGPT-style CustomizePanel).
- [x] Threads/history wired to `/sessions` (kept working — sidebar unchanged).
- [x] `tsc --noEmit` + `next build` clean (via the /home clone workflow).
- [x] Tri-state wall intact; `scripts/eval.py` (11/12, unchanged baseline) + pytest (169 passed) green.
- [x] Verified on the production image (auth ON): streaming token frames, tri-state `answer_state`
      across grounded/general-knowledge/decline, in-chat upload → grounded cited answer. Live site
      loads + `/health` green at https://assistant.lazysnail.xyz/. (The public `/ask` edge strips the
      bearer header for a scripted client, so the authed API was exercised directly against the same
      running container; the browser flow uses the NextAuth-minted JWT.)

## Verification notes

- **Build:** `tsc --noEmit` exit 0; `next build` compiled + 4/4 pages generated, page bundle ~32 kB.
- **Backend:** `pytest -q` → 169 passed, 10 skipped. `scripts.eval` → 11/12 (pre-existing baseline;
  no Python files changed this phase).
- **Live/API (production image, auth ON):**
  - Grounded: "how many customers…" → `grounded`, route `SQL`, 6 citations, 64 streamed frames.
  - Reasoned: "SaaS renewal best practices" → labeled, route `GENERAL_KNOWLEDGE`, 357 frames.
  - Decline: "revenue on the Mars colony 2019" → honest not-found, route `HYBRID`.
  - Upload: minimal PDF → `indexed` (1 chunk) → asked → `grounded`, 1 citation, with the Phase-1
    low-parse-confidence caveat preserved. Synthetic verify tenants reset afterward.
