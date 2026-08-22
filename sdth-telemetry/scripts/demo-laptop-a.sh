#!/usr/bin/env bash
set -Eeuo pipefail

# Laptop A simulates the controller: watch a directory and upload raw logs
# to Laptop B over Tailscale. Same-laptop fallback: BASE_URL=http://localhost:8000

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
INGEST_DIR="$REPO_ROOT/sdth-ingestion pipeline"
WATCH_DIR="${WATCH_DIR:-$REPO_ROOT/sdth-telemetry/demo-watch}"
BASE_URL="${BASE_URL:-}"
API_KEY="${API_KEY:-${INGEST_API_KEYS:-${WISL_UPLOAD_KEY:-}}}"
INTERVAL="${INTERVAL:-2}"
ONCE="${ONCE:-0}"

log() { printf '[Laptop A controller] %s\n' "$*"; }
fail() { printf '[Laptop A controller] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: API_KEY=... BASE_URL=http://<laptop-b-tailscale-ip>:8000 \
  ./scripts/demo-laptop-a.sh [raw-log-to-drop]

Drops an optional raw log into the watch directory, then uploads stable files
to Laptop B. Omit the file argument to watch an existing directory.

Same-laptop fallback:
  BASE_URL=http://localhost:8000 ONCE=1 ./scripts/demo-laptop-a.sh fixtures/demo/controller_mission_alpha.csv
EOF
}

[[ "${1:-}" != "-h" && "${1:-}" != "--help" ]] || { usage; exit 0; }
[[ -n "$BASE_URL" ]] || fail "BASE_URL is required (Laptop B Tailscale URL or http://localhost:8000)"
[[ -n "$API_KEY" ]] || fail "API_KEY is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"

BASE_URL="${BASE_URL%/}"
mkdir -p "$WATCH_DIR"

log "Checking Laptop B at $BASE_URL"
curl --fail --silent --show-error --max-time 10 "$BASE_URL/health" >/dev/null \
  || fail "Cannot reach $BASE_URL/health. Start Laptop B or use the localhost fallback."

if [[ $# -eq 1 ]]; then
  [[ -f "$1" ]] || fail "Raw log does not exist: $1"
  dest="$WATCH_DIR/$(basename -- "$1")"
  cp "$1" "$dest"
  log "Dropped $(basename -- "$1") into $WATCH_DIR"
fi

export PYTHONPATH="$INGEST_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export WISL_UPLOAD_KEY="$API_KEY"
args=(
  "$WATCH_DIR"
  --endpoint "$BASE_URL/v1/logs/upload"
  --interval "$INTERVAL"
)
if [[ "$ONCE" == "1" ]]; then
  log "One-shot upload from $WATCH_DIR"
  python3 -m wisl_ingest.edge.cli "${args[@]}"
else
  log "Watching $WATCH_DIR every ${INTERVAL}s"
  python3 -m wisl_ingest.edge.cli "${args[@]}" --watch
fi
