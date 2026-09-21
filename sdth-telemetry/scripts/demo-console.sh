#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_PYTHON="${WISL_PYTHON:-$TASK_ROOT/.venv/bin/python}"
if [[ ! -x "$TASK_PYTHON" ]]; then
  TASK_PYTHON="${WISL_PYTHON:-python3}"
fi
export PYTHONPATH="$TASK_ROOT/sdth-telemetry/platform-api:$TASK_ROOT/sdth-telemetry${PYTHONPATH:+:$PYTHONPATH}"
export DATABASE_PATH="${DATABASE_PATH:-$TASK_ROOT/data/demo-console.db}"
export RAW_UPLOAD_DIR="${RAW_UPLOAD_DIR:-$TASK_ROOT/data/demo-uploads}"
export REPORTS_DIR="${REPORTS_DIR:-$TASK_ROOT/data/demo-reports}"
export VISUALS_DIR="${VISUALS_DIR:-$TASK_ROOT/data/demo-visuals}"
export TILE_CACHE_DIR="${TILE_CACHE_DIR:-$TASK_ROOT/data/tiles}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"
export LOCAL_DEMO_WORKER=true
export INGEST_MODEL_ENRICHMENT=false
export REPLAY_STATIC_DIR="$TASK_ROOT/sdth-replay/public"
if [[ ! -f "$TASK_ROOT/sdth-replay/public/cesium/Cesium.js" ]]; then
  if ! node "$TASK_ROOT/sdth-replay/scripts/fetch-cesium.cjs" >/dev/null 2>&1; then
    printf 'Cesium fetch failed; the replay will fall back to the cesium.com CDN.\n'
  fi
fi
export DEMO_STATIC_DIR="$TASK_ROOT/sdth-demo"
export API_HOST=127.0.0.1
export API_PORT="${API_PORT:-8010}"
# The existing API key is entered in the console, never embedded in the page.
export INGEST_API_KEYS="${INGEST_API_KEYS:-dev-teammate-key-change-me}"
DEMO_URL="http://127.0.0.1:${API_PORT}/demo/"
printf 'WISL console: %s\n' "$DEMO_URL"
printf 'Open that URL. http://127.0.0.1:%s/ and /replay/ redirect there.\n' "$API_PORT"
printf 'Local demo only. Enter your INGEST_API_KEYS value in the console connection panel.\n'
(
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if "$TASK_PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${API_PORT}/health', timeout=1)" >/dev/null 2>&1; then
      break
    fi
    sleep 0.4
  done
  if command -v open >/dev/null; then
    open "$DEMO_URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null; then
    xdg-open "$DEMO_URL" >/dev/null 2>&1 || true
  fi
) &
cd "$TASK_ROOT/sdth-telemetry/platform-api"
exec "$TASK_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
