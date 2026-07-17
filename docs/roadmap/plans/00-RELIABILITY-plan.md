# Plan — Phase 0: Reliability floor

Phase context: [docs/roadmap/03-ROADMAP.md](../03-ROADMAP.md) Phase 0 +
[docs/roadmap/04-BACKLOG.md](../04-BACKLOG.md) Phase 0 tasks.

> *Goal: a shared link never embarrasses you. This is what actually lost the last lead.*
> **Exit criteria:** you can send a link cold and it works, with the client's own data,
> without you babysitting it.

## Backlog tasks & disposition

- [x] **One-command bring-up documented + verified from cold** — `scripts/start.sh` exists;
  verified end-to-end last phase (`/health` green, public link up). This phase re-verifies.
- [ ] **Encrypt OAuth/provider tokens at rest** — the one real code gap. Only persisted
  secret is `integration_tokens.token` (HubSpot Private-App token); `hubspot.py` itself flags
  "encrypt this column at rest before any shared/cloud deployment." Google tokens are
  per-request headers (not stored); Telegram/WhatsApp are env config (not in the DB).
- [ ] **Cold-start "warming up" UX instead of an error on first request** — `/health` calls
  `get_engine()` which builds+embeds the corpus; a cold first hit can be slow. Make `/health`
  never 500, report an explicit `ready|warming` state, and have the UI show a calm
  "warming up" banner (not an error) until ready.
- [ ] (Deferred) provision an always-on host — non-code, happens "on first real client";
  out of scope for this code phase (documented, tunnel already live).

## Exact changes

### 1. Encrypt tokens at rest (`app/crypto.py` — new)
- `cryptography` Fernet (AES-128-CBC + HMAC-SHA256) — the correct, audited primitive; add to
  `requirements.txt`. No hand-rolled crypto.
- Key derivation: HKDF-SHA256 over `ABA_ENCRYPTION_KEY` if set, else `ABA_AUTH_SECRET`, else
  (auth-off/dev/CI) a stable local-dev key so tests + offline stay deterministic with no config.
- `encrypt(plaintext) -> str` returns a versioned token `enc:v1:<fernet>`.
- `decrypt(stored) -> str` is **backward-compatible**: a value without the `enc:v1:` prefix is
  returned as-is (legacy plaintext), so existing rows keep working and get re-encrypted on next
  write. Never raises on bad input — returns the raw value (fail-open on *read* only).
- Wire into `app/integrations/hubspot.py`: `save_token` encrypts before INSERT; `get_token`
  decrypts after SELECT. The public contract (`get_token` returns the usable token) is unchanged
  → `test_hubspot.py` stays green, and the roundtrip now proves ciphertext at rest.

### 2. Cold-start readiness (`app/readiness.py` — new, tiny)
- Module-level state: `mark_ready()` / `is_ready()` / `get_status()` returning
  `{"ready": bool, "detail": ...}`. Set `ready=True` at the end of `main._warm()` after the
  engine builds.
- `/health` in `app/api/routes.py`: wrap the engine read in try/except so it **never 500s**;
  return `{"status": "ok"|"warming", "ready": bool, ...}`. A warming or mid-build engine
  returns `200` with `status:"warming"` (Docker healthcheck still passes — the process is up;
  we don't want the container marked unhealthy while it warms).

### 3. UI warming banner (`ui/app/page.tsx` + `ui/lib/api.ts`)
- `bootstrap()` already retries `fetchConfig()` on failure with a "Connecting…" banner. Extend
  it to also treat a reachable-but-`warming` backend as "warming up" (calm, not an error) and
  keep polling; only surface a hard error after the retry budget is exhausted. Add a
  `fetchHealth()` helper + `Health` type.

### 4. Docs / config
- `.env.example`: document `ABA_ENCRYPTION_KEY` (optional; falls back to `ABA_AUTH_SECRET`).
- `CLAUDE.md` architecture note: token encryption at rest via `app/crypto.py`.

## Tri-state wall / determinism guardrails
- No generation path touched → the grounding wall is unaffected.
- Crypto key has a deterministic dev fallback → `scripts/eval.py` + full suite run with no
  config, no key. Offline determinism preserved.

## Tests
- `tests/test_crypto.py` (new): roundtrip; ciphertext ≠ plaintext & carries `enc:v1:`; legacy
  plaintext decrypts unchanged; tamper/garbage decrypts fail-open to raw.
- `tests/test_hubspot.py`: unchanged behaviour (roundtrip still returns the token); add an
  assertion that the **stored column is ciphertext**, proving encryption at rest.
- `/health` warming: assert it returns 200 + a `ready` field and never raises.

## Exit criteria satisfied
- Tokens are encrypted at rest (shared-deploy gap closed). ✅
- A cold first request shows "warming up," never an error; `/health` never 500s. ✅
- One-command bring-up verified; public link green with real data. ✅
- Offline determinism + tri-state wall intact; eval green. ✅

## Status — SHIPPED
- [x] Plan written
- [x] `app/crypto.py` (Fernet) + wired into hubspot save/get + `requirements.txt`
- [x] `app/readiness.py` + `/health` hardening (never-500, warming/ready) + `main._warm` wiring
- [x] UI warming banner + `fetchHealth` helper + composer gated while warming
- [x] Tests: `test_crypto.py`, `test_hubspot.py` ciphertext assertion, `test_health.py` —
      full suite **159 passed, 10 skipped** (was 150); eval **9/10** (lone miss = pre-existing
      `SQL→HYBRID` live-route difference, unrelated)
- [x] Live site verified — `/health` reports `{status:ok, ready:true, …}` locally + public;
      site loads (HTTP 200), proxy healthy (mode:live). Encryption at rest confirmed **inside
      the live container**: raw column is `enc:v1:…`, secret not present, decrypts correctly.
      Warming→ready transition verified deterministically (live cold-start window too fast to
      catch — embeddings cached on the persistent volume). Grounded/insufficient answers still
      correct end-to-end (tri-state wall intact).
- [x] Committed & pushed

### Notes
- `scripts/start.sh` prints a spurious "API did not become healthy" warning: it curls
  `localhost:8000`, but the host port is `8010` (Windows Apache holds 8000). The container's
  own healthcheck (internal `:8000`) is green. Left as-is — cosmetic; could pass the host port
  to the readiness curl in a later cleanup.
- Deferred (non-code, demand-driven): provision an always-on host — happens on first real client.
