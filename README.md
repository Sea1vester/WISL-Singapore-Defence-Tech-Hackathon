# WISL Singapore Defence Tech Hackathon

Hackathon repo for our drone telemetry MVP.

## Platform

The telemetry cloud platform lives in [`sdth-telemetry/`](sdth-telemetry/README.md):

- FastAPI ingest API (SQLite + Redis)
- Ollama/DeepSeek translation to canonical JSON
- Docker Compose for local dev; Tailscale for teammate integration

See [sdth-telemetry/README.md](sdth-telemetry/README.md) for setup and API docs.
