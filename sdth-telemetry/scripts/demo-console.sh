#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_PYTHON="${WISL_PYTHON:-$TASK_ROOT/.venv/bin/python}"
if [[ ! -x "$TASK_PYTHON" ]]; then
  TASK_PYTHON="${WISL_PYTHON:-python3}"
fi
# The existing API key is entered in the console, never embedded in the page.
exec "$TASK_PYTHON" "$TASK_ROOT/sdth-telemetry/scripts/demo-console.py" "$@"
