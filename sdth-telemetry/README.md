# SDTH Telemetry Platform

Mac-first drone telemetry platform: ingest normalized JSON from your teammate (via Tailscale), store in SQLite, translate to canonical JSON with local Ollama/DeepSeek.

## Quick start

### Prerequisites

- Docker Desktop
- Ollama on your Mac: `brew install ollama && ollama pull deepseek-r1:7b`
- Keep Ollama running (Docker worker calls `http://host.docker.internal:11434`)
- Tailscale (already set up)

### Run the stack

```bash
cd sdth-telemetry
cp .env.example .env
docker compose up --build
```

API listens on `http://0.0.0.0:8000` (reachable via Tailscale at `http://$(tailscale ip -4):8000`).

### Test ingest locally

Full E2E (ingest + poll translation + show canonical records):

```bash
./scripts/test-ingest.sh
```

Manual ingest:

```bash
curl -X POST http://localhost:8000/v1/telemetry/ingest \
  -H "Authorization: Bearer dev-teammate-key-change-me" \
  -H "Content-Type: application/json" \
  -d @fixtures/sample_l1.json
```

Check job status (use `ingest_id` from response):

```bash
curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  http://localhost:8000/v1/ingest/<ingest_id>/status
```

List flights and records:

```bash
curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  http://localhost:8000/v1/flights

curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  http://localhost:8000/v1/flights/<flight_id>/records
```

### Teammate integration (Tailscale)

Share with teammate:

- URL: `http://<your-tailscale-ip>:8000/v1/telemetry/ingest`
- API key: value of `INGEST_API_KEYS` in `.env`
- OpenAPI spec: `openapi/openapi.yaml`

They POST **normalized JSON** (L1), not raw binary telemetry.

## Architecture

| Component | Role |
|-----------|------|
| FastAPI (`api`) | Ingest + query endpoints |
| Redis | Translation job queue |
| Worker | Pulls jobs, calls Ollama, writes canonical JSON |
| SQLite (`/data/telemetry.db`) | Persistent storage |
| Ollama on Mac host | DeepSeek LLM inference |

## Local development (without Docker)

```bash
cd platform-api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
redis-server &  # or brew services start redis
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.worker
```

Set `OLLAMA_BASE_URL=http://127.0.0.1:11434` when running outside Docker.

## Azure (later)

Same `docker-compose.yml` deploys to an Azure VM in the final hackathon month. No code changes expected.
