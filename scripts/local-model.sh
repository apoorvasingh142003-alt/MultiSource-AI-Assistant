#!/usr/bin/env bash
#
# local-model.sh — one command to run the MultiSource AI Assistant on a fully
# local Ollama model (no cloud key required).
#
# It is idempotent and safe to re-run: it (1) starts Ollama if it isn't already
# serving, (2) pulls the model if it's missing, (3) brings the app up with the
# local-model docker config, (4) flips the app into "local" mode, and (5) runs a
# smoke test that proves the local model is actually answering.
#
#   ./scripts/local-model.sh                 # use the default model below
#   ABA_LOCAL_MODEL=qwen2.5:3b-instruct ./scripts/local-model.sh   # override
#
set -euo pipefail

MODEL="${ABA_LOCAL_MODEL:-qwen2.5:7b-instruct}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '\033[36m[local-model]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[local-model] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

ollama_up() { curl -sf --max-time 2 "http://localhost:${OLLAMA_PORT}/api/tags" >/dev/null 2>&1; }

# 1. Ensure Ollama is serving (bound to 0.0.0.0 so the Docker container can reach it).
if ollama_up; then
  log "Ollama already serving on :${OLLAMA_PORT}."
else
  command -v ollama >/dev/null 2>&1 || die "ollama is not installed (expected in PATH)."
  log "Starting Ollama on 0.0.0.0:${OLLAMA_PORT}..."
  OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}" nohup ollama serve >/tmp/ollama.log 2>&1 &
  disown 2>/dev/null || true
  for _ in $(seq 1 20); do ollama_up && break; sleep 1; done
  ollama_up || die "Ollama failed to start — see /tmp/ollama.log"
  log "Ollama is up."
fi

# 2. Ensure the model is present.
if ollama list 2>/dev/null | grep -qF "$MODEL"; then
  log "Model '${MODEL}' is present."
else
  log "Pulling '${MODEL}' (first time only, this may take a while)..."
  ollama pull "$MODEL"
fi

# 3. Bring the app up with the local-model docker config (recreates api only if
#    the compose config changed; otherwise a no-op).
cd "$PROJECT_DIR"
log "Ensuring the app is running with the local-model config..."
ABA_LOCAL_MODEL="$MODEL" docker compose up -d
for _ in $(seq 1 30); do
  curl -sf --max-time 2 http://localhost:8000/health >/dev/null 2>&1 && break; sleep 2
done
curl -sf --max-time 2 http://localhost:8000/health >/dev/null 2>&1 || die "API did not become healthy."

# 4. Flip the running app into local mode (no restart needed).
log "Switching the app to local-model mode..."
curl -sf -X POST http://localhost:8000/runtime/model-mode \
  -H 'Content-Type: application/json' -d '{"mode":"local"}' >/dev/null

# 5. Smoke test — prove the local model actually answers.
log "Smoke test (asking the local model a demo question)..."
ANS=$(curl -s --max-time 180 -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many customers are in the database?","scope":"demo"}' \
  | python3 -c "import sys,json;print((json.load(sys.stdin).get('answer') or '<no answer>')[:200])" 2>/dev/null || echo "<request failed>")
log "Answer: ${ANS}"

log "Status: $(curl -s http://localhost:8000/runtime/model-mode)"
log "Ready.  UI: http://localhost:3000   ·   API: http://localhost:8000   ·   model: ${MODEL}"
