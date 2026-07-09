#!/usr/bin/env bash
#
# start.sh — bring up EVERYTHING so the permanent link works:
#   the app (api + ui) + the permanent Cloudflare tunnel → https://assistant.lazysnail.xyz
#
#   ./scripts/start.sh            # app + permanent tunnel (uses the model configured in .env)
#   ./scripts/start.sh --local    # ALSO start the local Ollama model and switch to it
#   ./scripts/start.sh --build    # rebuild images first (run this after pulling code changes)
#
# Notes:
#   • Only the tunnels auto-restart after a reboot; api/ui do not — so run this to fix a 502.
#   • Stop everything with ./scripts/stop.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BUILD=""
LOCAL=0
for a in "$@"; do
  case "$a" in
    --build) BUILD="--build" ;;
    --local) LOCAL=1 ;;
    *) echo "unknown option: $a" >&2; exit 1 ;;
  esac
done

log() { printf '\033[36m[start]\033[0m %s\n' "$*"; }

# 1. App (api + ui). These have no restart policy, so they need starting after a reboot.
log "Starting the app (api + ui)${BUILD:+ with rebuild}..."
docker compose up -d $BUILD

# 2. Wait for the API to be healthy.
log "Waiting for the API to be healthy..."
for _ in $(seq 1 40); do
  curl -sf --max-time 2 http://localhost:8010/health >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -sf --max-time 2 http://localhost:8010/health >/dev/null 2>&1; then
  echo "[start] WARNING: API did not become healthy — check: docker compose logs api" >&2
fi

# 3. Permanent Cloudflare tunnel (only if a token is configured).
if grep -qE '^CLOUDFLARE_TUNNEL_TOKEN=.+' .env 2>/dev/null; then
  log "Starting the permanent Cloudflare tunnel..."
  docker compose --profile named-tunnel up -d named-tunnel
else
  log "No CLOUDFLARE_TUNNEL_TOKEN in .env — skipping the permanent tunnel."
fi

# 4. Optional: local Ollama model.
if [ "$LOCAL" -eq 1 ]; then
  log "Starting the local Ollama model + switching to local mode..."
  ./scripts/local-model.sh
fi

log "Ready."
echo "   Public : https://assistant.lazysnail.xyz"
echo "   Local  : http://localhost:3000   ·   API http://localhost:8010"
echo
docker compose --profile named-tunnel ps
