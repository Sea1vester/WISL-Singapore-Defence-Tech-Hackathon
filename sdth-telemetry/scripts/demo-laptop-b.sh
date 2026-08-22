#!/usr/bin/env bash
set -Eeuo pipefail

# Laptop B hosts processing and replay: Ollama, Docker API/worker, Cesium viewer.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
START_TIMEOUT="${START_TIMEOUT:-180}"
COMPOSE_BUILD="${COMPOSE_BUILD:-1}"
LAUNCH_REPLAY="${LAUNCH_REPLAY:-1}"
API_KEY="${API_KEY:-${INGEST_API_KEYS:-}}"

if [[ -z "$API_KEY" && -f "$PROJECT_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$PROJECT_DIR/.env"
  set +a
  API_KEY="${API_KEY:-${INGEST_API_KEYS:-dev-teammate-key-change-me}}"
fi
API_KEY="${API_KEY:-dev-teammate-key-change-me}"

log() { printf '[Laptop B processor] %s\n' "$*"; }
fail() { printf '[Laptop B processor] ERROR: %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + START_TIMEOUT))
  until curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      fail "$label did not become ready within ${START_TIMEOUT}s ($url)"
    fi
    sleep 2
  done
}

require_command curl
require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"
docker info >/dev/null 2>&1 || fail "Docker Desktop is not running"

if command -v ollama >/dev/null 2>&1; then
  if ! curl --fail --silent --max-time 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    log "Starting Ollama in the background"
    nohup ollama serve >"${TMPDIR:-/tmp}/wisl-ollama.log" 2>&1 &
  fi
  wait_for_url "$OLLAMA_URL/api/tags" "Ollama"
  if ! ollama list | awk 'NR > 1 {print $1}' | cut -d: -f1 | grep -qx 'deepseek-r1'; then
    log "Pulling deepseek-r1:7b"
    ollama pull deepseek-r1:7b
  fi
else
  log "Ollama not installed. Replay and detection still work; report enrichment will degrade."
fi

compose_args=(up --detach)
if [[ "$COMPOSE_BUILD" == "1" ]]; then
  compose_args+=(--build)
fi

log "Starting API, Redis, and worker"
docker compose --project-directory "$PROJECT_DIR" "${compose_args[@]}"
wait_for_url "${BASE_URL%/}/health" "Telemetry API"

TAILSCALE_IP=""
if command -v tailscale >/dev/null 2>&1; then
  TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | awk 'NR == 1 {print; exit}' || true)"
fi

log "Stack is ready at ${BASE_URL%/}"
if [[ -n "$TAILSCALE_IP" ]]; then
  log "Laptop A URL: http://${TAILSCALE_IP}:8000"
else
  log "No Tailscale IPv4 address found. Use the same-laptop localhost fallback."
fi

if [[ "$LAUNCH_REPLAY" == "1" ]]; then
  token_q="$(
    python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$API_KEY"
  )"
  replay_url="${BASE_URL%/}/replay/?token=${token_q}&latest=1"
  log "Opening Cesium replay at ${replay_url}"
  if command -v open >/dev/null 2>&1; then
    open "$replay_url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$replay_url" >/dev/null 2>&1 || true
  fi
fi

log "Follow logs with: docker compose --project-directory \"$PROJECT_DIR\" logs -f"
