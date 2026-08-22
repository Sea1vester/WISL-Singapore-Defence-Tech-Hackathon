#!/usr/bin/env bash
set -Eeuo pipefail

# Laptop B hosts processing and replay: Ollama, Docker API/worker, C++ viewer.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$PROJECT_DIR/.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
START_TIMEOUT="${START_TIMEOUT:-180}"
COMPOSE_BUILD="${COMPOSE_BUILD:-1}"
LAUNCH_REPLAY="${LAUNCH_REPLAY:-1}"
API_KEY="${API_KEY:-${INGEST_API_KEYS:-dev-teammate-key-change-me}}"

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
  TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | awk 'NR == 1 {print; exit}')"
fi

log "Stack is ready at ${BASE_URL%/}"
if [[ -n "$TAILSCALE_IP" ]]; then
  log "Laptop A URL: http://${TAILSCALE_IP}:8000"
else
  log "No Tailscale IPv4 address found. Use the same-laptop localhost fallback."
fi

if [[ "$LAUNCH_REPLAY" == "1" ]]; then
  replay_bin="$REPO_ROOT/sdth-replay/build/sdth-replay"
  if [[ ! -x "$replay_bin" ]]; then
    if command -v cmake >/dev/null 2>&1; then
      log "Building sdth-replay"
      cmake -S "$REPO_ROOT/sdth-replay" -B "$REPO_ROOT/sdth-replay/build" -DSDTH_REPLAY_BUILD_APP=ON
      cmake --build "$REPO_ROOT/sdth-replay/build" --target sdth-replay
    else
      log "cmake not found; open the offline demo later with a prebuilt binary"
      replay_bin=""
    fi
  fi
  if [[ -x "$replay_bin" ]]; then
    log "Launching C++ replay against ${BASE_URL%/}"
    exec "$replay_bin" --latest --api "${BASE_URL%/}" --token "$API_KEY"
  fi
fi

log "Follow logs with: docker compose --project-directory \"$PROJECT_DIR\" logs -f"
