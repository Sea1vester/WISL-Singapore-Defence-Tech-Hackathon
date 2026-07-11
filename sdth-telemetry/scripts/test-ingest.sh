#!/usr/bin/env bash
set -euo pipefail

API_KEY="${INGEST_API_KEYS:-dev-teammate-key-change-me}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
FIXTURE="${FIXTURE:-fixtures/sample_l1.json}"

echo "Health:"
curl -s "$BASE_URL/health"
echo -e "\n\nIngest:"
PAYLOAD=$(python3 -c "
import json, time
p = json.load(open('$FIXTURE'))
p['event_id'] = f'evt-script-{int(time.time())}'
print(json.dumps(p))
")
RESP=$(curl -s -X POST "$BASE_URL/v1/telemetry/ingest" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")
echo "$RESP"

INGEST_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['ingest_id'])")
FLIGHT_ID=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['flight_id'])")

echo -e "\nPolling translation job..."
for _ in $(seq 1 60); do
  STATUS_JSON=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/v1/ingest/$INGEST_ID/status")
  STATUS=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  status=$STATUS"
  if [[ "$STATUS" == "done" || "$STATUS" == "failed" ]]; then
    echo "$STATUS_JSON"
    break
  fi
  sleep 3
done

if [[ "${STATUS:-}" == "done" ]]; then
  echo -e "\nCanonical records:"
  curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/v1/flights/$FLIGHT_ID/records"
  echo
fi
