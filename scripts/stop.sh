#!/usr/bin/env bash
#
# stop.sh — stop the app and the Cloudflare tunnels (frees the ports).
#   ./scripts/stop.sh
#
# Ollama (if you started it with --local) keeps serving in the background; stop it with:
#   pkill ollama
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "[stop] Bringing down api, ui, and the tunnels..."
docker compose --profile named-tunnel --profile tunnel down
echo "[stop] Done. Start again with ./scripts/start.sh"
