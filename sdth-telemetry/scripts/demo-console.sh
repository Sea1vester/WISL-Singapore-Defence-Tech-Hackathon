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
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-deepseek-r1:7b}"
export LOCAL_DEMO_WORKER=true
export INGEST_MODEL_ENRICHMENT=false
export REPLAY_STATIC_DIR="$TASK_ROOT/sdth-replay/public"
export API_HOST=127.0.0.1
export API_PORT="${API_PORT:-8010}"
# The existing API key is entered in the console, never embedded in the page.
export INGEST_API_KEYS="${INGEST_API_KEYS:-dev-teammate-key-change-me}"
printf 'WISL console: http://127.0.0.1:%s/demo/\n' "$API_PORT"
printf 'Local demo only. Enter your INGEST_API_KEYS value in the console connection panel.\n'
cd "$TASK_ROOT/sdth-telemetry/platform-api"
exec "$TASK_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
