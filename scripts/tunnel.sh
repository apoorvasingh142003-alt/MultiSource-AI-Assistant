#!/usr/bin/env bash
#
# tunnel.sh — bring the app up on its PERMANENT public URL via a Cloudflare
# Named Tunnel (token-based). Unlike the quick trycloudflare.com tunnel, the
# hostname is stable (e.g. https://assistant.lazysnail.xyz) and is live whenever
# this stack runs. DNS for that subdomain is managed by Cloudflare, so nothing
# at the zone apex (e.g. an existing site on the same domain) is affected.
#
#   ./scripts/tunnel.sh          # start the named tunnel (needs the stack + token)
#   ./scripts/tunnel.sh --down   # stop just the tunnel
#
# ── ONE-TIME SETUP (Cloudflare dashboard — needs your Cloudflare account) ──────
#   1. https://one.dash.cloudflare.com → Networks → Tunnels → "Create a tunnel"
#        → connector: "Cloudflared" → name it (e.g. "msaa") → Save.
#   2. On the "Install connector" screen, COPY THE TOKEN (the long string after
#        `--token`). You do NOT run the shown command — this script runs it in Docker.
#   3. Open the tunnel → "Public Hostname" tab → "Add a public hostname":
#        Subdomain:  assistant
#        Domain:     lazysnail.xyz
#        Path:       (leave empty)
#        Service:    Type = HTTP    URL = ui:3000
#        Save.  (Cloudflare auto-creates the proxied DNS record — apex untouched.)
#   4. Put the token in .env next to this repo:
#        CLOUDFLARE_TUNNEL_TOKEN=eyJ...   (git-ignored; never commit it)
#
# After that, `./scripts/tunnel.sh` is all you need on every run.
#
# NOTE: until Google sign-in / auth ships (next build phase), this URL is OPEN to
# anyone who has it — same as the quick tunnel. Optionally gate it with Cloudflare
# Access in the meantime.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

log() { printf '\033[36m[tunnel]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[tunnel] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${1:-}" == "--down" ]]; then
  log "Stopping the named tunnel..."
  docker compose --profile named-tunnel stop named-tunnel >/dev/null 2>&1 || true
  docker compose --profile named-tunnel rm -f named-tunnel >/dev/null 2>&1 || true
  log "Named tunnel stopped."
  exit 0
fi

# Load .env if present so we can validate the token.
[[ -f .env ]] && set -a && . ./.env && set +a || true

if [[ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  die "CLOUDFLARE_TUNNEL_TOKEN is not set in .env — complete the one-time setup in this file's header first."
fi

# The tunnel routes to ui:3000 on the compose network, so the app must be up.
if ! docker compose ps --status running ui >/dev/null 2>&1 || \
   ! curl -sf --max-time 3 http://localhost:3000 >/dev/null 2>&1; then
  log "App UI not detected on :3000 — bringing the stack up first..."
  docker compose up -d
  for _ in $(seq 1 30); do curl -sf --max-time 2 http://localhost:3000 >/dev/null 2>&1 && break; sleep 2; done
fi

log "Starting the Cloudflare Named Tunnel..."
docker compose --profile named-tunnel up -d named-tunnel

sleep 4
log "Tunnel container status:"
docker compose --profile named-tunnel ps named-tunnel

log "Recent tunnel log lines (look for 'Registered tunnel connection'):"
docker compose --profile named-tunnel logs --tail 15 named-tunnel 2>&1 | sed 's/^/    /'

cat <<'EOF'

[tunnel] Done. If connections registered above, your app is live at the public
[tunnel] hostname you configured (e.g. https://assistant.lazysnail.xyz).
[tunnel] Stop it any time with:  ./scripts/tunnel.sh --down
EOF
