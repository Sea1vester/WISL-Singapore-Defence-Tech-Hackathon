#!/usr/bin/env bash
set -Eeuo pipefail

# One-laptop demo: ingest the recorded controller logs and drive the full
# parse -> normalize -> detect -> report -> bulletin workflow.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-${INGEST_API_KEYS:-}}"
POLL_TIMEOUT="${POLL_TIMEOUT:-120}"
LAUNCH_REPLAY="${LAUNCH_REPLAY:-1}"
ALPHA="${ALPHA:-$PROJECT_DIR/fixtures/demo/controller_mission_alpha.csv}"
BRAVO="${BRAVO:-$PROJECT_DIR/fixtures/demo/controller_mission_bravo.csv}"

if [[ -z "$API_KEY" && -f "$PROJECT_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$PROJECT_DIR/.env"
  set +a
  API_KEY="${API_KEY:-${INGEST_API_KEYS:-}}"
fi

log() { printf '[local demo] %s\n' "$*" >&2; }
fail() { printf '[local demo] ERROR: %s\n' "$*" >&2; exit 1; }

json_value() {
  python3 -c '
import json, sys
data = json.load(sys.stdin)
value = data
for key in sys.argv[1].split("."):
    if not isinstance(value, dict) or key not in value:
        sys.exit(0)
    value = value[key]
if value is not None:
    print(value)
' "$1"
}

api() {
  curl --fail-with-body --silent --show-error \
    -H "Authorization: Bearer $API_KEY" \
    "$@"
}

upload_and_wait() {
  local file="$1"
  [[ -f "$file" ]] || fail "Missing demo log: $file"
  log "Uploading $(basename -- "$file")"
  local sha256
  sha256="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$file")"
  local response upload_id status flight_id deadline
  response="$(
    api -X POST \
      -H "X-WISL-SHA256: $sha256" \
      -F "file=@${file}" \
      "${BASE_URL%/}/v1/logs/upload"
  )"
  upload_id="$(printf '%s' "$response" | json_value upload_id)"
  [[ -n "$upload_id" ]] || fail "Upload did not return upload_id: $response"
  deadline=$((SECONDS + POLL_TIMEOUT))
  while :; do
    response="$(api "${BASE_URL%/}/v1/uploads/${upload_id}")"
    status="$(printf '%s' "$response" | json_value status)"
    flight_id="$(printf '%s' "$response" | json_value flight_id)"
    case "${status,,}" in
      ready) break ;;
      failed|error) fail "Processing failed for $(basename -- "$file"): $response" ;;
    esac
    if (( SECONDS >= deadline )); then
      fail "Timed out waiting for $(basename -- "$file") ($status)"
    fi
    log "  $(basename -- "$file"): $status"
    sleep 2
  done
  printf '%s\n' "$flight_id"
}

[[ -n "$API_KEY" ]] || fail "Set API_KEY or INGEST_API_KEYS in sdth-telemetry/.env"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

curl --fail --silent --show-error --max-time 5 "${BASE_URL%/}/health" >/dev/null \
  || fail "API is not reachable at ${BASE_URL%/}/health. Start ./scripts/demo-laptop-b.sh first."

alpha_id="$(upload_and_wait "$ALPHA")"
bravo_id="$(upload_and_wait "$BRAVO")"

log "Flight A: $alpha_id"
log "Flight B: $bravo_id"

alpha_path="$(api "${BASE_URL%/}/v1/flights/${alpha_id}/path")"
alpha_incidents="$(api "${BASE_URL%/}/v1/flights/${alpha_id}/incidents")"
alpha_report="$(api "${BASE_URL%/}/v1/flights/${alpha_id}/incident-report")"
patterns="$(api "${BASE_URL%/}/v1/incidents/patterns?min_flights=2")"
bulletin="$(
  api -X POST "${BASE_URL%/}/v1/mitigation-bulletins" \
    -H "Content-Type: application/json" \
    -d '{"signature":"operator_warning"}'
)"

python3 - "$alpha_path" "$alpha_incidents" "$alpha_report" "$patterns" "$bulletin" <<'PY'
import json, sys
path, incidents, report, patterns, bulletin = (json.loads(item) for item in sys.argv[1:])
print(f"[local demo] Path samples: {path.get('count')}")
types = {item.get("incident_type") for item in incidents.get("items", [])}
print(f"[local demo] Incidents: {', '.join(sorted(types)) or 'none'}")
print(f"[local demo] Report: {report.get('kind')} ({report.get('model_enrichment')})")
sigs = {item.get("signature") for item in patterns.get("items", [])}
print(f"[local demo] Recurring patterns: {', '.join(sorted(sigs)) or 'none'}")
print(f"[local demo] Bulletin: {bulletin.get('kind')} for {bulletin.get('signature')}")
print("[local demo] This bulletin is reviewable guidance, not a vehicle command.")
PY

if [[ "$LAUNCH_REPLAY" == "1" ]]; then
  token_q="$(
    python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$API_KEY"
  )"
  replay_url="${BASE_URL%/}/replay/?token=${token_q}&flights=${alpha_id},${bravo_id}"
  log "Opening Cesium replay for $alpha_id and $bravo_id"
  log "Replay: $replay_url"
  if command -v open >/dev/null 2>&1; then
    open "$replay_url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$replay_url" >/dev/null 2>&1 || true
  fi
fi

log "Ingest complete. Open replay with:"
log "  ${BASE_URL%/}/replay/?token=\$INGEST_API_KEYS&flights=${alpha_id},${bravo_id}"
