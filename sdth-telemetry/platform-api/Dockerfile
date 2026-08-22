FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY platform-api/pyproject.toml platform-api/README.md ./
COPY platform-api/app ./app
COPY platform-api/migrations ./migrations
COPY parsers ./parsers

RUN pip install --no-cache-dir .

ENV DATABASE_PATH=/data/telemetry.db
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
