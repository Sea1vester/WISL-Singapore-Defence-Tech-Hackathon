FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY sdth-telemetry/platform-api/pyproject.toml sdth-telemetry/platform-api/README.md ./
COPY sdth-telemetry/platform-api/app ./app
COPY sdth-telemetry/platform-api/migrations ./migrations
COPY sdth-telemetry/parsers ./parsers
COPY sdth-replay/public /replay/public
COPY sdth-replay/src /replay/src

RUN pip install --no-cache-dir .

ENV DATABASE_PATH=/data/telemetry.db
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV REPLAY_STATIC_DIR=/replay/public
ENV RAW_DATASETS_DIR=/datasets

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
